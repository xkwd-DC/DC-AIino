# Model Card — XGBoost 基线（v3 真实单产，11 维）

## 训练信息
- 训练日期：2026-05-17 10:03:58
- 训练人：熊鑫
- 数据源：data/interim/paper_panel_v3.parquet（MD5 前 12 位 `7f2070282216`，由石灵子 PR #7 重算）
- 数据规模：N = 403（31 省 × 13 年），11 维 X（原 10 维 + NDVI）
- Target：`yield_kg_per_ha`（真实单产 kg/ha，由原始 .xlsx 重算，**非王天硕已煮熟的 Y**）
- 协议：10 种子 `[0, 1, 2, 3, 4, 5, 6, 7, 8, 9]`，8:2 split，超参固定

## 超参（论文 §4.1）
```json
{
  "learning_rate": 0.1,
  "max_depth": 6,
  "n_estimators": 150,
  "objective": "reg:squarederror"
}
```

## 指标（10 种子）

| 指标 | 训练集 mean | 训练集 std | 测试集 mean | 测试集 std | 申报书硬指标 | 状态 |
|---|---|---|---|---|---|---|
| R² | 1.0000 | 0.0000 | 0.9072 | 0.0383 | ≥ 0.62 | ✅ |
| RMSE (kg/ha) | 4.5 | 0.7 | 312.5 | 54.2 | — | — |

> 旧 RMSE 阈值 0.0055 已作废：那是 normalized y 上的指标，本次 target 单位为 kg/ha（≈3700 量级）。

## SHAP Top 5（10 种子 mean|SHAP| 平均）
1. ndvi: 510.1943
2. temp: 219.7554
3. prec: 218.9410
4. irr: 213.7525
5. fert: 91.5836

期望 Top 3（申报书 §1.3）：`irr > flood > sun`
实测 Top 3：`ndvi > temp > prec`    ⚠️ 不一致

## 代表模型
- 保存的 `xgb_model.pkl` / `scaler.pkl` 来自 **seed = 9**
  （test R² 0.9182，最贴近 10 种子中位数 0.9163）
- 全部 10 个 seed 的完整结果见 `xgb_seeds_results.json`

## 与申报书对照
- 申报书 §3.1 硬指标 R² ≥ 0.62 → **mean test R² = 0.9072** ✅ 远超
- 申报书 §1.3 期望 SHAP Top-3 顺序 → ⚠️ 实测为 ndvi > temp > prec

## 背景
本基线为 `project_v3_real_yield_finding.md` **路线 E 第 1 项**：在真实单产（而非王天硕 PR 前已煮熟的 Y）上的 XGB 基线。
对照消融 `y_butter` 残差另起脚本；LSTM 基线（路线 E 第 2 项）需同步重训。

## 状态
✅ 基线通过申报书硬指标，可作为下游 LSTM / Attention-LSTM 的参照。

> ⚠️ 注意：`feature_columns.json` 现在是 11 列（原 10 列）；若 `backend/inference.py` 仍按 10 列硬编码，需要同步更新。
