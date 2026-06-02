import pandas as pd
import numpy as np
from pathlib import Path

PROJECT = Path('/home/slz/workspace/DC-AIino')

# Load both
v3 = pd.read_parquet(PROJECT / 'data/interim/paper_panel_v3.parquet')
df_m = pd.read_excel(PROJECT / 'data/raw/paper_panel/wang_tianshuo_original/总表.xlsx')

# Province name mapping (short → full v3 name)
# From the data: 总表 uses short names, v3 uses full names
v3_provinces = sorted(v3['province'].unique())
master_provinces = sorted(df_m['省份'].unique())
print(f"总表 provinces ({len(master_provinces)}): {master_provinces}")
print(f"v3 provinces ({len(v3_provinces)}): {v3_provinces[:5]}...")

# Merge on province + year to compare
# First create a mapping
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
unmapped = df_m[df_m['province_full'].isna()]['省份'].unique()
if len(unmapped) > 0:
    print(f"\nUNMAPPED: {unmapped}")

# Merge
merged = v3.merge(
    df_m[['province_full', '年份', '旱灾受灾面积', '水灾受灾面积', '降水量', '日照时数', '洪涝占比']],
    left_on=['province', 'year'],
    right_on=['province_full', '年份'],
    how='inner'
)
print(f"\nMerged rows: {len(merged)} / {len(v3)}")

# Compare disaster columns
print("\n=== drou_a (旱灾受灾面积) ===")
print(f"  v3 drou_a:     mean={v3['drou_a'].mean():.2f}  min={v3['drou_a'].min():.2f}  max={v3['drou_a'].max():.2f}")
print(f"  总表 旱灾:       mean={df_m['旱灾受灾面积'].mean():.2f}  min={df_m['旱灾受灾面积'].min():.2f}  max={df_m['旱灾受灾面积'].max():.2f}")
# Check if they're the same
drou_diff = (merged['drou_a'] - merged['旱灾受灾面积']).abs()
print(f"  Mean abs diff: {drou_diff.mean():.4f}  Max diff: {drou_diff.max():.4f}")
print(f"  Identical rows: {(drou_diff < 0.01).sum()} / {len(merged)}")

print("\n=== flood_a (水灾受灾面积) ===")
print(f"  v3 flood_a:    mean={v3['flood_a'].mean():.2f}  min={v3['flood_a'].min():.2f}  max={v3['flood_a'].max():.2f}")
print(f"  总表 水灾:       mean={df_m['水灾受灾面积'].mean():.2f}  min={df_m['水灾受灾面积'].min():.2f}  max={df_m['水灾受灾面积'].max():.2f}")
flood_diff = (merged['flood_a'] - merged['水灾受灾面积']).abs()
print(f"  Mean abs diff: {flood_diff.mean():.4f}  Max diff: {flood_diff.max():.4f}")
print(f"  Identical rows: {(flood_diff < 0.01).sum()} / {len(merged)}")

# Compare SPEI-derived proxy vs real
# v3 flood = max(0, SPEI * 30)
print("\n=== SPEI proxy check ===")
merged['flood_spei_proxy'] = np.maximum(0, merged['spei'] * 30)
corr = merged['flood_spei_proxy'].corr(merged['水灾受灾面积'])
print(f"  Corr(SPEI×30 proxy, 水灾受灾面积real): {corr:.4f}")
corr2 = merged['flood_a'].corr(merged['水灾受灾面积'])
print(f"  Corr(v3 flood_a, 水灾受灾面积real): {corr2:.4f}")

# Check prec / sun
print("\n=== prec (降水量) ===")
print(f"  v3 prec:       mean={v3['prec'].mean():.2f}  min={v3['prec'].min():.2f}  max={v3['prec'].max():.2f}")
print(f"  总表 降水量:     mean={df_m['降水量'].mean():.2f}  min={df_m['降水量'].min():.2f}  max={df_m['降水量'].max():.2f}")

print("\n=== sun (日照时数) ===")
# v3 sun
v3_sun = v3['sun']
print(f"  v3 sun:        mean={v3_sun.mean():.2f}  min={v3_sun.min():.2f}  max={v3_sun.max():.2f}")
print(f"  总表 日照时数:   mean={df_m['日照时数'].mean():.2f}  min={df_m['日照时数'].min():.2f}  max={df_m['日照时数'].max():.2f}")
