# v6 XGBoost 产量异常 + 生长季/极端指数 预测报告

- 面板: paper_panel_v7_prediction.parquet
- 目标变量: **y_anom**（县 OLS 线性趋势残差=产量异常/增减产）
- 特征 (15): temp, prec, sun, log_sown, gs_tmax_mean, gs_tmin_mean, gs_ppt, gs_srad, gs_pet, gdd10, gs_aridity, prec_cv, gs_prec_share, winter_temp, seasonal_temp_range
- 协议: LCO 10 折按县分组 + 时间外推(≤2019→2020-22); 种子 42

## 多种子结果

| seed | lco_r2 | lco_rmse | time_r2 | time_rmse |
|---|---|---|---|---|
| 42 | -0.0103 | 0.1531 | -0.62 | 0.2265 |

## 特征重要性（时间模型）

| feature | importance |
|---|---|
| log_sown | 0.1266898363828659 |
| prec_cv | 0.09152013063430786 |
| gs_prec_share | 0.07892477512359619 |
| winter_temp | 0.07211290299892426 |
| gdd10 | 0.06835593283176422 |
| sun | 0.0642203837633133 |
| gs_ppt | 0.06224703788757324 |
| gs_tmin_mean | 0.0605374276638031 |
| seasonal_temp_range | 0.058561719954013824 |
| gs_tmax_mean | 0.05782907456159592 |
| temp | 0.053098104894161224 |
| prec | 0.05201662331819534 |
| gs_aridity | 0.05173157900571823 |
| gs_srad | 0.05131661519408226 |
| gs_pet | 0.05083774775266647 |
