#!/usr/bin/env python3
"""Merge all EPS partial CSV files into one complete dataset + add remaining provinces."""
import pandas as pd
import io
from pathlib import Path

RAW = Path("/home/slz/workspace/DC-AIino/data/raw/eps_yield")
OUT = RAW / "eps_city_yield_all.csv"

# Read all existing partials
files = sorted(RAW.glob("*.csv"))
pieces = []
for f in files:
    if f.name == "eps_city_yield_all.csv":
        continue
    df = pd.read_csv(f)
    pieces.append(df)
    print(f"  {f.name}: {len(df)} rows")

if pieces:
    df = pd.concat(pieces, ignore_index=True)
    df = df.drop_duplicates().sort_values(["province","city","year"]).reset_index(drop=True)
    
    # Remove non-10-province data (山西、辽宁、浙江、福建 are not in 10 major provinces)
    # Actually keep them for reference but only use 10 provinces for merge
    ten_provs = {"黑龙江","河南省","山东","山东省","吉林","吉林省","安徽","安徽省","湖南","湖南省","河北","河北省","四川","四川省","江苏","江苏省","湖北","湖北省","河南","黑龙江省"}
    df_10 = df[df['province'].isin(ten_provs)].copy()
    
    # Also remove 莱芜市 (merged into 济南 after 2019)
    df_10 = df_10[~((df_10['province']=='山东') & (df_10['city']=='莱芜市') & (df_10['year']>=2019))]
    
    print(f"\n✅ 合并后: {len(df_10)} 行（仅10主产省）")
    print("\n覆盖:")
    for p in ten_provs:
        sub = df_10[df_10['province']==p]
        cities = sub['city'].nunique()
        years = sub['year'].nunique()
        print(f"  {p}: {cities} 地级市, {years} 年")
    
    df_10.to_csv(OUT, index=False)
    print(f"\n✅ 保存到 {OUT}")
else:
    print("❌ 没有分片文件")
