"""模型推理服务 — 接口契约（Protocol stub）+ 参考实现

当前为骨架，**`ModelInferer` 仅定义类型 / 接口**。
M2 节点（2026-11 前）由潘妙齐填充 Protocol 的 predict_xgboost / predict_lstm /
predict_dual（接 SHAP / attention weights / consensus）。

本文件已落地的最小参考实现：
  - `_load_artifacts()`：加载 6 个 artifact，校验两份 feature_columns 与契约一致
  - `predict_xgb_yield(features, *, xgb, x_scaler)` → 单产 kg/ha
  - `predict_lstm_yield(features, *, lstm, x_scaler, y_scaler)` → 单产 kg/ha
    （LSTM 训练时 y 做了 StandardScaler，predict 出 z-score，必须 inverse_transform
     回 kg/ha；M2 wrapper 必须保持这个 pipeline）

算法组（熊鑫）保证产出的 6 个 artifact（见 `_REQUIRED` 列表）能被
`_sanity_check_loadable()` 加载并通过 Henan 2022 样例的 PASS 检查。

详细要求见 docs/07_模型训练任务_算法组.md。
"""
from typing import Protocol, TypedDict

# ─── API 字段（小写）→ 训练字段（首字母大写） ─────────────────────────
API_TO_TRAINING = {
    "irr":     "Irr",
    "flood":   "Flood_R",
    "sun":     "Sun",
    "temp":    "Temp",
    "spei":    "SPEI",
    "prec":    "Prec",
    "mech":    "Mech",
    "fert":    "Fert",
    "drou_a":  "Drou_A",
    "flood_a": "Flood_A",
    "ndvi":    "NDVI",
}
TRAINING_TO_API = {v: k for k, v in API_TO_TRAINING.items()}

# 训练时输入 numpy 数组的列顺序（与 feature_columns.json 保持一致）
TRAINING_FEATURE_ORDER = list(API_TO_TRAINING.values())


def to_training_keys(api_params: dict[str, float]) -> dict[str, float]:
    """{'irr': 65.4, 'flood': 4.2, ...} → {'Irr': 65.4, 'Flood_R': 4.2, ...}"""
    return {API_TO_TRAINING[k]: v for k, v in api_params.items()}


def to_api_keys(training_dict: dict[str, float]) -> dict[str, float]:
    """{'Irr': 0.42, 'Flood_R': 0.38, ...} → {'irr': 0.42, 'flood': 0.38, ...}"""
    return {TRAINING_TO_API[k]: v for k, v in training_dict.items()}


# ─── 输出类型 ────────────────────────────────────────────────────────────
class XGBOutput(TypedDict):
    risk: float                          # 0.005–0.055
    shap_values: dict[str, float]        # 11 个特征的 SHAP 值（训练字段名）


class LSTMOutput(TypedDict):
    risk: float
    attention_weights: dict[str, float] | None   # Attention-LSTM 才有


class DualOutput(TypedDict):
    xgboost_risk: float
    lstm_risk: float
    consensus: float
    divergence: float
    shap_values: dict[str, float]


# ─── 推理接口（潘妙齐 M2 节点实装） ─────────────────────────────────────
class ModelInferer(Protocol):
    """所有方法接受**训练字段名**（大写）的特征 dict。

    API 层（api/predict.py）通过 to_training_keys() 转换后调用本服务。
    """

    def load_models(self) -> None:
        """启动时加载所有模型 + scaler 到内存。"""
        ...

    def predict_xgboost(self, features: dict[str, float]) -> XGBOutput: ...
    def predict_lstm(self, features: dict[str, float]) -> LSTMOutput: ...
    def predict_dual(self, features: dict[str, float]) -> DualOutput: ...


# ─── 参考实现（路线 E artifact 加载 + 推理 pipeline） ───────────────────
#
# Target 单位说明（重要！）：
#   路线 E 后 XGB / LSTM 都训练在 `yield_kg_per_ha`（真实单产，约 3000–4500 kg/ha）。
#   旧的 "risk_score ∈ [0.005, 0.055]" 语义来自王天硕的坏 Y，已废弃。
#   `api/predict.py` 的 _predict_mock 仍输出 risk_score —— M2 接真模型时需要
#   把 yield 映射到 risk（或直接换 API 语义），不是本文件的事。

_REQUIRED = [
    "xgb_model.pkl",          # XGBRegressor → 直接输出 kg/ha
    "scaler.pkl",             # XGB X StandardScaler
    "lstm_model.h5",          # Keras LSTM → 输出 z-score
    "lstm_scaler.pkl",        # LSTM X StandardScaler
    "lstm_y_scaler.pkl",      # LSTM y StandardScaler（z → kg/ha 必须 inverse_transform）
    "feature_columns.json",
    "lstm_feature_columns.json",
]


def _load_artifacts(models_dir=None):
    """加载全部 6 个 artifact + 2 份 feature_columns。

    返回：dict 含 keys ['xgb', 'xgb_x_scaler', 'lstm', 'lstm_x_scaler', 'lstm_y_scaler']

    校验项（任一失败 → RuntimeError）：
      - 7 个文件全部存在
      - feature_columns.json / lstm_feature_columns.json 均等于 TRAINING_FEATURE_ORDER
    """
    import json
    from pathlib import Path

    import joblib
    import tensorflow as tf

    if models_dir is None:
        models_dir = Path(__file__).resolve().parent.parent / "models"
    else:
        models_dir = Path(models_dir)

    missing = [f for f in _REQUIRED if not (models_dir / f).exists()]
    if missing:
        raise RuntimeError(f"缺少 artifact：{missing}（路径 {models_dir}）")

    for fname in ("feature_columns.json", "lstm_feature_columns.json"):
        cols = json.load(open(models_dir / fname))
        if cols != TRAINING_FEATURE_ORDER:
            raise RuntimeError(
                f"{fname} 与契约不一致\n  期望：{TRAINING_FEATURE_ORDER}\n  实际：{cols}"
            )

    return {
        "xgb": joblib.load(models_dir / "xgb_model.pkl"),
        "xgb_x_scaler": joblib.load(models_dir / "scaler.pkl"),
        "lstm": tf.keras.models.load_model(models_dir / "lstm_model.h5", compile=False),
        "lstm_x_scaler": joblib.load(models_dir / "lstm_scaler.pkl"),
        "lstm_y_scaler": joblib.load(models_dir / "lstm_y_scaler.pkl"),
    }


def predict_xgb_yield(features: dict[str, float], *, xgb, x_scaler) -> float:
    """XGB 推理 pipeline：dict(训练字段名) → kg/ha。

    XGB target 即 yield_kg_per_ha，predict 输出已经是原单位，无需 inverse_transform。
    """
    import numpy as np

    arr = np.array([[features[k] for k in TRAINING_FEATURE_ORDER]], dtype=float)
    return float(xgb.predict(x_scaler.transform(arr))[0])


def predict_lstm_yield(features: dict[str, float], *, lstm, x_scaler, y_scaler) -> float:
    """LSTM 推理 pipeline：dict(训练字段名) → kg/ha。

    关键步骤：lstm.predict 出 z-score（因 train 时对 y 做了 StandardScaler），
    必须 `y_scaler.inverse_transform` 回 kg/ha，否则得到的是无量纲值。
    """
    import numpy as np

    arr = np.array([[features[k] for k in TRAINING_FEATURE_ORDER]], dtype=float)
    scaled = x_scaler.transform(arr).reshape(1, 1, -1)        # (1, T=1, F=11)
    z = lstm.predict(scaled, verbose=0)[0][0]
    return float(y_scaler.inverse_transform(np.array([[z]]))[0][0])


def _sanity_check_loadable():
    """算法组交付验收脚本，确认 6 个 artifact 能被后端正确加载。

    使用：
        python -m backend.services.inference

    通过 = 你的训练产物符合后端集成要求（feature 顺序、scaler 名称、y_scaler 存在）。
    """
    # Henan 2022 测试样例 — 取自 data/interim/paper_panel_v3.parquet 实际行
    # （docs/07 §3.3 旧合成值未跟上 PR #7 的单位重整，比如 mech 1620 vs 实际 0.74，
    #   drou_a 4.5 vs 实际 307；树模型对此鲁棒、LSTM 不鲁棒。用真值。）
    # ground truth yield_kg_per_ha = 4615.01
    henan_2022 = {
        "Irr": 74.61, "Flood_R": 4.59, "Sun": 3355.83, "Temp": 16.23, "SPEI": -1.38,
        "Prec": 604.32, "Mech": 0.74, "Fert": 595.31, "Drou_A": 307.73, "Flood_A": 527.87,
        "NDVI": 0.60,
    }
    GROUND_TRUTH_YIELD = 4615.01  # 河南省 2022 实际单产

    try:
        art = _load_artifacts()
    except RuntimeError as e:
        print(f"❌ {e}")
        return False

    xgb_yield = predict_xgb_yield(
        henan_2022, xgb=art["xgb"], x_scaler=art["xgb_x_scaler"]
    )
    lstm_yield = predict_lstm_yield(
        henan_2022,
        lstm=art["lstm"],
        x_scaler=art["lstm_x_scaler"],
        y_scaler=art["lstm_y_scaler"],
    )

    xgb_err = xgb_yield - GROUND_TRUTH_YIELD
    lstm_err = lstm_yield - GROUND_TRUTH_YIELD
    print(f"  ground truth  = {GROUND_TRUTH_YIELD:.1f} kg/ha")
    print(f"✅ xgb_model.pkl  → 河南 2022 yield = {xgb_yield:.1f} kg/ha  (err {xgb_err:+.1f})")
    print(f"✅ lstm_model.h5  → 河南 2022 yield = {lstm_yield:.1f} kg/ha  (err {lstm_err:+.1f})")
    print(f"   两模型分歧 |Δ| = {abs(xgb_yield - lstm_yield):.1f} kg/ha")

    # 容忍度 = 3 × model card 报告的测试集 RMSE：
    #   XGB  test RMSE = 312.5 kg/ha  → tolerance 940
    #   LSTM test RMSE = 362.0 kg/ha  → tolerance 1086
    # 同时下限 500 kg/ha 防 z-score 漏 inverse_transform（z 通常在 ±2 → 漏算时 |y| < 5）。
    XGB_TOL, LSTM_TOL = 940.0, 1086.0
    MIN_YIELD = 500.0

    ok = (
        xgb_yield > MIN_YIELD
        and lstm_yield > MIN_YIELD
        and abs(xgb_err) <= XGB_TOL
        and abs(lstm_err) <= LSTM_TOL
    )
    if ok:
        print(f"✅ PASS（|err| ≤ 3× RMSE：XGB ≤ {XGB_TOL:.0f}, LSTM ≤ {LSTM_TOL:.0f}）")
    else:
        if xgb_yield <= MIN_YIELD or lstm_yield <= MIN_YIELD:
            print(f"❌ FAIL — yield < {MIN_YIELD:.0f}，可能 LSTM y_scaler.inverse_transform 漏调用")
        else:
            print(f"❌ FAIL — |err| 超出 3× RMSE 容忍区间，"
                  f"请排查 feature 顺序 / scaler 加载 / 模型 seed 匹配")
    return ok


if __name__ == "__main__":
    import sys

    sys.exit(0 if _sanity_check_loadable() else 1)
