import pandas as pd
import numpy as np
from pathlib import Path

PROJECT = Path('/home/slz/workspace/DC-AIino')

# ── 1. Load v3 panel ──────────────────────────────────────
v3 = pd.read_parquet(PROJECT / 'data/interim/paper_panel_v3.parquet')
print(f"v3: {v3.shape}")

# ── 2. Load 总表 (master table) ───────────────────────────
df_master = pd.read_excel(
    PROJECT / 'data/raw/paper_panel/wang_tianshuo_original/总表.xlsx'
)
print(f"总表: {df_master.shape}")
print(f"Columns: {list(df_master.columns)}")

# ── 3. Inspect all columns ────────────────────────────────
print("\n--- 总表 sample ---")
print(df_master.head(3).to_string())
print(f"\nUnique provinces: {sorted(df_master['省份'].unique())}")
print(f"Year range: {df_master['年份'].min()} - {df_master['年份'].max()}")

# ── 4. Check numeric columns ──────────────────────────────
for col in df_master.columns:
    if col not in ('省份', '年份'):
        vals = pd.to_numeric(df_master[col], errors='coerce')
        print(f"  {col:20s}  min={vals.min():.2f}  max={vals.max():.2f}  NaN={vals.isna().sum()}")

# ── 5. Check a specific province (Henan) across years ─────
hn = df_master[df_master['省份'] == '河南'].sort_values('年份')
print("\n--- 河南 full series ---")
print(hn.to_string())
