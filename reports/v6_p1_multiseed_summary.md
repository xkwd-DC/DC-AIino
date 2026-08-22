# v6 P1 多种子稳健性与省特征消融汇总(2026-08-22)

三模型 × 5 种子(42–46),LCO 10 折按县分组;同面板同 split,模型/折划分随 seed 变化。
官方口径:seed 42。所有报告、fold/seed 明细见同目录 `v6_*_report.md` / `*_seed_results.csv`。

## 汇总表(LCO R², 均值±std)

| 模型配置 | 特征数 | SPEI 粒度 | LCO R² | 时间外推 R² |
|---|---:|---:|---:|---:|
| XGB 全特征(官方) | 14 | 省级 | **0.6604**(seed42) | -0.85 |
| XGB 消融 县级特征 | 4 | —(省级 SPEI 剔除) | 0.5470 ± 0.0023 | **+0.368 ± 0.009** |
| XGB 消融 县级特征 | 6 | 县级 | 0.5760 ± 0.0028 | **+0.319 ± 0.011** |
| LSTM 全特征 | 14 | 县级 | 0.0755 ± 0.0206(seed42: 0.0706) | -1.37 ± 0.26 |
| ATT 全特征 | 14 | 县级 | 0.0452 ± 0.0231(seed42: 0.0363) | -0.90 ± 0.93 |

参考:v6 首轮(省级 SPEI,seed42)LSTM +0.0488 / ATT +0.0412;XGB 全特征县级 SPEI 0.6625(单 seed)。

## 关键结论

1. **省级共享特征贡献有限**:10 个省-年常量特征重要性合计 ~73%,剔除后 XGB LCO R² 仅降 0.66→0.55(±0.002,极稳)。县级气候 + 播种面积本身解释 ~55–58% 方差。
2. **县级特征模型时间外推转正**:XGB 全特征时间外推 -0.85 → 消融后 **+0.32~0.37**。负 R² 源于省级共享特征(省-年常量)携带训练期时间趋势、无法外推;县级气候因子具备真实时间信号。论文叙事建议:截面空间归因 + 已见省份因子,而非未来气候预测。
3. **县级 SPEI 边际增益 +0.029**(0.576 vs 0.547),且县级 SPEI 对 LSTM 增益显著(seed42: 0.049→0.071)。
4. **LSTM/ATT 稳健性差**:std 0.02–0.03(相对均值 40–50%),时间外推全负;对超参/种子敏感,论文建议作为对照基线,主结论以 XGB 消融为骨架。

## 复现

```
python scripts/data/v6_04_train_xgb_lco.py --ablate-prov --seeds 42,43,44,45,46
python scripts/data/v6_04_train_xgb_lco.py --ablate-prov --panel data/interim/paper_panel_v6_climate_full.parquet --seeds 42,43,44,45,46
python scripts/data/v6_05_train_lstm_lco.py --panel data/interim/paper_panel_v6_climate_full.parquet --seeds 42,43,44,45,46
python scripts/data/v6_06_train_att_lstm_lco.py --panel data/interim/paper_panel_v6_climate_full.parquet --seeds 42,43,44,45,46
```

脚本支持断点续跑(fold CSV 已有 seed 自动跳过)。
