# v10-04 日值极端指数消融

> 数据：`paper_panel_v7_prediction.parquet` + `nasapower_county_daily_extremes.parquet` ｜ 种子 42, 43, 44, 45, 46 ｜ 时间切分 ≤2019

| 目标 | 配置 | 特征数 | 行数 | 县数 | LCO R² | 时间外推 R² |
|---|---|---:|---:|---:|---|---|
| log_single_yield | CLIMG16 | 16 | 4693 | 627 | +0.5208 ± 0.0073 | +0.4474 ± 0.0064 |
| log_single_yield | CLIMG16+NP_ALL | 28 | 4693 | 627 | +0.5193 ± 0.0076 | +0.4269 ± 0.0103 |
| log_single_yield | CLIMG16+NP_CORE | 23 | 4693 | 627 | +0.5274 ± 0.0080 | +0.4524 ± 0.0144 |
| log_yield | CLIMG16 | 16 | 10407 | 1041 | +0.4489 ± 0.0065 | +0.3644 ± 0.0044 |
| log_yield | CLIMG16+NP_ALL | 28 | 10407 | 1041 | +0.4722 ± 0.0068 | +0.3511 ± 0.0083 |
| log_yield | CLIMG16+NP_CORE | 23 | 10407 | 1041 | +0.4735 ± 0.0068 | +0.3522 ± 0.0078 |

## 相对 CLIMG16 的增益

- **log_single_yield / CLIMG16+NP_ALL**：LCO Δ=-0.0015，时间外推 Δ=-0.0204
- **log_single_yield / CLIMG16+NP_CORE**：LCO Δ=+0.0066，时间外推 Δ=+0.0050
- **log_yield / CLIMG16+NP_ALL**：LCO Δ=+0.0233，时间外推 Δ=-0.0133
- **log_yield / CLIMG16+NP_CORE**：LCO Δ=+0.0247，时间外推 Δ=-0.0122

## 判读

- 若 OM 增益 ≥ +0.02 且方向稳定：日值极端值得进主模型，下一步做 4.6 km 网格版或固定阈值 R95p。
- 若增益在 ±0.01 内：日值极端对当前目标没有额外信息，问题更可能在目标/样本，而不是数据频率。
- 若增益为负：日值极端与现有 `gs_tmax/gs_aridity` 高度共线，先做相关性/消融，不要硬堆。

## 边界

- NASA POWER 是 0.5° 再分析/卫星融合，县治点最近格点，不是台站观测。
- `np_prec_p95` 是年内湿日 95 分位；跨年比较时更稳的做法是用 2012–2023 固定阈值重算 R95p。
- 所有配置都限制在同样本，但 NP 覆盖少的县会被丢掉；看 `n_rows` / `n_counties` 列。

> 复现：`python scripts/data/v10_04_daily_extremes_ablation.py`
