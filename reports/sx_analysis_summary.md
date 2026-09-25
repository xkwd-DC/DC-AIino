# 山西县极端气候-粮食因子分析摘要

样本 1241 县域年, 115 县, 2012-2023

## 气候归因(cluster县)
                      coef       se       p        t
const            -194.8130  26.5326  0.0000  -7.3424
gs_mean_tmax        0.0268   0.0195  0.1685   1.3771
spei3_growing       0.1173   0.0395  0.0030   2.9675
heat_jja            0.0000   0.0000  0.0000   7.3425
cdd_max            -0.0046   0.0043  0.2938  -1.0498
rainstorm_days     -0.0252   0.0232  0.2771  -1.0869
dry_hot_wind        0.0000   0.0000  0.0000   7.3418
autumn_rain_days    0.0042   0.0079  0.5928   0.5348
log_mach            1.0553   0.0777  0.0000  13.5732
year                0.1006   0.0131  0.0000   7.6709

## 异质性 高温×高海拔
                coef      se       p        t
gs_mean_tmax  0.0394  0.0432  0.3608   0.9139
high_elev    -0.0746  1.3764  0.9568  -0.0542
tmax_x_he     0.0139  0.0535  0.7945   0.2605
log_mach      1.1410  0.0730  0.0000  15.6277
const         6.6007  1.0529  0.0000   6.2689

## XGBoost-SHAP
LCO R2=0.6891 | 时间外推 R2=0.7984
log_mach            0.6300
gs_mean_tmax        0.1579
spei3_growing       0.1117
autumn_rain_days    0.0898
cdd_max             0.0840
rainstorm_days      0.0134
heat_jja            0.0000
dry_hot_wind        0.0000
