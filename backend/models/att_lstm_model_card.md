# Model Card — Attention-LSTM 基线（v3 真实单产，11 维，TIMESTEPS=1）

## 训练信息
- 训练日期：2026-05-21 17:20:01
- 训练人：熊鑫
- 数据源：data/interim/paper_panel_v3.parquet（MD5 前 12 位 `7f2070282216`，由石灵子 PR #7 重算）
- 数据规模：N = 403 行 → 403 个 (1, 11) 窗口
- Target：`yield_kg_per_ha`（真实单产 kg/ha）
- 协议：10 种子 `[0, 1, 2, 3, 4, 5, 6, 7, 8, 9]`，8:2 split，超参固定，TIMESTEPS=1

## 架构（feature-level attention gating）
Input (1, 11) → Reshape (11,)
  → Dense(11) → Softmax(name=`feature_attention`) → ⊙ features
  → Reshape (1, 11)
→ LSTM(64, return_sequences=True) → LSTM(32) → Dropout(0.2) → Dense(1)

为什么 feature-gating 而不是 timestep self-attention：
TIMESTEPS=1（论文设置），时间轴只有 1 个位置，timestep-level attention 无东西可注意。
改在 11 个特征维上学一组输入-相关的软掩码，权重和为 1，可解释、可与 XGB SHAP 对照。

## 超参
```json
{
  "timesteps": 1,
  "lstm_units": [
    64,
    32
  ],
  "dropout": 0.2,
  "batch_size": 16,
  "epochs": 100,
  "lr": 0.001,
  "early_stop_patience": 10
}
```

## 指标（10 种子）

| 指标 | 训练 mean | 训练 std | 测试 mean | 测试 std | 申报书硬指标 | 状态 |
|---|---|---|---|---|---|---|
| R² | 0.8617 | 0.0536 | 0.8160 | 0.0502 | ≥ 0.62 | ✅ |
| RMSE (kg/ha) | 383.3 | 66.5 | 456.4 | 59.6 | — | — |

## 各种子明细
- seed=0: te_R²=0.8009  te_RMSE=463.1 kg/ha  epochs=100
- seed=1: te_R²=0.7362  te_RMSE=503.0 kg/ha  epochs=100
- seed=2: te_R²=0.7338  te_RMSE=569.4 kg/ha  epochs=34
- seed=3: te_R²=0.8908  te_RMSE=358.2 kg/ha  epochs=100
- seed=4: te_R²=0.8238  te_RMSE=447.2 kg/ha  epochs=100
- seed=5: te_R²=0.8904  te_RMSE=370.3 kg/ha  epochs=100
- seed=6: te_R²=0.8323  te_RMSE=429.4 kg/ha  epochs=100
- seed=7: te_R²=0.8078  te_RMSE=506.6 kg/ha  epochs=100
- seed=8: te_R²=0.8329  te_RMSE=464.7 kg/ha  epochs=100
- seed=9: te_R²=0.8113  te_RMSE=452.3 kg/ha  epochs=100

## 10 种子 Attention 权重均值（11 维，按降序）
  1. Flood_A: 0.1038 ± 0.0320
  2. Mech: 0.1030 ± 0.0289
  3. Temp: 0.1022 ± 0.0188
  4. NDVI: 0.1012 ± 0.0260
  5. Sun: 0.0901 ± 0.0269
  6. Drou_A: 0.0889 ± 0.0438
  7. Flood_R: 0.0869 ± 0.0430
  8. Prec: 0.0847 ± 0.0240
  9. Fert: 0.0841 ± 0.0296
  10. SPEI: 0.0819 ± 0.0368
  11. Irr: 0.0733 ± 0.0152

## 与 XGB SHAP 对照（doc 06 §3.2 一致性任务）
- XGB SHAP top-3：`ndvi > temp > prec`
- Attention top-3：`Flood_A > Mech > Temp`

## 代表模型
- 保存的 `att_lstm_model.h5` / `att_lstm_x_scaler.pkl` / `att_lstm_y_scaler.pkl` 来自 **seed = 4**
  （test R² 0.8238，最贴近 10 种子中位数 0.8176）

## 与申报书对照
- 申报书 §3.1 硬指标 R² ≥ 0.62 → **mean test R² = 0.8160** ✅

## 后端集成
`backend/services/inference.py` 的 `predict_att_lstm_yield()` 加载
`att_lstm_model.h5` / `att_lstm_x_scaler.pkl` / `att_lstm_y_scaler.pkl`，返回
`(yield_kg_per_ha, attention_weights_dict)`，后者 11 维 sum=1。
