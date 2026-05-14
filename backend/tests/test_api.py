"""端到端测试 4 个端点的契约 + 校验路径。AAA 模式。"""


# ─── /api/health ─────────────────────────────────────────────────────────
def test_health_returns_ok(client):
    res = client.get("/api/health")

    assert res.status_code == 200
    body = res.get_json()
    assert body["success"] is True
    assert body["error"] is None
    assert body["data"]["status"] == "ok"
    assert body["data"]["service"] == "grain-risk-api"


# ─── /api/provinces ──────────────────────────────────────────────────────
def test_provinces_returns_31(client):
    res = client.get("/api/provinces")

    assert res.status_code == 200
    body = res.get_json()
    assert body["success"] is True
    assert len(body["data"]) == 31


def test_provinces_item_has_required_fields(client):
    res = client.get("/api/provinces")

    item = res.get_json()["data"][0]
    required = {"name", "y", "irr", "flood", "sun", "temp", "spei", "type", "summary"}
    assert required.issubset(item.keys())


# ─── /api/predict 正常路径 ──────────────────────────────────────────────
VALID_PARAMS = {"irr": 65.4, "flood": 4.2, "sun": 2240, "temp": 14.2, "spei": -0.2}


def test_predict_happy_path(client):
    res = client.post(
        "/api/predict",
        json={"province": "河南", "year": 2026, "params": VALID_PARAMS, "model": "ensemble"},
    )

    assert res.status_code == 200
    data = res.get_json()["data"]
    assert data["province"] == "河南"
    assert data["model"] == "ensemble"
    assert 0.005 <= data["risk_score"] <= 0.055
    assert data["delta"] == round(data["risk_score"] - data["baseline"], 6)
    assert data["_mock"] is True


def test_predict_shap_top_shape(client):
    res = client.post("/api/predict", json={"province": "河南", "params": VALID_PARAMS})

    shap = res.get_json()["data"]["shap_top"]
    assert 1 <= len(shap) <= 5
    for entry in shap:
        assert entry["direction"] in {"harm", "protect"}
        assert isinstance(entry["value"], (int, float))


def test_predict_default_model_is_ensemble(client):
    res = client.post("/api/predict", json={"province": "河南", "params": VALID_PARAMS})

    assert res.get_json()["data"]["model"] == "ensemble"


def test_predict_models_produce_different_scores(client):
    scores = {}
    for model in ("xgboost", "lstm", "ensemble"):
        res = client.post(
            "/api/predict", json={"province": "河南", "params": VALID_PARAMS, "model": model}
        )
        scores[model] = res.get_json()["data"]["risk_score"]

    assert len(set(scores.values())) == 3, f"expected 3 distinct scores, got {scores}"


def test_predict_clamps_to_max_with_extreme_input(client):
    """风险值应被 clip 到 0.055 上限，不会无限上涨。"""
    extreme = {"irr": 0, "flood": 100, "sun": 0, "temp": 50, "spei": -5}

    res = client.post("/api/predict", json={"province": "河南", "params": extreme})

    assert res.get_json()["data"]["risk_score"] <= 0.055


# ─── /api/predict 校验错误 ──────────────────────────────────────────────
def test_predict_400_when_body_empty(client):
    res = client.post("/api/predict", json={})

    assert res.status_code == 400
    assert res.get_json()["error"]["code"] == 400


def test_predict_400_when_province_unknown(client):
    res = client.post("/api/predict", json={"province": "火星", "params": VALID_PARAMS})

    assert res.status_code == 400
    assert "province" in res.get_json()["error"]["message"]


def test_predict_400_when_params_missing(client):
    res = client.post("/api/predict", json={"province": "河南"})

    assert res.status_code == 400
    assert "params" in res.get_json()["error"]["message"]


def test_predict_400_when_params_partial(client):
    res = client.post(
        "/api/predict", json={"province": "河南", "params": {"irr": 60}}
    )

    assert res.status_code == 400
    msg = res.get_json()["error"]["message"]
    for field in ("flood", "sun", "temp", "spei"):
        assert field in msg


def test_predict_400_when_param_not_numeric(client):
    bad = {**VALID_PARAMS, "temp": "热"}

    res = client.post("/api/predict", json={"province": "河南", "params": bad})

    assert res.status_code == 400
    assert "numeric" in res.get_json()["error"]["message"]


def test_predict_400_when_model_invalid(client):
    res = client.post(
        "/api/predict",
        json={"province": "河南", "params": VALID_PARAMS, "model": "gpt"},
    )

    assert res.status_code == 400
    assert "model" in res.get_json()["error"]["message"]


# ─── 404 兜底 ────────────────────────────────────────────────────────────
def test_404_uses_unified_envelope(client):
    res = client.get("/api/this-does-not-exist")

    assert res.status_code == 404
    body = res.get_json()
    assert body["success"] is False
    assert body["data"] is None
    assert body["error"]["code"] == 404
