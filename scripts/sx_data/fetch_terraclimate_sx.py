"""
TerraClimate（月度 4.6km，本地 .nc）→ 山西县年度/生长季气候聚合。
一次只开一个 (var, year) 文件；预先算好县治最近格点索引，用 isel 提取（避免 method='nearest' 重复搜索）。
产出: data/interim/terraclimate_sx_county_yearly.parquet
"""
import xarray as xr
import pandas as pd
import numpy as np
from pathlib import Path

ROOT = Path(r"D:\DC\DC-AIino")
TC_DIR = ROOT / "data" / "raw" / "terraclimate"
cdf = pd.read_csv(ROOT / "data" / "interim" / "sx_county_centroids.csv")

VARS = ["tmax", "tmin", "ppt", "pet", "srad"]
YEARS = list(range(2012, 2024))
LON0, LON1, LAT0, LAT1 = 110.0, 115.5, 34.0, 41.0


def nearest_idx(coord, target):
    return int(np.abs(np.asarray(coord) - target).argmin())


rows = []
for var in VARS:
    for year in YEARS:
        fp = TC_DIR / f"TerraClimate_{var}_{year}.nc"
        if not fp.exists():
            continue
        ds = xr.open_dataset(fp)
        sub = ds[var].sel(lat=slice(LAT1, LAT0), lon=slice(LON0, LON1))
        latc, lonc = sub.lat.values, sub.lon.values
        t_idx = pd.to_datetime(sub.time.values)
        # 一次性把 bbox 子集读进内存（约 2MB，避免每县重复磁盘解压读）
        arr = sub.values
        for r in cdf.itertuples():
            li = nearest_idx(latc, r.lat)
            oi = nearest_idx(lonc, r.lon)
            vals = arr[:, li, oi]
            s = pd.Series(vals, index=t_idx)
            annual = float(s.mean())
            gs = s[(s.index.month >= 4) & (s.index.month <= 9)]
            rows.append({
                "county": r.county, "adcode": r.adcode, "year": year, "var": var,
                "annual": annual, "gs_mean": float(gs.mean()) if len(gs) else np.nan,
            })
        ds.close()
    print(f"  {var} 完成")

df = pd.DataFrame(rows)
wide = df.pivot_table(index=["county", "adcode", "year"], columns="var",
                      values=["annual", "gs_mean"]).reset_index()
wide.columns = [f"{a}_{b}" if b else a for a, b in wide.columns]
out = ROOT / "data" / "interim" / "terraclimate_sx_county_yearly.parquet"
wide.to_parquet(out, index=False)
print("已输出:", out, "| 行:", len(wide))
print(wide.head(4).to_string(index=False))
