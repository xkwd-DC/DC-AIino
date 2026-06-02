"""
8a — 致灾因子真实化 + 单位审计
Steps: verify flood proxy, extract severe data, audit sun/prec
"""
import pandas as pd
import numpy as np
from pathlib import Path

PROJ = Path('/home/slz/workspace/DC-AIino')
BASE = PROJ / 'data/raw/paper_panel/wang_tianshuo_original'

v3 = pd.read_parquet(PROJ / 'data/interim/paper_panel_v3.parquet')

# ═══ STEP 1: Confirm flood = SPEI proxy ═══
print("=" * 60)
print("STEP 1: Verify 'flood' column is SPEI proxy")
v3_work = v3.copy()
v3_work['flood_from_spei'] = np.maximum(0, v3_work['spei'] * 30)
diff = (v3_work['flood'] - v3_work['flood_from_spei']).abs()
print(f"flood = max(0, SPEI×30)?")
print(f"  Mean abs diff: {diff.mean():.6f}  Max diff: {diff.max():.6f}")
print(f"  Identical: {(diff < 0.001).sum()} / {len(v3)}")
print(f"  Corr: {v3_work['flood'].corr(v3_work['flood_from_spei']):.6f}")

# Also check: is flood just a scaled version of flood_a?
corr_fa = v3_work['flood'].corr(v3_work['flood_a'])
print(f"\n  flood vs flood_a corr: {corr_fa:.4f}")
print(f"  Sample rows:")
print(v3_work[['province','year','spei','flood','flood_a','flood_from_spei']].head(6).to_string())

# Is flood the same as 洪涝占比?
df_m = pd.read_excel(BASE / '总表.xlsx')
name_map = {
    '北京': '北京市', '天津': '天津市', '上海': '上海市', '重庆': '重庆市',
    '河北': '河北省', '山西': '山西省', '辽宁': '辽宁省', '吉林': '吉林省',
    '黑龙江': '黑龙江省', '江苏': '江苏省', '浙江': '浙江省', '安徽': '安徽省',
    '福建': '福建省', '江西': '江西省', '山东': '山东省', '河南': '河南省',
    '湖北': '湖北省', '湖南': '湖南省', '广东': '广东省', '海南': '海南省',
    '四川': '四川省', '贵州': '贵州省', '云南': '云南省', '陕西': '陕西省',
    '甘肃': '甘肃省', '青海': '青海省', '台湾': '台湾省',
    '内蒙古': '内蒙古自治区', '广西': '广西壮族自治区',
    '西藏': '西藏自治区', '宁夏': '宁夏回族自治区',
    '新疆': '新疆维吾尔自治区',
}
df_m['province_full'] = df_m['省份'].map(name_map)
merged = v3.merge(
    df_m[['province_full','年份','洪涝占比']],
    left_on=['province','year'], right_on=['province_full','年份'], how='inner'
)
flood_ratio_diff = (merged['flood'] - merged['洪涝占比']).abs()
print(f"\n  flood vs 总表 洪涝占比:")
print(f"  Mean diff: {flood_ratio_diff.mean():.4f}  Max diff: {flood_ratio_diff.max():.4f}")
print(f"  Identical: {(flood_ratio_diff < 0.01).sum()} / {len(merged)}")

# ═══ STEP 2: Extract 成灾面积 ═══
print("\n" + "=" * 60)
print("STEP 2: Extract severe affected area (成灾面积)")

df_severe = pd.read_excel(BASE / '分省年度成灾数据 (5).xlsx', header=None)
print(f"Raw shape: {df_severe.shape}")
print("First 5 rows:")
for j in range(min(5, len(df_severe))):
    print(f"  Row {j}: {[str(x)[:40] for x in df_severe.iloc[j].tolist()[:12]]}")

# Parse: header is row 3, data from row 4
# Columns: 地区, 2025年, 2024年, ..., 2011年 (right to left)
# Row 0: "指标：受灾面积 (千公顷)"
# Row 1: "时间：2011年-2025年"
# Row 2: "地区" header
# Actually from earlier exploration: Row 3 is header, Row 4+ is data

# Let me parse this properly
# Row 0 = metadata, Row 1 = metadata, Row 2 = blank or metadata, Row 3 = headers
header_row = 3
# Read with proper header
df_sev = pd.read_excel(BASE / '分省年度成灾数据 (5).xlsx', header=header_row)
print(f"\nParsed shape: {df_sev.shape}")
print(f"Columns: {list(df_sev.columns)[:15]}")

# Rename first column
prov_col = df_sev.columns[0]
df_sev = df_sev.rename(columns={prov_col: '地区'})

# Drop metadata rows (row 0-3 in original become header, row 4 becomes first data row)
# Actually with header=3, the data starts from row 4 of original
# But there might still be NaN rows
df_sev = df_sev.dropna(subset=['地区'])
df_sev = df_sev[~df_sev['地区'].astype(str).str.contains('指标|时间|数据库|全国')]
df_sev = df_sev[df_sev['地区'].astype(str).str.strip() != '']

print(f"\nCleaned shape: {df_sev.shape}")
print(f"Provinces: {sorted(df_sev['地区'].unique())}")

# Year columns
year_cols = [c for c in df_sev.columns if '2011' in str(c) or '2012' in str(c) or '2013' in str(c)]
print(f"Sample year cols: {year_cols[:5]}")

# The year columns are like '2011年', '2012年', etc.
# Need to extract year number
def parse_year(col_name):
    import re
    match = re.search(r'(\d{4})', str(col_name))
    return int(match.group(1)) if match else None

year_map = {}
for c in df_sev.columns[1:]:
    y = parse_year(c)
    if y:
        year_map[c] = y

print(f"\nYear mapping ({len(year_map)} years): {sorted(year_map.values())}")

# Filter to 2011-2023
target_years = set(range(2011, 2024))
cols_keep = ['地区'] + [c for c, y in year_map.items() if y in target_years]
df_sev = df_sev[cols_keep]

# Rename columns to year numbers
rename_map = {c: str(year_map[c]) for c in cols_keep[1:]}
df_sev = df_sev.rename(columns=rename_map)

print(f"\nFinal 成灾数据 shape: {df_sev.shape}")
print(f"Columns: {list(df_sev.columns)[:15]}")
print(df_sev.head(3).to_string())
