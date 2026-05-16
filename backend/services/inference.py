"""模型推理服务 — 接口契约（Protocol stub）

当前为骨架，**仅定义类型 / 接口**，未实装。
M2 节点（2026-11 前）由潘妙齐填充实现：
  - load_models() 启动时加载 .pkl/.h5/scaler
  - predict_xgboost / predict_lstm / predict_dual 输入 11 特征 → 风险 + SHAP

算法组（王天硕、张嘉越）只需保证产出的模型能用本文件底部 demo 加载即可。
详细要求见 docs/07_模型训练任务_算法组.md
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


# ─── 算法组验收脚本（参考实现） ─────────────────────────────────────────
def _sanity_check_loadable():
    """给王天硕 / 张嘉越交付时跑一遍这个，确认模型能被后端加载。

    使用：
        python -m backend.services.inference

    通过 = 你的训练产物符合后端集成要求。
    """
    import json
    from pathlib import Path

    import joblib
    import numpy as np
    import tensorflow as tf

    models_dir = Path(__file__).resolve().parent.parent / "models"
    required = ["xgb_model.pkl", "lstm_model.h5", "scaler.pkl", "feature_columns.json"]
    missing = [f for f in required if not (models_dir / f).exists()]
    if missing:
        print(f"❌ 缺少文件：{missing}")
        print(f"   预期路径：{models_dir}")
        return False

    columns = json.load(open(models_dir / "feature_columns.json"))
    if columns != TRAINING_FEATURE_ORDER:
        print(f"❌ feature_columns.json 与契约不一致")
        print(f"   期望：{TRAINING_FEATURE_ORDER}")
        print(f"   实际：{columns}")
        return False

    xgb = joblib.load(models_dir / "xgb_model.pkl")
    lstm = tf.keras.models.load_model(models_dir / "lstm_model.h5", compile=False)
    scaler = joblib.load(models_dir / "scaler.pkl")

    # 河南 2022 测试样例（与 docs/07 §3.3 一致）
    henan_2022 = np.array([[65.4, 4.2, 2240, 14.2, -0.2, 750, 1620, 360, 4.5, 3.8, -0.05]])
    scaled = scaler.transform(henan_2022)

    xgb_risk = float(xgb.predict(scaled)[0])
    lstm_risk = float(lstm.predict(scaled.reshape(1, 1, 11), verbose=0)[0][0])

    print(f"✅ xgb_model.pkl   → 河南 2022 risk = {xgb_risk:.4f}")
    print(f"✅ lstm_model.h5   → 河南 2022 risk = {lstm_risk:.4f}")
    print(f"   分歧 |Δ| = {abs(xgb_risk - lstm_risk):.4f}")

    ok = (
        0.020 <= xgb_risk <= 0.030 and
        0.020 <= lstm_risk <= 0.030 and
        abs(xgb_risk - lstm_risk) <= 0.005
    )
    print("✅ PASS" if ok else "❌ FAIL — 输出超出预期区间，请排查训练数据 / 模型加载")
    return ok


if __name__ == "__main__":
    _sanity_check_loadable()
