"""模型推理 API：POST /api/predict

当前阶段：mock 实现，使用 demo HTML 中的线性近似公式。
M2 节点后：在 _predict_mock() 位置换成 .pkl / .h5 真实模型调用，外部接口不变。
"""
import json
from pathlib import Path

from flask import Blueprint, request

from . import envelope

predict_bp = Blueprint("predict", __name__)

# ─── 启动时加载省份基线（与 app.py 共用同一份 JSON） ─────────────────────
_DATA_DIR = Path(__file__).resolve().parent.parent / "data"
with (_DATA_DIR / "provinces_baseline.json").open(encoding="utf-8") as f:
    _PROVINCES = {p["name"]: p for p in json.load(f)}

# ─── 线性近似的中心点与系数（来自 demo HTML，全国均值标定） ────────────
_CENTERS = {"irr": 56.7, "flood": 2.97, "sun": 2086, "temp": 14.0, "spei": -0.08}
_COEFS = {
    "irr":   -0.000115,   # 灌溉率 ↑ → 风险 ↓
    "flood":  0.000420,   # 洪涝占比 ↑ → 风险 ↑
    "sun":   -0.0000023,  # 日照时数 ↑ → 风险 ↓
    "temp":   0.000180,   # 平均气温 ↑ → 风险 ↑
    "spei":  -0.000310,   # SPEI ↑（更湿润）→ 风险 ↓
}
_BASELINE_RISK = 0.0235      # E[f(x)]：全国风险中枢
_CLIP = (0.005, 0.055)       # 模型输出区间
_FEATURE_LABELS = {
    "irr": "灌溉率", "flood": "洪涝占比", "sun": "日照时数",
    "temp": "平均气温", "spei": "SPEI 干旱指数",
}
_VALID_MODELS = {"xgboost", "lstm", "ensemble"}


def _contributions(params):
    """每个因子相对中心点的贡献，等价于 mock SHAP 值。"""
    return {k: (params[k] - _CENTERS[k]) * _COEFS[k] for k in _CENTERS}


def _predict_mock(params, model):
    """M2 后此函数被真实模型替换，签名保持不变。"""
    contribs = _contributions(params)
    raw = _BASELINE_RISK + sum(contribs.values())
    # 制造三个模型间的可见差异，方便前端调试 toggle
    raw *= {"xgboost": 1.0, "lstm": 1.03, "ensemble": 1.015}[model]
    risk = max(_CLIP[0], min(_CLIP[1], raw))
    return risk, contribs


def _shap_top(contribs, top_n=5):
    items = sorted(contribs.items(), key=lambda kv: abs(kv[1]), reverse=True)[:top_n]
    return [
        {
            "feature": _FEATURE_LABELS[k],
            "value": round(v, 6),
            "direction": "harm" if v > 0 else "protect",
        }
        for k, v in items
    ]


def _recommendations(contribs):
    """从贡献最大的 harm 因子里挑 1-2 条，给定性建议。M2 后接入王天硕的路径模型。"""
    harms = sorted(((k, v) for k, v in contribs.items() if v > 0), key=lambda kv: -kv[1])[:2]
    catalog = {
        "flood": ("提升排涝标准至 20 年一遇 + 建设生态调蓄区", "high", 1.0),
        "temp":  ("引入耐热品种，播期调整 7–15 天",         "medium", 0.6),
        "spei":  ("部署土壤墒情监测 + 推广节水灌溉",         "high",   0.7),
        "irr":   ("升级高标准农田灌溉系统",                  "high",   0.8),
        "sun":   ("光伏 + 智能温室补光（光照不足地区）",     "low",    0.4),
    }
    out = []
    for k, v in harms:
        action, priority, recovery_ratio = catalog[k]
        out.append({
            "action": action,
            "factor": _FEATURE_LABELS[k],
            "expected_delta": round(-v * recovery_ratio, 6),
            "priority": priority,
        })
    return out


@predict_bp.post("/api/predict")
def predict():
    body = request.get_json(silent=True) or {}
    province = body.get("province")
    params = body.get("params")
    model = body.get("model", "ensemble")
    year = body.get("year")

    # 输入校验（系统边界，必须严格）
    if not province or province not in _PROVINCES:
        return envelope(error={"code": 400, "message": f"unknown province: {province!r}"}, status=400)
    if not isinstance(params, dict):
        return envelope(error={"code": 400, "message": "params must be an object"}, status=400)
    missing = [k for k in _CENTERS if k not in params]
    if missing:
        return envelope(error={"code": 400, "message": f"missing params: {missing}"}, status=400)
    try:
        params = {k: float(params[k]) for k in _CENTERS}
    except (TypeError, ValueError):
        return envelope(error={"code": 400, "message": "all params must be numeric"}, status=400)
    if model not in _VALID_MODELS:
        return envelope(error={"code": 400, "message": f"model must be one of {sorted(_VALID_MODELS)}"}, status=400)

    risk, contribs = _predict_mock(params, model)
    baseline = _PROVINCES[province]["y"]

    return envelope(data={
        "province": province,
        "year": year,
        "model": model,
        "risk_score": round(risk, 6),
        "baseline": baseline,
        "delta": round(risk - baseline, 6),
        "confidence": 0.78,  # mock；真模型用预测区间 / MC dropout 计算
        "shap_top": _shap_top(contribs),
        "recommendations": _recommendations(contribs),
        "_mock": True,  # 明确标识：M2 后移除此字段
    })
