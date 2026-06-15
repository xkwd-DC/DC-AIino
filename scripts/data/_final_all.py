#!/usr/bin/env python3
"""Merge all partial CSV files, import to v5, commit and push."""
import os, pandas as pd
import subprocess, sys
from pathlib import Path

RAW = Path("/home/slz/workspace/DC-AIino/data/raw/eps_yield")
V5 = Path("/home/slz/workspace/DC-AIino/data/interim/feature_matrix_v5.parquet")
PROJ = Path("/home/slz/workspace/DC-AIino")

# ── Step 1: Merge all CSV files ──
print("="*60)
print("STEP 1: 合并所有EPS分片文件")
print("="*60)

dfs = []
for f in sorted(RAW.glob("*.csv")):
    if f.name == "eps_city_yield_all.csv":
        continue
    df = pd.read_csv(f)
    dfs.append(df)
    provs = df['province'].unique()
    print(f"  {f.name}: {len(df)} rows ({', '.join(provs)})")

df_all = pd.concat(dfs, ignore_index=True)
df_all = df_all.drop_duplicates().sort_values(["province","city","year"]).reset_index(drop=True)
print(f"\n✅ 合并后总行数: {len(df_all)}")
for p in sorted(df_all['province'].unique()):
    c = df_all[df_all['province']==p]['city'].nunique()
    print(f"  {p}: {c} 地级市")

df_all.to_csv(RAW / "eps_city_yield_all.csv", index=False)
print("✅ 已保存")

# ── Step 2: Import to v5 ──
print("\n" + "="*60)
print("STEP 2: 导入地级市产量到 v5")
print("="*60)

v5 = pd.read_parquet(V5)
v5_before = v5.copy()

# Province name mapping
prov_map = {
    "黑龙江省":"黑龙江","河南省":"河南","山东省":"山东","吉林省":"吉林",
    "安徽省":"安徽","湖南省":"湖南","河北省":"河北","四川省":"四川",
    "江苏省":"江苏","湖北省":"湖北","浙江省":"浙江","福建省":"福建"
}
df_all['province_short'] = df_all['province'].map(prov_map).fillna(df_all['province'])

# Only 10 major provinces
ten_provs = {"黑龙江","河南","山东","吉林","安徽","湖南","河北","四川","江苏","湖北"}
eps = df_all[df_all['province_short'].isin(ten_provs)].copy()
eps = eps.dropna(subset=['production_wan_ton'])
eps['production_wan_ton'] = pd.to_numeric(eps['production_wan_ton'], errors='coerce')
eps = eps.dropna(subset=['production_wan_ton'])

print(f"EPS 10主产省数据: {len(eps)} 行")

eps_merge = eps[['province_short','city','year','production_wan_ton']].rename(
    columns={'province_short':'province','production_wan_ton':'production_city'}
)

v5_new = v5.merge(eps_merge, on=['province','city','year'], how='left')

matched = v5_new['production_city'].notna().sum()
print(f"地级市产量匹配: {matched}/{len(v5_new)} ({matched/len(v5_new)*100:.1f}%)")

mask = v5_new['production_city'].notna()
v5_new.loc[mask, 'production_wan_ton'] = v5_new.loc[mask, 'production_city']
v5_new = v5_new.drop(columns=['production_city'])

# Recalculate yield
if 'sown_qian_ha' in v5_new.columns:
    v5_new['yield_kg_per_ha'] = v5_new['production_wan_ton'] * 10000 / v5_new['sown_qian_ha']

changed = (v5_new['production_wan_ton'] != v5_before['production_wan_ton']).sum()
print(f"产量值变更: {changed}/{len(v5_new)} ({changed/len(v5_new)*100:.1f}%)")

v5_new.to_parquet(V5, index=False)
print(f"✅ v5 已更新: {len(v5_new)} 行, NaN: {v5_new.isna().sum().sum()}")

# Show per province stats
print("\n各地产量变更:")
for p in sorted(ten_provs):
    old = v5_before[v5_before['province']==p]['production_wan_ton'].unique()
    new_vals = v5_new[v5_new['province']==p]['production_wan_ton']
    unique_new = new_vals.nunique()
    print(f"  {p}: 省统一值{len(old)}个 → 地级市{unique_new}个不同值")

# ── Step 3: Commit and Push ──
print("\n" + "="*60)
print("STEP 3: Git commit + push")
print("="*60)

# Read token
token = open(Path.home() / ".gh_token").read().strip()
os.environ['GH_TOKEN'] = token

cmds = [
    f"cd {PROJ} && git add -A",
    f"cd {PROJ} && git commit -m 'feat(v5): EPS地级市粮食产量导入 - 10省×148地级市×2011-2024'",
    f"cd {PROJ} && git push origin main",
]

for cmd in cmds:
    result = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=30)
    out = result.stdout.strip() + result.stderr.strip()
    print(out[:200] if out else "OK")
