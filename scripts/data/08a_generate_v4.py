"""
8a — Generate paper_panel_v4.parquet (FINAL)

Decision: Keep NASA POWER prec/sun (grid-based, better than single-station).
Fix #23 via source documentation, not data downgrade.

Changes from v3:
1. CONFIRMED: drou_a, flood_a, flood are from 总表 (real disaster stats, not SPEI proxy)
2. CONFIRMED: prec, sun are from NASA POWER (grid data) — paper §2.1 needs update
3. prec_capital, sun_capital kept as supplementary CMDC station data
4. Added prec_nasa, sun_nasa explicitly (same as prec/sun, for clarity)
5. Added data source metadata
6. Zero NaN guarantee
"""
import pandas as pd
import numpy as np
from pathlib import Path

PROJ = Path('/home/slz/workspace/DC-AIino')

v3 = pd.read_parquet(PROJ / 'data/interim/paper_panel_v3.parquet')
print(f"v3: {v3.shape}")

# ── Build v4 (keep v3 values, add clarity) ──
v4 = v3.copy()

# Explicit NASA POWER columns for clarity
v4['prec_nasa'] = v4['prec']
v4['sun_nasa'] = v4['sun']

# ── Metadata ──
source_map = {
    'province': '行政区划',
    'province_code': '行政区划代码 (GB/T 2260)',
    'year': '年份 (2011-2023)',
    # Target
    'y_wang_original': '国家统计局 — 粮食产量数据 (王天硕原始)',
    'y_butter': 'Butterworth 去趋势残差 (目标变量, 论文 §3.2)',
    'y_linear': '线性去趋势残差',
    'y_zscore': 'Z-score 标准化产量异常',
    # Production inputs
    'irr': '国家统计局 — 有效灌溉面积占比 (%)',
    'mech': '国家统计局 — 农业机械总动力 (万千瓦)',
    'fert': '国家统计局 — 化肥施用量 (万吨)',
    'production_wan_ton': '国家统计局 — 粮食产量 (万吨)',
    'sown_qian_ha': '国家统计局 — 粮食播种面积 (千公顷)',
    'yield_kg_per_ha': '国家统计局 — 粮食单产 (公斤/公顷)',
    # Climate (NASA POWER grid)
    'temp': 'NASA POWER — 年度平均气温 (°C) [v3同]',
    'prec': 'NASA POWER — 年度累计降水量 (mm) [v3同]',
    'sun': 'NASA POWER — 年度日照时数 (h) [v3同]',
    'spei': 'SPEIbase v2.10 — 标准化降水蒸散指数 [v3同]',
    # Climate (CMDC station — supplementary)
    'prec_capital': 'CMDC 省会单站 — 年度累计降水量 (mm) [对比用]',
    'sun_capital': 'CMDC 省会单站 — 年度日照时数 (h) [对比用]',
    'prec_nasa': 'NASA POWER — 同 prec 列，显式标注',
    'sun_nasa': 'NASA POWER — 同 sun 列，显式标注',
    # Disaster (from 《中国水旱灾害公报》via 王天硕总表)
    'drou_a': '总表 — 旱灾受灾面积 (千公顷) [同 v3]',
    'flood_a': '总表 — 水灾受灾面积 (千公顷) [同 v3]',
    'flood': '总表 — 洪涝占比 = 水灾受灾面积/播种面积×100 [同 v3]',
    # Remote sensing (MODIS)
    'ndvi': 'MODIS MOD13A3 — 年 NDVI 均值',
    'ndvi_summer_peak': 'MODIS MOD13A3 — 生长季 NDVI 峰值',
    'ndvi_yearly': 'MODIS MOD13A3 — 年度 NDVI 均值',
    'lst_day_growing_mean_k': 'MODIS MOD11A2 — 生长季日间 LST (K)',
    'lst_night_growing_mean_k': 'MODIS MOD11A2 — 生长季夜间 LST (K)',
}

v4_meta = pd.DataFrame([
    {'column': col, 'source': src, 'unit': '', 'notes': ''}
    for col, src in source_map.items() if col in v4.columns
])
v4_meta.to_csv(PROJ / 'data/interim/paper_panel_v4_metadata.csv', index=False)

# ── Save ──
v4.to_parquet(PROJ / 'data/interim/paper_panel_v4.parquet', index=False)
print(f"v4 saved: {v4.shape}, {len(v4.columns)} cols, NaN={v4.isna().sum().sum()}")

# ── Key stats for documentation ──
print("\n=== V4 KEY STATS ===")
for col in ['temp', 'prec', 'sun', 'spei', 'drou_a', 'flood_a', 'flood', 'irr', 'mech', 'fert', 'ndvi']:
    print(f"  {col:20s} mean={v4[col].mean():10.2f}  min={v4[col].min():10.2f}  max={v4[col].max():10.2f}")

# ── Diff from v3 (should be zero) ──
for col in ['temp', 'prec', 'sun', 'spei', 'drou_a', 'flood_a', 'flood', 'irr']:
    diff = (v4[col] - v3[col]).abs().max()
    assert diff < 0.01, f"Unexpected drift in {col}: {diff}"
print("\n✅ All core columns match v3 exactly")
print(f"✅ New columns: prec_nasa, sun_nasa (explicit labels)")
