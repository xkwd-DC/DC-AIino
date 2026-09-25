# v6_13 县级气候迁移能力 — 三重防挨打验证

> 数据: paper_panel_v7_prediction.parquet | 目标: log_yield（总产量）/ log(yield_ton_per_ha)（单产）
> null 采用**逐列 permutation**（保持边际分布、破坏特征-产量关联），折固定 seed 42，次数=30
> bootstrap 跨县重采样 × 多种子，次数=80; 显著性以 P(Δ≤0) 与 95%CI 报告

## 一、Null model（permutation 阴性对照）

真实 LCO R² vs 打乱后的 null LCO R²：

| config | n_feat | true_mean | true_std | null_mean | null_sd | null_max | excess_true_over_null | frac_true_gt_null | q05 | q95 |
|---|---|---|---|---|---|---|---|---|---|---|
| CLIM3 | 3 | 0.26 | 0.004 | -0.0142 | 0.0022 | -0.0094 | 0.2743 | 1.0 | -0.0177 | -0.0108 |
| CLIM5 | 5 | 0.3241 | 0.0054 | -0.0153 | 0.0023 | -0.0105 | 0.3393 | 1.0 | -0.0192 | -0.0119 |
| CLIMG | 16 | 0.4489 | 0.0058 | -0.0157 | 0.0022 | -0.0113 | 0.4646 | 1.0 | -0.0199 | -0.0129 |

- **判读**：若 `excess_true_over_null` 大（真实远高于 null），说明 R² 是**气候信号**；
  若真实≈null（excess≈0），说明前面的 R² 是**结构性/特征数假象**。
- `frac_true_gt_null`= 真实 R² 超过 null 分布的比例（近似可信度）。

## 二、单产目标（剥离面积）——log(yield_ton_per_ha)

单产 = 总产量/播种面积（本面板比值恒=1.0，故 log(单产)=log_yield−log(面积)，天然剥离规模）：

| config | n_feat | n_rows | n_county | lco_r2 | lco_std | null_lco_r2 | excess |
|---|---|---|---|---|---|---|---|
| CLIM3 | 3 | 4693 | 627 | 0.3505 | 0.0064 | -0.0282 | 0.3787 |
| CLIM5 | 5 | 4693 | 627 | 0.4397 | 0.0062 | -0.0292 | 0.4689 |
| CLIMG | 16 | 4693 | 627 | 0.5208 | 0.0065 | -0.0336 | 0.5544 |

> ⚠️ 单产非空样本只有 4703 行 / 629 县（覆盖 60%），且 2020-22 每年仅 ~200 县/年，
> **时间外推样本过小会误导**，因此此处**只报 LCO**。与 log_yield 的 LCO 对比即「剥离规模」后的附录证据。

## 三、Bootstrap 显著性（CLIM3 → CLIMG 提升）

| pair | n_boot | n_common | delta_point | delta_boot_mean | ci_lo | ci_hi | p_delta_le_0 |
|---|---|---|---|---|---|---|---|
| CLIM3->CLIMG | 80 | 10407 | 0.1888 | 0.1571 | 0.1241 | 0.1848 | 0.0 |

- 若 `ci_lo > 0` 且 `p_delta_le_0 < 0.05`：提升**显著**，不是种子抖动。
- 样本为 CLIM3/CLIMG 共同县×年份（配对公平），跨县 bootstrap 平滑随机性。

---

> 复现: `python scripts/data/v6_13_null_and_significance.py --configs CLIM3,CLIM5,CLIMG --seeds 42,43,44,45,46 --n-perm 30 --n-boot 80`
