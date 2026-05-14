"""模型推理 API：POST /api/predict

当前阶段：mock 实现，使用 demo HTML 的线性近似公式扩展到 10 个核心特征。
M2 节点后：在 _predict_mock() 位置换成 .pkl / .h5 真实模型调用，外部接口不变。

字段映射（API → 训练 feature_columns.json）：
  irr → Irr,  flood → Flood_R,  sun → Sun,  temp → Temp,  spei → SPEI,
  prec → Prec, mech → Mech, fert → Fert, drou_a → Drou_A, flood_a → Flood_A
  （ndvi 是 UI doc 增加的第 11 个特征，训练时是否纳入由算法组决定）
"""
import json
from pathlib import Path

from flask import Blueprint, request

from . import envelope

predict_bp = Blueprint("predict", __name__)

# ─── 启动时加载省份基线 ─────────────────────────────────────────────────
_DATA_DIR = Path(__file__).resolve().parent.parent / "data"
with (_DATA_DIR / "provinces_baseline.json").open(encoding="utf-8") as f:
    _PROVINCES = {p["name"]: p for p in json.load(f)}

# ─── 11 个特征的中心点与系数（线性近似 mock） ───────────────────────────
# 前 5 个系数来自 demo HTML 实测标定；后 6 个按 UI doc SHAP 重要性比例外推
_CENTERS = {
    "irr":     56.7,   "flood":   2.97, "sun":     2086, "temp":    14.0,  "spei":    -0.08,
    "prec":     800,   "mech":    800,  "fert":     200, "drou_a":   4.0,  "flood_a":   3.0,
    "ndvi":     0.0,
}
_COEFS = {
    "irr":     -0.000115,    # 灌溉率 ↑ → 风险 ↓
    "flood":    0.000420,    # 洪涝占比 ↑ → 风险 ↑
    "sun":     -0.0000023,   # 日照 ↑ → 风险 ↓
    "temp":     0.000180,    # 气温 ↑ → 风险 ↑
    "spei":    -0.000310,    # SPEI ↑（湿润）→ 风险 ↓
    "prec":     0.0000010,   # 降水 ↑ → 洪涝风险 ↑
    "mech":    -0.0000040,   # 农机总动力 ↑ → 韧性 ↑
    "fert":     0.0000050,   # 化肥过量 → 致灾 ↑
    "drou_a":   0.0002500,   # 旱灾面积 ↑ → 风险 ↑
    "flood_a":  0.0002200,   # 水灾面积 ↑ → 风险 ↑
    "ndvi":    -0.0008000,   # NDVI 异常正向 → 植被健康 → 韧性 ↑
}
_BASELINE_RISK = 0.0235      # E[f(x)]：全国风险中枢
_CLIP = (0.005, 0.055)       # 模型输出区间

_FEATURE_LABELS = {
    "irr":     "灌溉率",      "flood":   "洪涝占比", "sun":  "日照时数",
    "temp":    "平均气温",    "spei":    "SPEI 干旱指数",
    "prec":    "降水量",      "mech":    "农机总动力", "fert": "化肥施用量",
    "drou_a":  "旱灾面积",    "flood_a": "水灾面积", "ndvi": "NDVI 异常",
}
_VALID_MODELS = {"xgboost", "lstm", "ensemble"}
_FEATURES = list(_CENTERS.keys())


def _contributions(params):
    return {k: (params[k] - _CENTERS[k]) * _COEFS[k] for k in _FEATURES}


def _predict_single(params, model_scale):
    """单模型预测 + clip。model_scale 用于在 mock 阶段制造模型间的可见差异。"""
    contribs = _contributions(params)
    raw = _BASELINE_RISK + sum(contribs.values())
    raw *= model_scale
    return max(_CLIP[0], min(_CLIP[1], raw)), contribs


def _predict_mock(params, model):
    """M2 后此函数被真实模型替换。

    返回：(主结果 dict, contribs)
    - 单模型（xgboost/lstm）：dict 含 risk_score
    - ensemble：dict 含 xgboost_risk / lstm_risk / consensus / divergence / risk_score
    """
    xgb_risk, contribs = _predict_single(params, 1.0)
    lstm_risk, _ = _predict_single(params, 1.03)

    if model == "xgboost":
        return {"risk_score": round(xgb_risk, 6)}, contribs
    if model == "lstm":
        return {"risk_score": round(lstm_risk, 6)}, contribs

    consensus = (xgb_risk + lstm_risk) / 2
    return {
        "risk_score": round(consensus, 6),   # 等价 consensus，保留主字段方便前端单值场景
        "xgboost_risk": round(xgb_risk, 6),
        "lstm_risk": round(lstm_risk, 6),
        "consensus": round(consensus, 6),
        "divergence": round(abs(xgb_risk - lstm_risk), 6),
    }, contribs


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
        "flood":   ("提升排涝标准至 20 年一遇 + 建设生态调蓄区", "high",   1.0),
        "temp":    ("引入耐热品种，播期调整 7–15 天",            "medium", 0.6),
        "spei":    ("部署土壤墒情监测 + 推广节水灌溉",            "high",   0.7),
        "irr":     ("升级高标准农田灌溉系统",                     "high",   0.8),
        "sun":     ("光伏 + 智能温室补光（光照不足地区）",         "low",    0.4),
        "prec":    ("加强极端降水监测，完善农田排水",              "medium", 0.5),
        "mech":    ("加大农机购置补贴，提升机械化率",              "medium", 0.6),
        "fert":    ("推广测土配方施肥，降低化肥过量",              "medium", 0.5),
        "drou_a":  ("旱灾应急储备库 + 抗旱品种轮作",              "high",   0.6),
        "flood_a": ("水灾应急储备 + 流域生态修复",                "high",   0.6),
        "ndvi":    ("退化植被生态修复 + 长势遥感监测",            "low",    0.5),
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


def _fill_from_baseline(province, params):
    """缺失字段用省份基线补全。返回完整 11 字段的 dict。"""
    baseline = _PROVINCES[province]
    return {k: float(params.get(k, baseline[k])) for k in _FEATURES}


@predict_bp.post("/api/predict")
def predict():
    body = request.get_json(silent=True) or {}
    province = body.get("province")
    params_in = body.get("params", {})
    model = body.get("model", "ensemble")
    year = body.get("year")

    # 输入校验（系统边界，必须严格）
    if not province or province not in _PROVINCES:
        return envelope(error={"code": 400, "message": f"unknown province: {province!r}"}, status=400)
    if not isinstance(params_in, dict):
        return envelope(error={"code": 400, "message": "params must be an object"}, status=400)
    unknown = [k for k in params_in if k not in _FEATURES]
    if unknown:
        return envelope(error={"code": 400, "message": f"unknown param keys: {unknown}; allowed: {_FEATURES}"}, status=400)
    if model not in _VALID_MODELS:
        return envelope(error={"code": 400, "message": f"model must be one of {sorted(_VALID_MODELS)}"}, status=400)
    try:
        params = _fill_from_baseline(province, params_in)
    except (TypeError, ValueError):
        return envelope(error={"code": 400, "message": "all params must be numeric"}, status=400)

    risk_payload, contribs = _predict_mock(params, model)
    baseline = _PROVINCES[province]["y"]

    data = {
        "province": province,
        "year": year,
        "model": model,
        "baseline": baseline,
        "delta": round(risk_payload["risk_score"] - baseline, 6),
        "confidence": 0.78,  # mock；真模型用预测区间 / MC dropout 计算
        "shap_top": _shap_top(contribs),
        "recommendations": _recommendations(contribs),
        "params_used": {k: round(params[k], 4) for k in _FEATURES},
        "params_filled_from_baseline": sorted(set(_FEATURES) - set(params_in.keys())),
        "_mock": True,  # M2 接真模型后移除
    }
    data.update(risk_payload)  # risk_score + (ensemble: xgboost_risk/lstm_risk/consensus/divergence)
    return envelope(data=data)
