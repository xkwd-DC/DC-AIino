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


def test_provinces_item_has_all_11_features(client):
    res = client.get("/api/provinces")

    item = res.get_json()["data"][0]
    required = {
        "name", "y", "type", "summary",
        "irr", "flood", "sun", "temp", "spei",
        "prec", "mech", "fert", "drou_a", "flood_a", "ndvi",
    }
    assert required.issubset(item.keys())


# ─── /api/predict 正常路径 ──────────────────────────────────────────────
VALID_5 = {"irr": 65.4, "flood": 4.2, "sun": 2240, "temp": 14.2, "spei": -0.2}
VALID_11 = {**VALID_5, "prec": 750, "mech": 1620, "fert": 360, "drou_a": 4.5, "flood_a": 3.8, "ndvi": -0.05}


def test_predict_happy_path_full_11_features(client):
    res = client.post(
        "/api/predict",
        json={"province": "河南", "year": 2026, "params": VALID_11, "model": "ensemble"},
    )

    assert res.status_code == 200
    data = res.get_json()["data"]
    assert data["province"] == "河南"
    assert data["model"] == "ensemble"
    assert 0.005 <= data["risk_score"] <= 0.055
    assert data["delta"] == round(data["risk_score"] - data["baseline"], 6)
    assert data["_mock"] is True
    assert data["params_filled_from_baseline"] == []


def test_predict_partial_params_filled_from_baseline(client):
    """只传 5 字段（情景模拟器 UX），其余从省份基线补全。"""
    res = client.post(
        "/api/predict", json={"province": "河南", "params": VALID_5}
    )

    assert res.status_code == 200
    data = res.get_json()["data"]
    assert set(data["params_filled_from_baseline"]) == {"prec", "mech", "fert", "drou_a", "flood_a", "ndvi"}
    # 用户传的值原样回显
    assert data["params_used"]["irr"] == 65.4
    # 未传的字段用 河南 基线 填补
    assert data["params_used"]["prec"] == 750.0


def test_predict_empty_params_uses_full_baseline(client):
    """完全不传 params，等价于查询该省基线风险。"""
    res = client.post("/api/predict", json={"province": "河南"})

    data = res.get_json()["data"]
    assert len(data["params_filled_from_baseline"]) == 11


def test_predict_ensemble_returns_dual_breakdown(client):
    res = client.post("/api/predict", json={"province": "河南", "params": VALID_11, "model": "ensemble"})

    data = res.get_json()["data"]
    for k in ("xgboost_risk", "lstm_risk", "consensus", "divergence"):
        assert k in data, f"ensemble must return {k}"
    assert data["consensus"] == data["risk_score"]
    assert data["divergence"] >= 0
    assert data["divergence"] == round(abs(data["xgboost_risk"] - data["lstm_risk"]), 6)


def test_predict_single_model_no_dual_breakdown(client):
    res = client.post("/api/predict", json={"province": "河南", "params": VALID_11, "model": "xgboost"})

    data = res.get_json()["data"]
    assert "xgboost_risk" not in data
    assert "consensus" not in data


def test_predict_shap_top_includes_new_features(client):
    """高 NDVI 异常时，NDVI 应进入 SHAP top。"""
    params = {**VALID_5, "ndvi": -1.5}
    res = client.post("/api/predict", json={"province": "河南", "params": params})

    shap = res.get_json()["data"]["shap_top"]
    features = [s["feature"] for s in shap]
    assert "NDVI 异常" in features


def test_predict_clamps_to_max_with_extreme_input(client):
    extreme = {"irr": 0, "flood": 100, "sun": 0, "temp": 50, "spei": -5, "drou_a": 50, "flood_a": 50}

    res = client.post("/api/predict", json={"province": "河南", "params": extreme})

    assert res.get_json()["data"]["risk_score"] <= 0.055


# ─── /api/predict 校验错误 ──────────────────────────────────────────────
def test_predict_400_when_province_missing(client):
    res = client.post("/api/predict", json={"params": VALID_11})

    assert res.status_code == 400
    assert "province" in res.get_json()["error"]["message"]


def test_predict_400_when_province_unknown(client):
    res = client.post("/api/predict", json={"province": "火星", "params": VALID_11})

    assert res.status_code == 400
    assert "province" in res.get_json()["error"]["message"]


def test_predict_400_when_unknown_param_key(client):
    res = client.post(
        "/api/predict", json={"province": "河南", "params": {"gpu_count": 8}}
    )

    assert res.status_code == 400
    assert "unknown param keys" in res.get_json()["error"]["message"]


def test_predict_400_when_param_not_numeric(client):
    bad = {**VALID_5, "temp": "热"}

    res = client.post("/api/predict", json={"province": "河南", "params": bad})

    assert res.status_code == 400
    assert "numeric" in res.get_json()["error"]["message"]


def test_predict_400_when_model_invalid(client):
    res = client.post(
        "/api/predict",
        json={"province": "河南", "params": VALID_11, "model": "gpt"},
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
