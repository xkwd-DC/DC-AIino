# v6 Attention-LSTM Leave-County-Out 报告（feature-level attention gating）

- 样本: 10407 行（1041 县 × 2012–2022 非平衡面板，10 主产省；385 县缺 1–10 年，2023 年产量缺失）
- 目标: log_yield  特征 (14): temp, prec, sun, spei_annual_mean, spei_growing_season_mean, ndvi_yearly, lst_day_growing_mean_k, fert, irr, flood, drou_a, flood_a, cropland_ratio, log_sown
- 结构: Input→Reshape→Dense(softmax 软掩码)→Multiply→LSTM(64)→LSTM(32)→Dropout→Dense(1)
- LCO overall R² = **+0.0412** (RMSE 1.3618)
- 时间外推 R² (≤2019 → 2020-22，2023 年产量缺失) = **-0.5846** (RMSE 1.7874)

## 各折结果

|   fold |   n_train |   n_test |      r2 |   rmse |
|-------:|----------:|---------:|--------:|-------:|
|      1 |      9344 |     1063 |  0.0552 | 1.3057 |
|      2 |      9381 |     1026 |  0.0838 | 1.3918 |
|      3 |      9354 |     1053 | -0.0177 | 1.4749 |
|      4 |      9371 |     1036 | -0.0261 | 1.3808 |
|      5 |      9368 |     1039 |  0.0022 | 1.2778 |
|      6 |      9370 |     1037 |  0.0194 | 1.558  |
|      7 |      9350 |     1057 |  0.078  | 1.1667 |
|      8 |      9384 |     1023 |  0.1117 | 1.1053 |
|      9 |      9365 |     1042 |  0.0234 | 1.4896 |
|     10 |      9376 |     1031 |  0.0679 | 1.3992 |

## 特征 attention 权重均值（与 XGB 时间模型 gain 重要性对照，非 SHAP）

| feature                  |   att_weight |
|:-------------------------|-------------:|
| spei_annual_mean         |    0.153157  |
| prec                     |    0.120871  |
| temp                     |    0.0952048 |
| log_sown                 |    0.0890643 |
| ndvi_yearly              |    0.0814181 |
| lst_day_growing_mean_k   |    0.0793245 |
| sun                      |    0.0760423 |
| fert                     |    0.0577618 |
| irr                      |    0.0548078 |
| flood                    |    0.0449729 |
| spei_growing_season_mean |    0.0415588 |
| cropland_ratio           |    0.0411859 |
| drou_a                   |    0.0337621 |
| flood_a                  |    0.030868  |

## 对比

| 版本 | CV | R² |
|---|---|---|
| v6 XGBoost | LCO | +0.6604 |
| v6 LSTM | LCO | 见 v6_lstm_lco_report.md |
| v6 Attention-LSTM (本报告) | LCO | +0.0412 |
