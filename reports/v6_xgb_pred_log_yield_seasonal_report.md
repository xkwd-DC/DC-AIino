# v6 XGBoost 产量异常 + 生长季/极端指数 预测报告

- 面板: paper_panel_v7_prediction.parquet
- 目标变量: **log_yield**（绝对产量，现状）
- 特征 (25): temp, prec, sun, spei_annual_mean, spei_growing_season_mean, ndvi_yearly, lst_day_growing_mean_k, fert, irr, flood, drou_a, flood_a, cropland_ratio, log_sown, gs_tmax_mean, gs_tmin_mean, gs_ppt, gs_srad, gs_pet, gdd10, gs_aridity, prec_cv, gs_prec_share, winter_temp, seasonal_temp_range
- 协议: LCO 10 折按县分组 + 时间外推(≤2019→2020-22); 种子 42

## 多种子结果

| seed | lco_r2 | lco_rmse | time_r2 | time_rmse |
|---|---|---|---|---|
| 42 | 0.6792 | 0.7877 | -0.4241 | 1.6945 |

## 特征重要性（时间模型）

| feature | importance |
|---|---|
| cropland_ratio | 0.260754257440567 |
| log_sown | 0.14641638100147247 |
| gdd10 | 0.08032137900590897 |
| drou_a | 0.07495729625225067 |
| gs_tmax_mean | 0.04516668990254402 |
| flood_a | 0.04110446944832802 |
| irr | 0.03540097549557686 |
| seasonal_temp_range | 0.029768042266368866 |
| lst_day_growing_mean_k | 0.029685886576771736 |
| gs_pet | 0.021560654044151306 |
| sun | 0.021243873983621597 |
| gs_tmin_mean | 0.021208206191658974 |
| winter_temp | 0.019927699118852615 |
| ndvi_yearly | 0.01914108544588089 |
| prec | 0.01827494613826275 |
| flood | 0.018212633207440376 |
| gs_ppt | 0.017025955021381378 |
| spei_growing_season_mean | 0.01548723503947258 |
| fert | 0.013629884459078312 |
| gs_srad | 0.013186614960432053 |
| prec_cv | 0.013059222139418125 |
| gs_aridity | 0.012817938812077045 |
| gs_prec_share | 0.011685431003570557 |
| temp | 0.011409630998969078 |
| spei_annual_mean | 0.008553561754524708 |
