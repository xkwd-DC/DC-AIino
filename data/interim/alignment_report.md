# 时空对齐报告（任务 1.7）

**状态**：✅ PASS（要求 ≥ 95%）
**论文 panel 行数**：403（31 × 13 = 403）
**MODIS 年度 panel 行数**：403（31 × 13 = 403）
**合并后含 NDVI 的行数**：403
**对齐准确率**：100.0%

## 合并 key
- `province_code` (民政部 6 位)
- `year`

## NDVI 列定义
- `ndvi`：生长季（4-10 月）月度 NDVI 均值 — 与作物物候对齐，**作为 11 维特征的 NDVI 列**
- `ndvi_summer_peak`：生长季月度 NDVI 最大值（次要参考）
- `ndvi_yearly`：全年 12 月均值（含冬季低值，参考用）
- `lst_day_growing_mean_k` / `lst_night_growing_mean_k`：生长季 LST 均值（**不进 11 维**，可选研究列）

## 缺失分析

### 论文有但 MODIS 缺
无

### MODIS 有但论文缺
无

## 下游使用
- 熊鑫训练：直接 `pd.read_parquet("data/interim/paper_panel_v1.parquet")`，11 维 X + Y 都齐
- 标准化（1.8 task）：归熊鑫，用 sklearn StandardScaler，scaler.pkl 存 backend/models/
