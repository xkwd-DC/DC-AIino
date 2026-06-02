"""
v4 sanity check: compare with paper table 2 + v3
"""
import pandas as pd
import numpy as np
from pathlib import Path

PROJ = Path('/home/slz/workspace/DC-AIino')

v3 = pd.read_parquet(PROJ / 'data/interim/paper_panel_v3.parquet')
v4 = pd.read_parquet(PROJ / 'data/interim/paper_panel_v4.parquet')

# Paper Table 2 reference values
paper_table = {
    'temp': 14.0,      # 平均气温
    'prec': 754.516,   # 降水量
    'sun': 2085.928,   # 日照时数
    'spei': -0.077,    # SPEI
    'flood': 2.970,    # 洪涝占比
    'drou_a': 323.095, # 旱灾受灾面积
    'flood_a': 185.076, # 水灾受灾面积 (paper 185.076 vs v3 285)
    'irr': 56.693,     # 灌溉率
    'mech': 0.704,     # 农机
    'fertilizer': 180.937, # 化肥
    'ndvi': 0.558,     # NDVI
}

print("=" * 80)
print("V4 vs PAPER TABLE 2 vs V3 COMPARISON")
print("=" * 80)
print(f"\n{'Column':<20s} {'Paper':>12s} {'v3':>12s} {'v4':>12s} {'v3Δpaper':>10s} {'v4Δpaper':>10s}")
print("-" * 80)

# Map v4 column names to paper names
comparisons = [
    ('temp', 'temp', '平均气温'),
    ('prec', 'prec', '降水量'),
    ('sun', 'sun', '日照时数'),
    ('spei', 'spei', 'SPEI'),
    ('flood', 'flood', '洪涝占比'),
    ('drou_a', 'drou_a', '旱灾受灾面积'),
    ('flood_a', 'flood_a', '水灾受灾面积'),
    ('irr', 'irr', '灌溉率'),
    ('mech', 'mech', '农机'),
    ('fert', 'fertilizer', '化肥'),
    ('ndvi', 'ndvi', 'NDVI'),
]

for col_v4, col_paper, label in comparisons:
    paper_val = paper_table.get(col_paper)
    if paper_val is None:
        continue
    
    v3_mean = v3[col_v4].mean()
    v4_mean = v4[col_v4].mean()
    
    v3_delta = (v3_mean - paper_val) / paper_val * 100 if paper_val != 0 else 0
    v4_delta = (v4_mean - paper_val) / paper_val * 100 if paper_val != 0 else 0
    
    v3_str = f"{v3_mean:>12.2f}"
    v4_str = f"{v4_mean:>12.2f}"
    paper_str = f"{paper_val:>12.3f}"
    d3_str = f"{v3_delta:>+9.1f}%"
    d4_str = f"{v4_delta:>+9.1f}%"
    
    # Flag large deltas
    flag = ""
    if abs(v4_delta) > 10:
        flag = " ⚠️ LARGE DRIFT"
    elif abs(v4_delta) > 5:
        flag = " ⚡ minor"
    
    print(f"{label:<20s} {paper_str} {v3_str} {v4_str} {d3_str} {d4_str}{flag}")

# ── Full describe ──
print("\n" + "=" * 80)
print("V4 FULL DESCRIBE")
print("=" * 80)

desc_cols = ['temp', 'prec', 'sun', 'spei', 'flood', 'drou_a', 'flood_a', 
             'irr', 'mech', 'fert', 'ndvi', 'y_butter']
print(v4[desc_cols].describe().round(2).to_string())

# ── Save describe for documentation ──
v4[desc_cols].describe().round(2).to_csv(PROJ / 'data/interim/v4_describe.csv')

# ── Check schema compatibility with v3 ──
v3_cols = set(v3.columns)
v4_cols = set(v4.columns)
new_cols = v4_cols - v3_cols
lost_cols = v3_cols - v4_cols
print(f"\nNew columns in v4: {new_cols}")
print(f"Columns lost from v3: {lost_cols}")
print(f"Common columns: {len(v3_cols & v4_cols)}")

# ── province_code check ──
print(f"\nProvince codes consistent: {'province_code' in v4.columns}")
print(f"Provinces: {sorted(v4['province'].unique())}")
print(f"Years: {sorted(v4['year'].unique())}")
