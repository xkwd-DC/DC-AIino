# v6 XGBoost 产量异常 + 生长季/极端指数 预测报告

- 面板: paper_panel_v7_prediction.parquet
- 目标变量: **y_anom**（县 OLS 线性趋势残差=产量异常/增减产）
- 特征 (25): temp, prec, sun, spei_annual_mean, spei_growing_season_mean, ndvi_yearly, lst_day_growing_mean_k, fert, irr, flood, drou_a, flood_a, cropland_ratio, log_sown, gs_tmax_mean, gs_tmin_mean, gs_ppt, gs_srad, gs_pet, gdd10, gs_aridity, prec_cv, gs_prec_share, winter_temp, seasonal_temp_range
- 协议: LCO 10 折按县分组 + 时间外推(≤2019→2020-22); 种子 42

## 多种子结果

| seed | lco_r2 | lco_rmse | time_r2 | time_rmse |
|---|---|---|---|---|
| 42 | 0.026 | 0.1503 | -1.4 | 0.2757 |

## 特征重要性（时间模型）

| feature | importance |
|---|---|
| ndvi_yearly | 0.10213115066289902 |
| irr | 0.09156688302755356 |
| log_sown | 0.08824519068002701 |
| lst_day_growing_mean_k | 0.053387757390737534 |
| drou_a | 0.05298767611384392 |
| fert | 0.04963616281747818 |
| cropland_ratio | 0.04939241334795952 |
| flood | 0.03918326646089554 |
| prec_cv | 0.03839137405157089 |
| winter_temp | 0.033404771238565445 |
| sun | 0.03284590691328049 |
| prec | 0.03156694769859314 |
| temp | 0.029984651133418083 |
| gs_tmin_mean | 0.02841266430914402 |
| flood_a | 0.02816067449748516 |
| gs_srad | 0.027696939185261726 |
| seasonal_temp_range | 0.027039365842938423 |
| gs_pet | 0.02681947499513626 |
| gdd10 | 0.026698099449276924 |
| gs_ppt | 0.02583182230591774 |
| spei_growing_season_mean | 0.025441166013479233 |
| gs_aridity | 0.024873416870832443 |
| gs_prec_share | 0.024455606937408447 |
| spei_annual_mean | 0.023177186027169228 |
| gs_tmax_mean | 0.018669435754418373 |
