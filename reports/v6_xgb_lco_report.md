# v6 XGBoost Leave-County-Out 报告（首轮 sanity）

- 样本: 10407 行（1041 县 × 2012–2022 非平衡面板，10 主产省；385 县缺 1–10 年，2023 年产量缺失）
- 目标: log_yield = log(粮食总产量_吨)
- 特征 (14): temp, prec, sun, spei_annual_mean, spei_growing_season_mean, ndvi_yearly, lst_day_growing_mean_k, fert, irr, flood, drou_a, flood_a, cropland_ratio, log_sown
- LCO overall R² = **+0.6604** (RMSE 0.8105)
- 时间外推 R² (≤2019 → 2020-22，2023 年产量缺失) = **-0.8537** (RMSE 1.9332)

## 各折结果

|   fold |   n_train |   n_test |     r2 |   rmse |
|-------:|----------:|---------:|-------:|-------:|
|      1 |      9344 |     1063 | 0.6846 | 0.7544 |
|      2 |      9381 |     1026 | 0.6131 | 0.9045 |
|      3 |      9354 |     1053 | 0.6558 | 0.8578 |
|      4 |      9371 |     1036 | 0.5291 | 0.9354 |
|      5 |      9368 |     1039 | 0.6898 | 0.7124 |
|      6 |      9370 |     1037 | 0.6311 | 0.9556 |
|      7 |      9350 |     1057 | 0.6834 | 0.6836 |
|      8 |      9384 |     1023 | 0.7225 | 0.6178 |
|      9 |      9365 |     1042 | 0.6587 | 0.8806 |
|     10 |      9376 |     1031 | 0.7486 | 0.7266 |

## 特征重要性（时间模型）

| feature                  |   importance |
|:-------------------------|-------------:|
| cropland_ratio           |    0.224234  |
| log_sown                 |    0.187686  |
| flood_a                  |    0.148881  |
| drou_a                   |    0.121806  |
| irr                      |    0.0503646 |
| ndvi_yearly              |    0.0498612 |
| lst_day_growing_mean_k   |    0.0420947 |
| temp                     |    0.0367632 |
| fert                     |    0.0356276 |
| prec                     |    0.0237573 |
| sun                      |    0.0219965 |
| flood                    |    0.0203447 |
| spei_growing_season_mean |    0.0191141 |
| spei_annual_mean         |    0.0174691 |

## 对比

| 版本 | CV | R² |
|---|---|---|
| v4 省级 (XGBoost-SHAP) | random 8:2 | 0.9072 |
| v4 省级 (XGBoost-SHAP) | leave-province-out（真实 LPO） | -16.83（中位） |
| v5 地级市 | 城市级 LPO | 0.213 |
| v6 县级 (本报告) | LCO | +0.6604 |
