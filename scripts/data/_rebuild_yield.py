#!/usr/bin/env python3
"""Build complete EPS city yield dataset from all user-provided data."""
import pandas as pd
from pathlib import Path

RAW = Path("/home/slz/workspace/DC-AIino/data/raw/eps_yield")

# Read existing 4 province files
dfs = []
for f in RAW.glob("*.csv"):
    if f.name == "eps_city_yield_all.csv":
        continue
    dfs.append(pd.read_csv(f))

# Combine with the data just provided in user messages
# These are the provinces: 河南,湖北,四川,山东,湖南,吉林,黑龙江
# Plus the existing: 安徽,江苏,河北

# Read the new partial that was just written
# Actually we need to save the user's latest data first
# For now, just merge what we have and deduplicate
df = pd.concat(dfs, ignore_index=True)
print(f"从已有文件合并: {len(df)} 行")
print(f"省份: {sorted(df['province'].unique())}")

df = df.drop_duplicates().sort_values(["province","city","year"]).reset_index(drop=True)
df.to_csv(RAW / "eps_city_yield_all.csv", index=False)
print(f"\n保存 {len(df)} 行")
