"""
合并山西县所有已获取数据 -> paper_panel_sx_full.parquet，并输出覆盖诊断。
合并键: (adcode, year)。统计面板按县代码匹配；气候/SPEI/高程按县质心代码匹配。
"""
import pandas as pd
import numpy as np
from pathlib import Path

ROOT = Path(r"D:\DC\DC-AIino") / "data" / "interim"

panel = pd.read_parquet(ROOT / "paper_panel_sx.parquet")
tc = pd.read_parquet(ROOT / "terraclimate_sx_county_yearly.parquet")
spei = pd.read_csv(ROOT / "spei_sx_county_annual.csv")
elev = pd.read_csv(ROOT / "sx_county_elevation.csv")
cent = pd.read_csv(ROOT / "sx_county_centroids.csv")
np_daily = pd.read_parquet(ROOT / "nasapower_sx_daily_factors.parquet")

# 统计面板已有 county_code；气候/SPEI 用 adcode（同区划代码）
def code_str(x):
    if x is None or (isinstance(x, float) and np.isnan(x)):
        return None
    return str(int(x)).zfill(6)

panel["code"] = panel["county_code"].map(code_str)
tc["code"] = tc["adcode"].astype(int).astype(str).str.zfill(6)
spei["code"] = spei["adcode"].astype(int).astype(str).str.zfill(6)
cent["code"] = cent["adcode"].astype(int).astype(str).str.zfill(6)

# 高程按县（adcode）合并到统计面板的 county 级（去重）
elev_by_code = elev.merge(cent[["county", "code", "lon", "lat"]], on=["lon", "lat"], how="left")
elev_map = elev_by_code.dropna(subset=["code"]).groupby("code")["elev_m"].first()

# 统计面板按 (code, year)
df = panel.merge(tc[["code", "year", "annual_tmax", "annual_tmin", "annual_ppt",
                     "annual_pet", "annual_srad", "gs_mean_tmax", "gs_mean_tmin",
                     "gs_mean_ppt", "gs_mean_pet", "gs_mean_srad"]],
                 on=["code", "year"], how="left")
df = df.merge(spei[["code", "year", "spei3_aprjun", "spei3_junaug", "spei3_growing"]],
              on=["code", "year"], how="left")
np_daily["code"] = np_daily["adcode"].astype(int).astype(str).str.zfill(6)
df = df.merge(np_daily[["code", "year", "heat_days", "heat_jja", "rainstorm_days",
                         "cdd_max", "dry_hot_wind", "autumn_rain_days"]],
              on=["code", "year"], how="left")
df["elev_m"] = df["code"].map(elev_map)

out = ROOT / "paper_panel_sx_full.parquet"
df.to_parquet(out, index=False)
print("已输出:", out, "| 行:", len(df))

# 覆盖诊断
key = ["grain_output_t", "sown_area_kha", "yield_ton_per_ha", "gs_mean_tmax",
       "gs_mean_ppt", "spei3_growing", "heat_jja", "cdd_max", "rainstorm_days",
       "dry_hot_wind", "autumn_rain_days", "elev_m", "county", "city", "year"]
diag = df[key].notna().mean().mul(100).round(1)
print("\n=== 合并后关键字段覆盖 (%) ===")
print(diag.to_string())
