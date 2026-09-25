# 县级气候变量的可迁移产量解释能力 — 隔离实验报告

> 数据: paper_panel_v7_prediction.parquet | 目标: log_yield = log(粮食总产量_吨)
> 协议: LCO 10 折按县分组 + 时间外推(≤2019 → 之后); 种子 42, 43, 44, 45, 46
> 混淆控制: 所有 CLIM* 配置均**不含** 播种面积/规模(log_sown) 与 省-年共享常量;
  `CLIMG+S`/`CLIMG+P` 仅为对照，用于曝露「规模/省常量」在背解释力。

## 产量口径诊断（为什么必须隔离）

log_yield 是被「规模(播种面积)」主导的总量指标，若直接报「气候解释力」会失真：

- 样本(n=有单产): 4703，log_yield 方差 = 1.7911
- log_yield 与 log(播种面积) 相关 = 0.9597；与 log(单产) 相关 = 0.5452
- 播种面积(log) 对 log_yield 方差的**解释份额 ≈ 92%**

## 迁移能力汇总（mean ± std，5 种子）

| config | n_feat | lco_r2 | time_r2 |
|---|---|---|---|
| CLIM3 | 3 | +0.2600 ± 0.0044 | +0.2216 ± 0.0024 |
| CLIM5 | 5 | +0.3241 ± 0.0060 | +0.2366 ± 0.0044 |
| CLIMG | 16 | +0.4489 ± 0.0065 | +0.3644 ± 0.0044 |
| CLIMG+S | 17 | +0.6465 ± 0.0046 | +0.4530 ± 0.0050 |
| CLIMG+P | 26 | +0.4736 ± 0.0074 | +0.3848 ± 0.0092 |

| 配置 | 含义 |
|---|---|
| CLIM3 | 纯县级气候 3 维（temp/prec/sun），无规模、无省常量 |
| CLIM5 | + 县级 SPEI ×2 |
| CLIMG | + 生长季/极端指数（gs_*/gdd10/gs_aridity） |
| CLIMG+S | CLIMG + 播种面积（规模）——曝露规模在背解释力 |
| CLIMG+P | CLIMG + 省-年共享常量——原「官方」口径 |

> 判读：**LCO R²** = 跨县空间迁移（能否解释未见县）；**时间外推 R²** = 跨时间迁移（能否解释未来年）。
> 若纯气候 CLIM* 的 LCO/time 显著为正，则县级气候变量**具备**可迁移解释能力；
> 若 CLIMG+S/P 比 CLIMG 高很多，说明**表面上**的「气候解释力」实际由规模/省常量承担。

## 气候特征 SHAP 方向一致性（seed 42 时间模型，train≤2019 vs test>2019）

同一气候特征在训练期(过去)与测试期(未来)的 SHAP 均值符号是否一致：
- `same_sign=True` 且为气候主效应：该特征的**解释方向可跨时间迁移**（如「降水↑→产量↑」在未来仍成立）；
- `same_sign=False` 或出现翻转：跨时间解释方向不稳定，需谨慎表述。

| config | feature | train_shap | test_shap | same_sign |
|---|---|---|---|---|
| CLIM3 | temp | 0.0264 | -0.0409 | False |
| CLIM3 | prec | -0.0253 | -0.0264 | True |
| CLIM3 | sun | 0.0183 | -0.0417 | False |
| CLIM5 | temp | 0.0556 | -0.0212 | False |
| CLIM5 | prec | -0.0084 | -0.0225 | True |
| CLIM5 | sun | -0.0163 | -0.0855 | True |
| CLIM5 | spei_annual_mean | 0.0072 | -0.0006 | False |
| CLIM5 | spei_growing_season_mean | -0.0268 | 0.0275 | False |
| CLIMG | temp | 0.0373 | 0.0123 | True |
| CLIMG | prec | -0.0029 | 0.0057 | False |
| CLIMG | sun | 0.017 | -0.0065 | False |
| CLIMG | spei_annual_mean | 0.0094 | 0.0234 | True |
| CLIMG | spei_growing_season_mean | -0.012 | 0.0064 | False |
| CLIMG | gs_tmax_mean | -0.037 | -0.0506 | True |
| CLIMG | gs_tmin_mean | 0.0261 | 0.0085 | True |
| CLIMG | gs_ppt | -0.0062 | -0.0089 | True |
| CLIMG | gs_srad | -0.0065 | -0.0128 | True |
| CLIMG | gs_pet | 0.0302 | 0.029 | True |
| CLIMG | gdd10 | -0.0362 | -0.0594 | True |
| CLIMG | gs_aridity | -0.0001 | 0.0028 | False |
| CLIMG | prec_cv | 0.0055 | 0.0166 | True |
| CLIMG | gs_prec_share | -0.0363 | -0.062 | True |
| CLIMG | winter_temp | 0.0139 | -0.003 | False |
| CLIMG | seasonal_temp_range | 0.011 | -0.0107 | False |
| CLIMG+S | temp | 0.0051 | -0.0128 | False |
| CLIMG+S | prec | -0.0323 | -0.0234 | True |
| CLIMG+S | sun | 0.0062 | -0.0083 | False |
| CLIMG+S | spei_annual_mean | 0.0042 | 0.008 | True |
| CLIMG+S | spei_growing_season_mean | -0.0097 | 0.0144 | False |
| CLIMG+S | gs_tmax_mean | -0.0198 | -0.0231 | True |
| CLIMG+S | gs_tmin_mean | -0.0188 | -0.0367 | True |
| CLIMG+S | gs_ppt | -0.0095 | -0.0125 | True |
| CLIMG+S | gs_srad | 0.0086 | 0.0 | True |
| CLIMG+S | gs_pet | 0.0443 | 0.0543 | True |
| CLIMG+S | gdd10 | 0.0016 | -0.0172 | False |
| CLIMG+S | gs_aridity | -0.0095 | -0.0072 | True |
| CLIMG+S | prec_cv | 0.0201 | 0.0387 | True |
| CLIMG+S | gs_prec_share | -0.0119 | -0.0232 | True |
| CLIMG+S | winter_temp | -0.0084 | -0.0114 | True |
| CLIMG+S | seasonal_temp_range | 0.0275 | 0.0312 | True |
| CLIMG+S | log_sown | 0.0219 | -0.0721 | False |
| CLIMG+P | temp | -0.0159 | -0.0348 | True |
| CLIMG+P | prec | -0.0148 | -0.0132 | True |
| CLIMG+P | sun | 0.0145 | -0.0034 | False |
| CLIMG+P | spei_annual_mean | 0.0026 | 0.0249 | True |
| CLIMG+P | spei_growing_season_mean | -0.0018 | 0.0142 | False |
| CLIMG+P | gs_tmax_mean | -0.015 | -0.0255 | True |
| CLIMG+P | gs_tmin_mean | 0.0232 | 0.0035 | True |
| CLIMG+P | gs_ppt | -0.0014 | -0.0098 | True |
| CLIMG+P | gs_srad | 0.0049 | -0.0045 | False |
| CLIMG+P | gs_pet | 0.0356 | 0.0401 | True |
| CLIMG+P | gdd10 | -0.0317 | -0.0508 | True |
| CLIMG+P | gs_aridity | 0.005 | 0.0058 | True |
| CLIMG+P | prec_cv | 0.0084 | 0.0252 | True |
| CLIMG+P | gs_prec_share | -0.0184 | -0.0465 | True |
| CLIMG+P | winter_temp | -0.0244 | -0.031 | True |
| CLIMG+P | seasonal_temp_range | -0.0054 | -0.0219 | True |
| CLIMG+P | ndvi_yearly | -0.0132 | 0.0102 | False |
| CLIMG+P | ndvi_summer_peak | 0.0139 | 0.0134 | True |
| CLIMG+P | lst_day_growing_mean_k | 0.0093 | 0.0207 | True |
| CLIMG+P | lst_night_growing_mean_k | 0.0002 | 0.003 | True |
| CLIMG+P | fert | 0.0002 | -0.0073 | False |
| CLIMG+P | irr | 0.0053 | 0.0032 | True |
| CLIMG+P | flood | -0.0026 | -0.0103 | True |
| CLIMG+P | drou_a | -0.0027 | -0.03 | True |
| CLIMG+P | flood_a | 0.0223 | -0.0158 | False |
| CLIMG+P | cropland_ratio | 0.0148 | -0.0256 | False |

---

> 复现: `python scripts/data/v6_12_climate_transfer.py --configs CLIM3,CLIM5,CLIMG,CLIMG+S,CLIMG+P --seeds 42,43,44,45,46`
