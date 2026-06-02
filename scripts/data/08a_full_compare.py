"""
8a — Full v3 vs 总表 column comparison + v4 generation
"""
import pandas as pd
import numpy as np
from pathlib import Path

PROJ = Path('/home/slz/workspace/DC-AIino')
BASE = PROJ / 'data/raw/paper_panel/wang_tianshuo_original'

v3 = pd.read_parquet(PROJ / 'data/interim/paper_panel_v3.parquet')
df_m = pd.read_excel(BASE / '总表.xlsx')

name_map = {
    '北京': '北京市', '天津': '天津市', '上海': '上海市', '重庆': '重庆市',
    '河北': '河北省', '山西': '山西省', '辽宁': '辽宁省', '吉林': '吉林省',
    '黑龙江': '黑龙江省', '江苏': '江苏省', '浙江': '浙江省', '安徽': '安徽省',
    '福建': '福建省', '江西': '江西省', '山东': '山东省', '河南': '河南省',
    '湖北': '湖北省', '湖南': '湖南省', '广东': '广东省', '海南': '海南省',
    '四川': '四川省', '贵州': '贵州省', '云南': '云南省', '陕西': '陕西省',
    '甘肃': '甘肃省', '青海': '青海省',
    '内蒙古': '内蒙古自治区', '广西': '广西壮族自治区',
    '西藏': '西藏自治区', '宁夏': '宁夏回族自治区',
    '新疆': '新疆维吾尔自治区',
}
df_m['province_full'] = df_m['省份'].map(name_map)

# Merge
merged = v3.merge(
    df_m[['province_full', '年份', '旱灾受灾面积', '水灾受灾面积', '降水量', '日照时数', '洪涝占比', '平均气温', '干旱指数']],
    left_on=['province', 'year'],
    right_on=['province_full', '年份'],
    how='inner'
)

# Column mapping: v3_col → 总表_col
col_pairs = [
    ('drou_a', '旱灾受灾面积', '旱灾受灾面积'),
    ('flood_a', '水灾受灾面积', '水灾受灾面积'),
    ('flood', '洪涝占比', '洪涝占比'),
    ('temp', '平均气温', '平均气温'),
    ('spei', '干旱指数', '干旱指数'),
    ('prec', '降水量', '降水量'),
    ('sun', '日照时数', '日照时数'),
]

print("=" * 70)
print("FULL v3 vs 总表 COMPARISON")
print("=" * 70)

for v3_col, master_col, label in col_pairs:
    v3_vals = merged[v3_col]
    m_vals = merged[master_col]
    diff = (v3_vals - m_vals).abs()
    
    # Check if identical
    identical = (diff < 0.01).sum()
    same_source = identical == len(merged)
    
    print(f"\n{'='*50}")
    print(f"{label} ({v3_col} vs 总表.{master_col})")
    print(f"{'='*50}")
    print(f"  Same source? {'YES ✅' if same_source else 'NO ⚠️ (different source)'}")
    print(f"  Identical rows: {identical} / {len(merged)}")
    print(f"  v3:    mean={v3_vals.mean():.4f}  min={v3_vals.min():.4f}  max={v3_vals.max():.4f}")
    print(f"  总表:  mean={m_vals.mean():.4f}  min={m_vals.min():.4f}  max={m_vals.max():.4f}")
    if not same_source:
        ratio = v3_vals.mean() / m_vals.mean() if m_vals.mean() > 0.001 else float('inf')
        print(f"  Ratio v3/总表: {ratio:.4f} ({'+' if ratio>1 else ''}{(ratio-1)*100:.1f}%)")
        corr_val = v3_vals.corr(m_vals)
        print(f"  Correlation: {corr_val:.4f}")
        # Show a few diverging examples
        worst = diff.nlargest(5).index
        print(f"  Top 5 diverging rows:")
        for idx in worst:
            row = merged.loc[idx]
            print(f"    {row['province']} {row['year']}: v3={v3_vals[idx]:.2f}  总表={m_vals[idx]:.2f}")

print("\n" + "=" * 70)
print("OTHER v3 COLUMNS (not in 总表)")
print("=" * 70)
v3_only_cols = [c for c in v3.columns if c not in ['province', 'year', 'drou_a', 'flood_a', 'flood', 
                                                      'temp', 'spei', 'prec', 'sun']]
for c in v3_only_cols:
    vals = v3[c]
    if vals.dtype in ('float64', 'int64'):
        print(f"  {c:25s} mean={vals.mean():.4f}  min={vals.min():.4f}  max={vals.max():.4f}  NaN={vals.isna().sum()}")
