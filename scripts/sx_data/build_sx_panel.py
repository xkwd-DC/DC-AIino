"""
从《中国县域统计年鉴》抽取山西省县级面板（P0）。
产出: data/interim/paper_panel_sx.parquet + data/interim/sx_panel_coverage.csv
字段用的是年鉴 A 文件《区县面板数据2000-2024.xlsx》的明列名。
零外部依赖（pandas + openpyxl）。
"""
import pandas as pd
import numpy as np
from pathlib import Path

ROOT = Path(r"D:\DC\DC-AIino")
YEARBOOK = ROOT / r"data\raw\statistical_yearbook\【25170】中国县域统计年鉴2000-2024\区县面板数据2000-2024.xlsx"
OUT_DIR = ROOT / "data" / "interim"
OUT_DIR.mkdir(parents=True, exist_ok=True)

# 年鉴明列名 -> 重命名
COLMAP = {
    "年份": "year",
    "省份": "province",
    "城市": "city",
    "区县": "county",
    "区县代码": "county_code",
    "行政区域土地面积_平方公里": "admin_area_km2",
    "农作物总播种面积_千公顷": "sown_area_kha",
    "常用耕地面积_公顷": "cultivated_area_ha",
    "粮食总产量_吨": "grain_output_t",
    "农业机械总动力_万千瓦特": "mach_power_10kw",
    "农村居民人均可支配收入_元": "rural_inc_yuan",
    "第一产业增加值_万元": "primary_va_wan",
    "地区生产总值_万元": "gdp_wan",
    "年末总人口_万人": "pop_wan",
    "乡村人口_万人": "rural_pop_wan",
    "乡村从业人员数_人": "rural_workers",
    "农林牧渔业从业人员数_人": "agri_workers",
    "农林牧渔业总产值_万元": "agri_output_wan",
}

df = pd.read_excel(YEARBOOK)
print("年鉴总行数:", len(df), "列:", df.shape[1])

# 仅保留山西 + 用到的列
df = df[df["省份"].astype(str).str.contains("山西")].copy()
print("山西行数:", len(df), " | 山西县级数(区县):", df["区县"].nunique())

keep = [c for c in COLMAP if c in df.columns]
df = df[keep].rename(columns=COLMAP)
df["year"] = df["year"].astype(int)
df = df.sort_values(["county_code", "year"]).reset_index(drop=True)

# 单产(吨/公顷) = 产量(吨) / (播种面积(千公顷)*1000)
sown_ha = df["sown_area_kha"] * 1000.0
df["yield_ton_per_ha"] = np.where(
    sown_ha > 0, df["grain_output_t"] / sown_ha, np.nan
)

# 落盘
out_pq = OUT_DIR / "paper_panel_sx.parquet"
df.to_parquet(out_pq, index=False)

# 覆盖诊断
diag = pd.DataFrame({
    "variable": list(df.columns),
    "nonnull_n": df.notna().sum(),
    "nonnull_pct": (df.notna().mean() * 100).round(2),
})
diag.to_csv(OUT_DIR / "sx_panel_coverage.csv", index=False)

print("已输出:", out_pq)
print("\n=== 山西县面板覆盖诊断 ===")
print(diag.to_string(index=False))

print("\n=== 山西县样本(前5) ===")
print(df.head(5).to_string())
