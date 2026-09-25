# v6 XGBoost 产量异常 + 生长季/极端指数 预测报告

- 面板: paper_panel_v7_prediction.parquet
- 目标变量: **log_yield**（绝对产量，现状）
- 特征 (15): temp, prec, sun, log_sown, gs_tmax_mean, gs_tmin_mean, gs_ppt, gs_srad, gs_pet, gdd10, gs_aridity, prec_cv, gs_prec_share, winter_temp, seasonal_temp_range
- 协议: LCO 10 折按县分组 + 时间外推(≤2019→2020-22); 种子 42

## 多种子结果

| seed | lco_r2 | lco_rmse | time_r2 | time_rmse |
|---|---|---|---|---|
| 42 | 0.6505 | 0.8222 | 0.4513 | 1.0517 |

## 特征重要性（时间模型）

| feature | importance |
|---|---|
| log_sown | 0.31609442830085754 |
| gdd10 | 0.1512109935283661 |
| seasonal_temp_range | 0.06773566454648972 |
| gs_tmax_mean | 0.0640735998749733 |
| winter_temp | 0.048521216958761215 |
| sun | 0.04620104283094406 |
| prec | 0.04327879846096039 |
| gs_tmin_mean | 0.041164807975292206 |
| gs_prec_share | 0.04024837911128998 |
| gs_aridity | 0.031969450414180756 |
| prec_cv | 0.030457906424999237 |
| temp | 0.03042149730026722 |
| gs_srad | 0.030256254598498344 |
| gs_ppt | 0.030002882704138756 |
| gs_pet | 0.028362993150949478 |
