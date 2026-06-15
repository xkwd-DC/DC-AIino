#!/usr/bin/env python3
"""Read all partial CSV files, merge, deduplicate, save as eps_city_yield_all.csv"""
import pandas as pd
from pathlib import Path

RAW = Path("/home/slz/workspace/DC-AIino/data/raw/eps_yield")
dfs = []
for f in sorted(RAW.glob("*.csv")):
    if f.name == "eps_city_yield_all.csv":
        continue
    df = pd.read_csv(f)
    dfs.append(df)
    print(f"  {f.name}: {len(df)} rows, provinces={list(df['province'].unique())}")

df = pd.concat(dfs, ignore_index=True)
before = len(df)
df = df.drop_duplicates().sort_values(["province","city","year"]).reset_index(drop=True)
print(f"\n✅ 合并前 {before} 行 → 去重后 {len(df)} 行")

for p in sorted(df['province'].unique()):
    c = df[df['province']==p]['city'].nunique()
    y_range = f"{df[df['province']==p]['year'].min()}-{df[df['province']==p]['year'].max()}"
    print(f"  {p}: {c} 地级市, {y_range}")

df.to_csv(RAW / "eps_city_yield_all.csv", index=False)
print(f"\n✅ 保存到 eps_city_yield_all.csv")
