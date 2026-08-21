# v6 XGBoost Leave-County-Out 报告（首轮 sanity）

- 样本: 10407 行 = 1041 县 × 11 年（10 主产省）
- 目标: log_yield = log(粮食总产量_吨)
- 特征 (14): temp, prec, sun, spei_annual_mean, spei_growing_season_mean, ndvi_yearly, lst_day_growing_mean_k, fert, irr, flood, drou_a, flood_a, cropland_ratio, log_sown
- LCO overall R² = **+0.6625** (RMSE 0.8080)
- 时间外推 R² (≤2019 → 2020-23) = **-0.8198** (RMSE 1.9154)

## 各折结果

|   fold |   n_train |   n_test |     r2 |   rmse |
|-------:|----------:|---------:|-------:|-------:|
|      1 |      9344 |     1063 | 0.6929 | 0.7444 |
|      2 |      9381 |     1026 | 0.6167 | 0.9002 |
|      3 |      9354 |     1053 | 0.6597 | 0.8529 |
|      4 |      9371 |     1036 | 0.5154 | 0.9489 |
|      5 |      9368 |     1039 | 0.7084 | 0.6908 |
|      6 |      9370 |     1037 | 0.6193 | 0.9708 |
|      7 |      9350 |     1057 | 0.6924 | 0.6739 |
|      8 |      9384 |     1023 | 0.7217 | 0.6187 |
|      9 |      9365 |     1042 | 0.663  | 0.875  |
|     10 |      9376 |     1031 | 0.7543 | 0.7183 |

## 特征重要性（时间模型）

| feature                  |   importance |
|:-------------------------|-------------:|
| cropland_ratio           |    0.218548  |
| log_sown                 |    0.206275  |
| flood_a                  |    0.137995  |
| drou_a                   |    0.113529  |
| ndvi_yearly              |    0.0550271 |
| irr                      |    0.0501888 |
| lst_day_growing_mean_k   |    0.040901  |
| temp                     |    0.0407627 |
| fert                     |    0.035189  |
| prec                     |    0.0267669 |
| sun                      |    0.0257462 |
| spei_growing_season_mean |    0.0193487 |
| flood                    |    0.017658  |
| spei_annual_mean         |    0.0120641 |

## 对比

| 版本 | CV | R² |
|---|---|---|
| v4 省级 (XGBoost-SHAP) | LPO | 0.9072 |
| v5 地级市 | 城市级 LPO | 0.213 |
| v6 县级 (本报告) | LCO | +0.6625 |
