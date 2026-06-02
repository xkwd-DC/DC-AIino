import pandas as pd
import os

base = 'data/raw/paper_panel/wang_tianshuo_original'
pd.set_option('display.max_columns', None)
pd.set_option('display.width', 300)

# === 1. 成灾数据 — all sheets ===
print("=" * 70)
print("1. 分省年度成灾数据 (5).xlsx — ALL SHEETS")
xl = pd.ExcelFile(os.path.join(base, '分省年度成灾数据 (5).xlsx'))
for sname in xl.sheet_names:
    df = pd.read_excel(xl, sheet_name=sname, header=None)
    print(f"\nSheet: '{sname}' — shape {df.shape}")
    for j in range(min(5, len(df))):
        row = [str(x)[:50] for x in df.iloc[j].tolist()[:10]]
        print(f"  Row {j}: {row}")

# === 2. 总表 — disaster columns ===
print("\n" + "=" * 70)
print("2. 总表.xlsx — disaster columns")
df_m = pd.read_excel(os.path.join(base, '总表.xlsx'))
disc = [c for c in df_m.columns if any(k in str(c) for k in ['灾','洪','旱','水','成','flood','drou'])]
print(f"Disaster-like columns: {disc}")
if disc:
    cols_show = [c for c in ['省份','年份','year','province'] if c in df_m.columns]
    print(df_m[cols_show + disc].head(20).to_string())

# === 3. 旱灾 — full structure ===
print("\n" + "=" * 70)
print("3. 旱灾受灾面积 — year range and province count")
df_d = pd.read_excel(os.path.join(base, '旱灾受灾面积（千公顷）.xlsx'))
year_cols = [c for c in df_d.columns if isinstance(c, (int, float)) or str(c).isdigit()]
# Filter to 2011-2023
target_years = [y for y in year_cols if 2011 <= int(y) <= 2023]
print(f"Province col: {df_d.columns[0]}")
print(f"All year cols: {year_cols}")
print(f"Target years (2011-2023): {target_years}")
print(f"Shape: {df_d.shape}")
print(f"Provinces: {df_d[df_d.columns[0]].tolist()}")
prov_count = sum(1 for p in df_d[df_d.columns[0]] if p != '全国总计' and pd.notna(p))
print(f"Province count (excl national): {prov_count}")

# === 4. 水灾 — check if extendable ===
print("\n" + "=" * 70)
print("4. 水灾受灾面积 — full structure")
df_f = pd.read_excel(os.path.join(base, '水灾受灾面积（千公顷）.xlsx'))
print(f"Columns: {list(df_f.columns)}")
print(f"Years: {[c for c in df_f.columns if isinstance(c, (int, float))]}")
print(f"Provinces: {df_f[df_f.columns[0]].tolist()}")
print(f"Available years: {df_f.columns[1:].tolist()}")

# === 5. Check v3 province names for alignment ===
print("\n" + "=" * 70)
print("5. v3 province names")
v3 = pd.read_parquet('data/interim/paper_panel_v3.parquet')
print(f"v3 provinces: {sorted(v3['province'].unique())}")
print(f"v3 years: {sorted(v3['year'].unique())}")
