#!/usr/bin/env python3
"""Step 1: Save all EPS yield data + merge + Step 2: Run import into v5"""
import pandas as pd
from pathlib import Path

RAW = Path("/home/slz/workspace/DC-AIino/data/raw/eps_yield")
V5 = Path("/home/slz/workspace/DC-AIino/data/interim/feature_matrix_v5.parquet")

# ── Step 1: Merge all partials ──
dfs = []
for f in sorted(RAW.glob("*.csv")):
    if f.name == "eps_city_yield_all.csv":
        continue
    dfs.append(pd.read_csv(f))

df_all = pd.concat(dfs, ignore_index=True)
df_all = df_all.drop_duplicates().sort_values(["province","city","year"]).reset_index(drop=True)
print(f"\n=== EPS 数据汇总 ===")
print(f"总行数: {len(df_all)}")
for p in sorted(df_all['province'].unique()):
    c = df_all[df_all['province']==p]['city'].nunique()
    y0 = df_all[df_all['province']==p]['year'].min()
    y1 = df_all[df_all['province']==p]['year'].max()
    print(f"  {p}: {c} 地级市, {y0}-{y1}")

df_all.to_csv(RAW / "eps_city_yield_all.csv", index=False)
print(f"✅ 已保存 eps_city_yield_all.csv")

# ── Step 2: Import into v5 ──
# Load v5
v5 = pd.read_parquet(V5)
print(f"\nv5 当前: {len(v5)} 行 × {v5.shape[1]} 列")

# Only keep data from 10 major grain provinces
ten_provs = {"黑龙江省","河南省","山东省","吉林省","安徽省","湖南省","河北省","四川省","江苏省","湖北省"}
eps = df_all[df_all['province'].isin(ten_provs)].copy()

# Drop rows where production is empty
eps = eps.dropna(subset=['production_wan_ton'])
eps['production_wan_ton'] = pd.to_numeric(eps['production_wan_ton'], errors='coerce')
eps = eps.dropna(subset=['production_wan_ton'])

# eps uses full names like "河南省", v5 uses short names like "河南"
prov_map = {
    "黑龙江省":"黑龙江","河南省":"河南","山东省":"山东","吉林省":"吉林",
    "安徽省":"安徽","湖南省":"湖南","河北省":"河北","四川省":"四川",
    "江苏省":"江苏","湖北省":"湖北","浙江省":"浙江","福建省":"福建",
    "辽宁省":"辽宁","山西省":"山西","广东省":"广东"
}
eps['province'] = eps['province'].map(prov_map).fillna(eps['province'])

print(f"\n10主产省地级市产量数据: {len(eps)} 行")
print(f"省份: {sorted(eps['province'].unique())}")

# Also filter v5 to only 10 provinces
v5_10 = v5[v5['province'].isin(ten_provs - {"浙江省","福建省","辽宁省","山西省"} | set(prov_map.values()))].copy()
# Actually just use the provinces that exist
v5_provs = set(v5['province'].unique())
eps_provs = set(eps['province'].unique())
print(f"v5 省份: {sorted(v5_provs)}")
print(f"EPS 省份: {sorted(eps_provs)}")

# Merge: replace v5's production_wan_ton with city-level data
# v5 has (province, city, year), eps has (province, city, year)
merge_cols = ['province','city','year']
v5_before = v5.copy()

# Rename to avoid conflict
eps_merge = eps.rename(columns={'production_wan_ton':'production_city'})

v5_new = v5.merge(eps_merge, on=merge_cols, how='left', suffixes=('','_eps'))

# Where city-level data exists, replace the provincial value
matched = v5_new['production_city'].notna().sum()
print(f"\n地级市产量匹配: {matched}/{len(v5_new)} ({matched/len(v5_new)*100:.1f}%)")

mask = v5_new['production_city'].notna()
v5_new.loc[mask, 'production_wan_ton'] = v5_new.loc[mask, 'production_city']
v5_new = v5_new.drop(columns=['production_city'])

# Recalculate yield_kg_per_ha
if 'sown_qian_ha' in v5_new.columns:
    v5_new['yield_kg_per_ha'] = v5_new['production_wan_ton'] * 10000 / v5_new['sown_qian_ha']

changed = (v5_new['production_wan_ton'] != v5_before['production_wan_ton']).sum()
print(f"产量值变更: {changed}/{len(v5_new)} ({changed/len(v5_new)*100:.1f}%)")

# Show examples
if changed > 0:
    diff = v5_new[v5_new['production_wan_ton'] != v5_before['production_wan_ton']].head(5)
    for _, r in diff.iterrows():
        old = v5_before.loc[(v5_before['province']==r['province'])&(v5_before['city']==r['city'])&(v5_before['year']==r['year']),'production_wan_ton'].values[0]
        print(f"  {r['province']} {r['city']} {r['year']}: {old:.2f} → {r['production_wan_ton']:.2f} 万吨")

# Save
v5_new.to_parquet(V5, index=False)
print(f"\n✅ v5 已更新: {len(v5_new)} 行 × {v5_new.shape[1]} 列")
print(f"✅ NaN: {v5_new.isna().sum().sum()}")
