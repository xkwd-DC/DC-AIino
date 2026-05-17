# Model Card — LSTM 基线（v3 真实单产，11 维，TIMESTEPS=1）

## 训练信息
- 训练日期：2026-05-17 10:18:09
- 训练人：熊鑫
- 数据源：data/interim/paper_panel_v3.parquet（MD5 前 12 位 `7f2070282216`，由石灵子 PR #7 重算）
- 数据规模：N = 403 行 → 403 个 (1, 11) 窗口
- Target：`yield_kg_per_ha`（真实单产 kg/ha，由原始 .xlsx 重算，**非王天硕已煮熟的 Y**）
- 协议：10 种子 `[0, 1, 2, 3, 4, 5, 6, 7, 8, 9]`，8:2 split，超参固定，TIMESTEPS=1

## 架构
输入 (1, 11) → LSTM(64, return_sequences=True) → LSTM(32) → Dropout(0.2) → Dense(1)
优化器：Adam(lr=0.001)   损失：MSE   EarlyStopping(patience=10)

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

| 指标 | 训练集 mean | 训练集 std | 测试集 mean | 测试集 std | 申报书硬指标 | 状态 |
|---|---|---|---|---|---|---|
| R² | 0.9280 | 0.0119 | 0.8856 | 0.0223 | ≥ 0.62 | ✅ |
| RMSE (kg/ha) | 279.8 | 20.6 | 362.0 | 29.2 | — | — |

> 旧 RMSE 阈值 0.0055 已作废：那是 normalized y 上的指标。论文报告 R²=0.6619 / RMSE=0.0046 同样基于 normalized y，与本基线不可直接比较，仅作历史脚注。

## 各种子明细
- seed=0: te_R²=0.8848  te_RMSE=352.3 kg/ha  epochs=100
- seed=1: te_R²=0.8264  te_RMSE=408.0 kg/ha  epochs=100
- seed=2: te_R²=0.9040  te_RMSE=342.0 kg/ha  epochs=85
- seed=3: te_R²=0.8973  te_RMSE=347.3 kg/ha  epochs=100
- seed=4: te_R²=0.9103  te_RMSE=319.1 kg/ha  epochs=77
- seed=5: te_R²=0.8944  te_RMSE=363.3 kg/ha  epochs=100
- seed=6: te_R²=0.8889  te_RMSE=349.4 kg/ha  epochs=100
- seed=7: te_R²=0.8693  te_RMSE=417.8 kg/ha  epochs=81
- seed=8: te_R²=0.8896  te_RMSE=377.7 kg/ha  epochs=87
- seed=9: te_R²=0.8912  te_RMSE=343.5 kg/ha  epochs=82

## 代表模型
- 保存的 `lstm_model.h5` / `lstm_scaler.pkl` / `lstm_history.json` 来自 **seed = 8**
  （test R² 0.8896，最贴近 10 种子中位数 0.8904）
- 该 seed 训练详情：训练 R² 0.9135 / RMSE 303.1 kg/ha，87/100 epochs
- 全部 10 个 seed 的完整结果见 `lstm_seeds_results.json`

## 与申报书对照
- 申报书 §3.1 硬指标 R² ≥ 0.62 → **mean test R² = 0.8856** ✅

## 背景
本基线为 `project_v3_real_yield_finding.md` **路线 E 第 2 项**：在真实单产上的 LSTM 基线。
路线 E 第 1 项（XGBoost）见 `model_card.md`；对照消融 `y_butter` 残差是第 3 项。

## TIMESTEPS 选择
- 当前用 TIMESTEPS=1（cheatsheet §5.3：论文 N=403 暗示 timesteps=1 = LSTM-as-MLP）
- 若要切真·时序，把脚本顶部 `TIMESTEPS = 1` 改成 5，每省样本数会变成 13-5+1=9
- 改完 TIMESTEPS 后建议同步更新 model card / inference.py

## 状态
✅ 多种子均值通过申报书硬指标。

> ⚠️ 注意：`lstm_feature_columns.json` 现在是 11 列（原 10 列）；若 `backend/inference.py` 仍按 10 列硬编码，需要同步更新。
