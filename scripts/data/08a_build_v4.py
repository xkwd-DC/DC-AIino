"""
8a — Build paper_panel_v4 from v3 + real disaster data + documentation
"""
import pandas as pd
import numpy as np
from pathlib import Path
import json
from datetime import datetime

PROJ = Path('/home/slz/workspace/DC-AIino')
BASE = PROJ / 'data/raw/paper_panel/wang_tianshuo_original'

v3 = pd.read_parquet(PROJ / 'data/interim/paper_panel_v3.parquet')
print(f"v3: {v3.shape}, columns: {len(v3.columns)}")

# ═══ Build v4 ═══
v4 = v3.copy()

# ── 1. Rename flood → flood_ratio (洪涝占比) ──
v4 = v4.rename(columns={'flood': 'flood_ratio'})
print("\n1. Renamed 'flood' → 'flood_ratio' (洪涝占比, %)")

# ── 2. Extract total affected area from 成灾数据 ──
df_sev = pd.read_excel(BASE / '分省年度成灾数据 (5).xlsx', header=3)
df_sev = df_sev.rename(columns={df_sev.columns[0]: 'province'})
df_sev = df_sev.dropna(subset=['province'])
# Filter out non-province rows
import re
df_sev = df_sev[~df_sev['province'].astype(str).str.contains('指标|时间|数据库|全国|注|数据来源')]
df_sev = df_sev[df_sev['province'].astype(str).str.strip() != '']

# Parse year columns and melt
year_cols = {}
for c in df_sev.columns[1:]:
    m = re.search(r'(\d{4})', str(c))
    if m:
        year_cols[c] = int(m.group(1))

# Filter to 2011-2023
cols_keep = ['province'] + [c for c, y in year_cols.items() if 2011 <= y <= 2023]
df_sev = df_sev[cols_keep]
rename_map = {c: str(year_cols[c]) for c in cols_keep[1:]}
df_sev = df_sev.rename(columns=rename_map)

# Melt to long format
df_sev_long = df_sev.melt(
    id_vars=['province'],
    var_name='year',
    value_name='affected_area_total'
)
df_sev_long['year'] = df_sev_long['year'].astype(int)
df_sev_long['affected_area_total'] = pd.to_numeric(df_sev_long['affected_area_total'], errors='coerce')

# Merge with v4
v4 = v4.merge(
    df_sev_long[['province', 'year', 'affected_area_total']],
    on=['province', 'year'],
    how='left'
)
print(f"2. Added 'affected_area_total' (总受灾面积): NaN={v4['affected_area_total'].isna().sum()}")

# Verify: affected_area_total ≈ drou_a + flood_a
v4['_check'] = (v4['drou_a'] + v4['flood_a'] - v4['affected_area_total']).abs()
print(f"   drou_a + flood_a vs total: mean_diff={v4['_check'].mean():.2f} max_diff={v4['_check'].max():.2f}")
v4 = v4.drop(columns=['_check'])

# ── 3. Add data source documentation columns ──
# Note: these are for future reference, not model input
print(f"\n3. Column documentation:")
print(f"   drou_a: 旱灾受灾面积(千公顷) — 国家统计局/王天硕总表 (already REAL in v3)")
print(f"   flood_a: 水灾受灾面积(千公顷) — 国家统计局/王天硕总表 (already REAL in v3)")
print(f"   flood_ratio: 洪涝占比(%) — 王天硕总表 (renamed from 'flood')")
print(f"   affected_area_total: 总受灾面积(千公顷) — 国家统计局分省年度数据")
print(f"   prec: 降水量(mm) — NASA POWER (省域网格), NOT CMDC省会单站")
print(f"   sun: 日照时数(h) — NASA POWER (省域网格), NOT CMDC省会单站")
print(f"   prec_capital: 降水量(mm) — CMDC省会单站 (王天硕xlsx, kept for reference)")
print(f"   sun_capital: 日照时数(h) — CMDC省会单站 (王天硕xlsx, kept for reference)")

# ── 4. Sanity checks ──
print(f"\n4. Sanity checks:")
print(f"   Shape: {v4.shape}")
print(f"   Total NaN: {v4.isna().sum().sum()}")
print(f"   Columns: {list(v4.columns)}")

# ── 5. Save v4 ──
out = PROJ / 'data/interim/paper_panel_v4.parquet'
v4.to_parquet(out)
print(f"\n5. Saved: {out}")

# ── 6. Generate diff report ──
print(f"\n6. v3 vs v4 diff report:")
print(f"   v3 shape: {v3.shape}  v4 shape: {v4.shape}")
common_cols = set(v3.columns) & set(v4.columns)
for c in sorted(common_cols):
    if c in ('province', 'year', 'province_code'):
        continue
    v3_m = v3[c].mean()
    v4_m = v4[c].mean()
    if abs(v3_m - v4_m) > 0.001:
        print(f"   {c:25s}: v3={v3_m:12.4f}  v4={v4_m:12.4f}  diff={abs(v3_m-v4_m):.4f}")

new_cols = set(v4.columns) - set(v3.columns)
print(f"\n   New columns: {sorted(new_cols)}")
removed_cols = set(v3.columns) - set(v4.columns)
print(f"   Renamed/removed: {sorted(removed_cols)}")
