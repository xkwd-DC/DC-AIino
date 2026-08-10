# Experiment Card — XGBoost 异常预测 leave-province-out

## 实验信息
- 日期: 2026-07-05 15:47:01
- 数据: data\interim\paper_panel_v3.parquet (N=403, 31省×13年)
- 特征: 11维 — irr, flood, sun, temp, spei, prec, mech, fert, drou_a, flood_a, ndvi
- 超参: `{"learning_rate": 0.1, "max_depth": 6, "n_estimators": 150, "objective": "reg:squarederror"}`
- 验证: leave-province-out (31折)

## 诊断背景

原始模型 (train_xgb_baseline.py) 在随机 8:2 切分下 R^2=0.907，
但 leave-province-out 预期 R^2≈-16.83。根因：

1. Target = yield_kg_per_ha (绝对产量) → 模型学省份产量基准
2. 特征 irr/mech/fert 等 = 省份身份代理变量 → 识别省份即可高分
3. 随机切分时同省样本泄漏到训练集 → 过拟合被 R^2 掩盖

## 三组对比

| 配置 | Target | 特征 | Pooled R^2 | Median R^2 | Mean R^2 ± Std |
|---|---|---|---|---|---|
| A. 现状复现 | yield_kg_per_ha (绝对产量) | 原始 (全局标准化) | +0.0977 | -16.8345 | -176.8508 ± 712.2974 |
| B. 异常值-省均值 | yield - province_mean | 省内 z-score | -0.2194 | -0.3911 | -1.7214 ± 2.7383 |
| C. 异常值-省线性趋势 | yield - province_linear_trend | 省内 z-score | -0.1700 | -0.1208 | -1.4976 ± 5.8588 |

## 结论

去省份基准后 R^2 仍为负 (B: -0.2194, C: -0.1700)。
说明 N=403 + 11 维特征确实不足以支撑跨省外推，需县级数据下沉。

## 详细结果
见 `xgb_anomaly_lpo_results.json`