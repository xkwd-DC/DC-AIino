"""模型推理 API：POST /api/predict

接入真实模型(Issue #39)。

字段映射(API → 训练 feature_columns.json):
  irr → Irr,  flood → Flood_R,  sun → Sun,  temp → Temp,  spei → SPEI,
  prec → Prec, mech → Mech, fert → Fert, drou_a → Drou_A, flood_a → Flood_A,
  ndvi → NDVI

模型加载策略
============
冷启动 TF/Keras 加载 .h5 需要数秒,不能每次请求加载。本模块在第一次需要时
通过 `_get_models()` 触发 `inference._load_artifacts()` 并缓存到 `_MODELS`
模块级变量;后续请求直接使用缓存的 model 对象。

启动期 smoke check (`run_startup_smoke_check`) 由 app.py 在 import 时调用,
失败 → raise → fail-fast,不静默 fallback。

yield → risk 映射
================
真实模型输出 yield_kg_per_ha(约 3000–5300),前端 API 契约保留 risk_score
∈ [0.005, 0.055] 不变。映射:

    relative_drop = (baseline_yield - pred_yield) / baseline_yield
    risk = _BASELINE_RISK + relative_drop * 0.10

每个省份的 `baseline_yield` 在 provinces_baseline.json 的 `yield_kg_per_ha`
字段提供(用 XGB 在该省 baseline 输入上预测得到,与生产推理一致)。

================================================================================
重要诚实约束(必读)
--------------------------------------------------------------------------------
本 API 的预测仅对 31 个**训练时已见过**的省份有效(`provinces_baseline.json`
白名单已强制收窄)。返回值反映:

    "省份历史 baseline + 输入参数对该 baseline 的小幅偏移"

并不代表跨省份可外推的 climate → yield 通用映射。Leave-province-out
交叉验证显示 R² 中位 = -16.83(31 省仅 1 省 R²>0),空间泛化能力不可用。

详见:`docs/_craic/robustness_summary_2026-05-22.md`
================================================================================
"""
from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Any

from flask import Blueprint, request

from . import envelope
from limiter import limiter

logger = logging.getLogger(__name__)

predict_bp = Blueprint("predict", __name__)

# ─── 启动时加载省份基线 ─────────────────────────────────────────────────
_DATA_DIR = Path(__file__).resolve().parent.parent / "data"
with (_DATA_DIR / "provinces_baseline.json").open(encoding="utf-8") as f:
    _PROVINCES = {p["name"]: p for p in json.load(f)}

# ─── 11 个特征定义 ───────────────────────────────────────────────────────
_FEATURE_LABELS = {
    "irr":     "灌溉率",      "flood":   "洪涝占比", "sun":  "日照时数",
    "temp":    "平均气温",    "spei":    "SPEI 干旱指数",
    "prec":    "降水量",      "mech":    "农机总动力", "fert": "化肥施用量",
    "drou_a":  "旱灾面积",    "flood_a": "水灾面积", "ndvi": "NDVI 异常",
}
_FEATURES = list(_FEATURE_LABELS.keys())
_VALID_MODELS = {"xgboost", "lstm", "ensemble"}

# ─── yield → risk 映射常量 ──────────────────────────────────────────────
_BASELINE_RISK = 0.0235      # 基线 yield 对应的 risk 中枢
_RISK_PER_DROP = 0.10        # 10% 单产下降 → +0.01 risk
_CLIP = (0.005, 0.055)


# ─── 启动期 Henan 2022 sanity check ─────────────────────────────────────
_HENAN_2022 = {
    "Irr": 74.61, "Flood_R": 4.59, "Sun": 3355.83, "Temp": 16.23, "SPEI": -1.38,
    "Prec": 604.32, "Mech": 0.74, "Fert": 595.31, "Drou_A": 307.73,
    "Flood_A": 527.87, "NDVI": 0.60,
}
_HENAN_2022_GROUND_TRUTH = 4615.01  # 河南 2022 实际单产 (kg/ha)
_HENAN_2022_TOLERANCE = 1370.0      # = 3 × Att-LSTM RMSE,见 inference._sanity_check_loadable


# ============================================================================
# Keras quantization_config 兼容补丁
# ----------------------------------------------------------------------------
# 训练 .h5 由 keras 3.14 保存,Dense 层 config 中带 `quantization_config`
# 字段;backend 上 python 3.10 装的 keras 3.12(3.13+ 要 py3.11+)不识别。
# 在 `_load_artifacts()` 触发 `tf.keras.models.load_model()` 之前,先 monkey
# patch `Dense.from_config` 丢弃这个未知 kwarg,即可加载。
#
# 等 deploy 环境升 python 3.11+ + keras 3.14+ 后,本补丁会变成 no-op
# (config.pop 找不到 key 时 no-op),不需要回滚。
# ============================================================================
def _apply_keras_compat_shim() -> None:
    """加载前应用 Dense.from_config 补丁,丢弃 keras 3.14 写入的 quantization_config。"""
    from tensorflow.keras.layers import Dense  # noqa: import-not-at-top, lazy

    if getattr(Dense, "_dc_ai_no_quant_patch_applied", False):
        return

    _original_from_config = Dense.from_config.__func__

    @classmethod
    def _patched_from_config(cls, config: dict) -> Any:
        config = dict(config)
        config.pop("quantization_config", None)
        return _original_from_config(cls, config)

    Dense.from_config = _patched_from_config
    Dense._dc_ai_no_quant_patch_applied = True
    logger.info("Applied keras Dense.from_config compat shim (drop quantization_config)")


# ============================================================================
# 模型 lazy load 缓存
# ----------------------------------------------------------------------------
# 首次调用 → `inference._load_artifacts()`(~3-5s 冷启动)→ 缓存到 _MODELS。
# 后续请求 O(预测时间)。
# ============================================================================
_MODELS: dict[str, Any] | None = None


def _get_models() -> dict[str, Any]:
    """返回缓存的模型 dict。首次调用触发加载 + 补丁。"""
    global _MODELS
    if _MODELS is None:
        _apply_keras_compat_shim()
        from services import inference  # lazy import — TF 启动慢
        logger.info("Loading model artifacts (first request, may take ~3-5s)...")
        _MODELS = inference._load_artifacts()
        logger.info("Model artifacts loaded successfully")
    return _MODELS


# ============================================================================
# 启动期 smoke check
# ----------------------------------------------------------------------------
# 由 app.py 在 import 时调用。任何环节失败 → raise RuntimeError → fail-fast。
# 跳过条件:DC_SKIP_MODEL_SMOKE=1(仅 CI / 离线开发场景)。
# ============================================================================
def run_startup_smoke_check() -> None:
    """加载模型 + 用 Henan 2022 验证 XGB 输出在容忍区间内。失败则 raise。"""
    if os.getenv("DC_SKIP_MODEL_SMOKE", "0") == "1":
        logger.warning("DC_SKIP_MODEL_SMOKE=1 — 跳过启动期模型自检,生产禁用")
        return

    from services import inference

    models = _get_models()
    yield_pred = inference.predict_xgb_yield(
        _HENAN_2022, xgb=models["xgb"], x_scaler=models["xgb_x_scaler"]
    )

    err = abs(yield_pred - _HENAN_2022_GROUND_TRUTH)
    if err > _HENAN_2022_TOLERANCE:
        raise RuntimeError(
            f"Startup smoke check FAILED — "
            f"Henan 2022 XGB yield {yield_pred:.1f} vs ground truth "
            f"{_HENAN_2022_GROUND_TRUTH:.1f} (|err|={err:.1f} > tol={_HENAN_2022_TOLERANCE:.1f}). "
            f"Possible causes: artifact corruption / wrong scaler / feature order mismatch."
        )

    logger.info(
        f"Startup smoke check PASS: Henan 2022 XGB yield "
        f"{yield_pred:.1f} kg/ha (err {yield_pred - _HENAN_2022_GROUND_TRUTH:+.1f}, "
        f"tol ±{_HENAN_2022_TOLERANCE:.0f})"
    )


# ============================================================================
# 推理 + 派生数据
# ============================================================================
def _yield_to_risk(pred_yield_kg: float, baseline_yield: float) -> float:
    """单产 → risk 映射。偏离基线越低 → 风险越高。

    baseline_yield → risk = _BASELINE_RISK
    10% drop      → +0.01 risk
    输出 clip 到 [0.005, 0.055] 与前端契约一致。
    """
    if baseline_yield <= 0:
        # 理论上 baseline_yield 来自模型预测应该恒 > 0;防御性兜底
        return _BASELINE_RISK
    relative_drop = (baseline_yield - pred_yield_kg) / baseline_yield
    risk = _BASELINE_RISK + relative_drop * _RISK_PER_DROP
    return max(_CLIP[0], min(_CLIP[1], risk))


def _baseline_yield_for(province: str) -> float:
    """从 provinces_baseline.json 取 yield_kg_per_ha;若缺失则报错。"""
    p = _PROVINCES[province]
    if "yield_kg_per_ha" not in p:
        raise RuntimeError(
            f"provinces_baseline.json 缺少 '{province}.yield_kg_per_ha' 字段。"
            f"运行 scripts/recompute_baseline_yields.py 或参见 Issue #39。"
        )
    return float(p["yield_kg_per_ha"])


def _predict_real(params: dict[str, float], model: str, province: str) -> tuple[dict, dict]:
    """调用真实模型。

    返回:(risk_payload, contribs)
      - 单模型:dict 含 risk_score
      - ensemble:dict 含 xgboost_risk / lstm_risk / consensus / divergence / risk_score
                       + att_lstm_yield_kg / att_lstm_risk(辅助信息)
      - contribs:dict[特征 → 对偏离 baseline 的贡献(用于 SHAP top-N 展示)]
    """
    from services import inference

    models = _get_models()
    training_features = inference.to_training_keys(params)
    baseline_yield = _baseline_yield_for(province)

    if model == "xgboost":
        yield_pred = inference.predict_xgb_yield(
            training_features,
            xgb=models["xgb"],
            x_scaler=models["xgb_x_scaler"],
        )
        risk = _yield_to_risk(yield_pred, baseline_yield)
        contribs = _approx_contribs(params, province)
        return {
            "risk_score": round(risk, 6),
            "yield_kg_per_ha": round(yield_pred, 1),
        }, contribs

    if model == "lstm":
        yield_pred = inference.predict_lstm_yield(
            training_features,
            lstm=models["lstm"],
            x_scaler=models["lstm_x_scaler"],
            y_scaler=models["lstm_y_scaler"],
        )
        risk = _yield_to_risk(yield_pred, baseline_yield)
        contribs = _approx_contribs(params, province)
        return {
            "risk_score": round(risk, 6),
            "yield_kg_per_ha": round(yield_pred, 1),
        }, contribs

    # ensemble: XGB + LSTM + Att-LSTM(辅助)
    xgb_yield = inference.predict_xgb_yield(
        training_features,
        xgb=models["xgb"],
        x_scaler=models["xgb_x_scaler"],
    )
    lstm_yield = inference.predict_lstm_yield(
        training_features,
        lstm=models["lstm"],
        x_scaler=models["lstm_x_scaler"],
        y_scaler=models["lstm_y_scaler"],
    )
    att_yield, _att_weights = inference.predict_att_lstm_yield(
        training_features,
        att_lstm=models["att_lstm"],
        attention_model=models["att_lstm_attention"],
        x_scaler=models["att_lstm_x_scaler"],
        y_scaler=models["att_lstm_y_scaler"],
    )

    xgb_risk = _yield_to_risk(xgb_yield, baseline_yield)
    lstm_risk = _yield_to_risk(lstm_yield, baseline_yield)
    att_risk = _yield_to_risk(att_yield, baseline_yield)
    consensus = (xgb_risk + lstm_risk) / 2
    contribs = _approx_contribs(params, province)

    return {
        "risk_score": round(consensus, 6),
        "xgboost_risk": round(xgb_risk, 6),
        "lstm_risk": round(lstm_risk, 6),
        "att_lstm_risk": round(att_risk, 6),
        "consensus": round(consensus, 6),
        "divergence": round(abs(xgb_risk - lstm_risk), 6),
        "xgboost_yield_kg_per_ha": round(xgb_yield, 1),
        "lstm_yield_kg_per_ha": round(lstm_yield, 1),
        "att_lstm_yield_kg_per_ha": round(att_yield, 1),
    }, contribs


# ────────────────────────────────────────────────────────────────────────
# Approximate per-feature contribution for SHAP top-N display.
#
# 真正的 SHAP 计算在 services/shap_api.py(M2 后接入)。这里用 single-feature
# perturbation 估计:把每个特征替换为该省 baseline,看 XGB 预测 yield 的变化,
# 反算成 risk 的变化。轻量级,够前端 top-5 高亮用,不替代 shap.TreeExplainer。
# ────────────────────────────────────────────────────────────────────────
_DATASET_MEAN: dict[str, float] | None = None


def _get_dataset_mean() -> dict[str, float]:
    """Lazy compute 跨 31 省 baseline 的特征均值, 用作 SHAP perturbation reference。

    用 dataset mean 而非省 baseline 做 perturbation:
    - 让"省内当前值 vs 跨省平均"的差异显现为非零贡献
    - 避免 caller 传入 == 省 baseline 时所有 contribs 退化为 0(原 bug)
    """
    global _DATASET_MEAN
    if _DATASET_MEAN is None:
        n = len(_PROVINCES)
        _DATASET_MEAN = {
            k: sum(p[k] for p in _PROVINCES.values()) / n for k in _FEATURES
        }
    return _DATASET_MEAN


def _approx_contribs(params: dict[str, float], province: str) -> dict[str, float]:
    """单特征扰动估计每个特征对 risk 的边际贡献(正 = 加风险)。

    Perturbation reference 用**跨 31 省 dataset mean**(不是该省 baseline),
    确保 caller 传 baseline params(M02 ShapDashboard 常见用法)也能拿到非零贡献。
    """
    from services import inference

    models = _get_models()
    baseline_yield = _baseline_yield_for(province)
    dataset_mean = _get_dataset_mean()

    training_full = inference.to_training_keys(params)
    full_yield = inference.predict_xgb_yield(
        training_full, xgb=models["xgb"], x_scaler=models["xgb_x_scaler"]
    )
    full_risk = _yield_to_risk(full_yield, baseline_yield)

    contribs = {}
    for k in _FEATURES:
        # 把第 k 个特征替换成 dataset mean,其它保留当前值
        perturbed = {**params, k: dataset_mean[k]}
        perturbed_training = inference.to_training_keys(perturbed)
        perturbed_yield = inference.predict_xgb_yield(
            perturbed_training, xgb=models["xgb"], x_scaler=models["xgb_x_scaler"]
        )
        perturbed_risk = _yield_to_risk(perturbed_yield, baseline_yield)
        # full_risk - perturbed_risk = 该特征(从 mean 偏离到 current)带来的 risk 增量
        contribs[k] = round(full_risk - perturbed_risk, 6)
    return contribs


def _shap_top(contribs: dict[str, float], top_n: int = 5) -> list[dict]:
    items = sorted(contribs.items(), key=lambda kv: abs(kv[1]), reverse=True)[:top_n]
    return [
        {
            "feature": _FEATURE_LABELS[k],
            "value": round(v, 6),
            "direction": "harm" if v > 0 else "protect",
        }
        for k, v in items
    ]


def _recommendations(contribs: dict[str, float]) -> list[dict]:
    """从贡献最大的 harm 因子里挑 1-2 条,给定性建议。"""
    harms = sorted(((k, v) for k, v in contribs.items() if v > 0), key=lambda kv: -kv[1])[:2]
    catalog = {
        "flood":   ("提升排涝标准至 20 年一遇 + 建设生态调蓄区", "high",   1.0),
        "temp":    ("引入耐热品种,播期调整 7–15 天",            "medium", 0.6),
        "spei":    ("部署土壤墒情监测 + 推广节水灌溉",            "high",   0.7),
        "irr":     ("升级高标准农田灌溉系统",                     "high",   0.8),
        "sun":     ("光伏 + 智能温室补光(光照不足地区)",         "low",    0.4),
        "prec":    ("加强极端降水监测,完善农田排水",              "medium", 0.5),
        "mech":    ("加大农机购置补贴,提升机械化率",              "medium", 0.6),
        "fert":    ("推广测土配方施肥,降低化肥过量",              "medium", 0.5),
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


def _fill_from_baseline(province: str, params: dict[str, float]) -> dict[str, float]:
    """缺失字段用省份基线补全。返回完整 11 字段的 dict。"""
    baseline = _PROVINCES[province]
    return {k: float(params.get(k, baseline[k])) for k in _FEATURES}


@predict_bp.post("/api/predict")
@limiter.limit("100 per hour")  # Issue #26 HIGH#3 - 真模型 CPU-heavy, DoS 防护 (按 IP)
def predict():
    body = request.get_json(silent=True) or {}
    province = body.get("province")
    params_in = body.get("params", {})
    model = body.get("model", "ensemble")
    year = body.get("year")

    # 输入校验(系统边界,必须严格)
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

    risk_payload, contribs = _predict_real(params, model, province)
    baseline = _PROVINCES[province]["y"]

    data = {
        "province": province,
        "year": year,
        "model": model,
        "baseline": baseline,
        "delta": round(risk_payload["risk_score"] - baseline, 6),
        "confidence": 0.78,  # 当前固定值;后续可用 MC dropout / 预测区间替换
        "shap_top": _shap_top(contribs),
        "recommendations": _recommendations(contribs),
        "params_used": {k: round(params[k], 4) for k in _FEATURES},
        "params_filled_from_baseline": sorted(set(_FEATURES) - set(params_in.keys())),
        "_mock": False,  # Issue #39 后改为 False;真模型生效
    }
    data.update(risk_payload)
    return envelope(data=data)
