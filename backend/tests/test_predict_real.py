"""Integration tests for /api/predict against real model artifacts (Issue #39).

Uses 河南 2022 ground-truth parameters and asserts the API:
  1. Loads the real XGB / LSTM / Att-LSTM artifacts (no mock fallback)
  2. Returns risk_score within [0.005, 0.055]
  3. Surfaces xgboost_risk / lstm_risk in ensemble mode
  4. No longer carries the `_mock: True` flag

These tests are slower than test_api.py because the first invocation triggers
TF / Keras model load (~3-5s cold start). Subsequent calls reuse the cached
module-level `_MODELS` dict.
"""
import pytest

# Henan 2022 actual panel row — also used by services.inference._sanity_check_loadable.
# ground truth yield_kg_per_ha = 4615.01
HENAN_2022 = {
    "irr": 74.61, "flood": 4.59, "sun": 3355.83, "temp": 16.23, "spei": -1.38,
    "prec": 604.32, "mech": 0.74, "fert": 595.31, "drou_a": 307.73,
    "flood_a": 527.87, "ndvi": 0.60,
}


@pytest.fixture(scope="module", autouse=True)
def _ensure_models_loaded():
    """Force one cold load up front so individual tests have predictable latency."""
    from api.predict import _get_models
    _get_models()


# ─── ensemble: most informative output ──────────────────────────────────
def test_predict_henan_2022_ensemble_returns_real_yields(client):
    """POST /api/predict with Henan 2022 ensemble → real XGB+LSTM+Att-LSTM."""
    res = client.post(
        "/api/predict",
        json={"province": "河南", "year": 2022, "params": HENAN_2022, "model": "ensemble"},
    )

    assert res.status_code == 200
    body = res.get_json()
    assert body["success"] is True
    data = body["data"]

    # _mock removed (or explicitly False per Issue #39 contract)
    assert data["_mock"] is False, "Real models should be loaded; mock flag must be False"

    # risk_score within clamp
    assert 0.005 <= data["risk_score"] <= 0.055

    # ensemble surfaces both backbones
    assert "xgboost_risk" in data
    assert "lstm_risk" in data
    assert 0.005 <= data["xgboost_risk"] <= 0.055
    assert 0.005 <= data["lstm_risk"] <= 0.055

    # divergence and consensus consistent
    assert data["consensus"] == data["risk_score"]
    assert data["divergence"] == round(abs(data["xgboost_risk"] - data["lstm_risk"]), 6)

    # yield surfaced (real model output) and physically plausible (rice/wheat range)
    assert "xgboost_yield_kg_per_ha" in data
    assert "lstm_yield_kg_per_ha" in data
    assert 1000 < data["xgboost_yield_kg_per_ha"] < 10000
    assert 1000 < data["lstm_yield_kg_per_ha"] < 10000


# ─── single-model paths ─────────────────────────────────────────────────
def test_predict_henan_2022_xgboost(client):
    res = client.post(
        "/api/predict",
        json={"province": "河南", "params": HENAN_2022, "model": "xgboost"},
    )
    assert res.status_code == 200
    data = res.get_json()["data"]
    assert data["_mock"] is False
    assert 0.005 <= data["risk_score"] <= 0.055
    # single-model path should not return ensemble-only breakdown
    assert "xgboost_risk" not in data
    assert "consensus" not in data
    assert "yield_kg_per_ha" in data


def test_predict_henan_2022_lstm(client):
    res = client.post(
        "/api/predict",
        json={"province": "河南", "params": HENAN_2022, "model": "lstm"},
    )
    assert res.status_code == 200
    data = res.get_json()["data"]
    assert data["_mock"] is False
    assert 0.005 <= data["risk_score"] <= 0.055
    assert "yield_kg_per_ha" in data
    assert 1000 < data["yield_kg_per_ha"] < 10000


# ─── risk-yield mapping sanity ──────────────────────────────────────────
def test_predict_baseline_inputs_yield_near_baseline_risk(client):
    """When params == province baseline, risk should be close to _BASELINE_RISK (0.0235)."""
    res = client.post("/api/predict", json={"province": "河南", "model": "xgboost"})

    assert res.status_code == 200
    data = res.get_json()["data"]
    # All 11 params filled from baseline → predicted yield ≈ baseline_yield
    # → relative_drop ≈ 0 → risk ≈ _BASELINE_RISK (0.0235)
    # Allow tolerance for floating-point and small XGB tree noise.
    assert abs(data["risk_score"] - 0.0235) < 0.005, (
        f"Baseline params should map to baseline risk; got {data['risk_score']}"
    )


def test_predict_perturbation_produces_different_yield(client):
    """Perturbing a feature should noticeably change yield prediction.

    We don't assert direction — XGB on N=403 is non-monotonic for individual
    features due to tree interactions. We just assert the model is actually
    reading the param (not constant on input).
    """
    baseline_res = client.post("/api/predict", json={"province": "河南", "model": "xgboost"})
    baseline_yield = baseline_res.get_json()["data"]["yield_kg_per_ha"]

    # Significant irrigation drop
    res = client.post(
        "/api/predict",
        json={"province": "河南", "params": {"irr": 5}, "model": "xgboost"},
    )
    perturbed_yield = res.get_json()["data"]["yield_kg_per_ha"]

    # Model must respond to the parameter change (not a constant function)
    assert abs(perturbed_yield - baseline_yield) > 1.0, (
        f"Model output unchanged by 50+ unit irr drop "
        f"(baseline={baseline_yield}, perturbed={perturbed_yield}). "
        "Possible: scaler frozen or feature dropped."
    )
