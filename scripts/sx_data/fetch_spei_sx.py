"""
SPEI-3（本地 spei03.nc，0.5° 全球）→ 山西县年度 SPEI（县治最近格点，isel 取）。
产出: data/interim/spei_sx_county_annual.csv
"""
import xarray as xr
import pandas as pd
import numpy as np
from pathlib import Path

ROOT = Path(r"D:\DC\DC-AIino")
SPEI = ROOT / "data" / "raw" / "spei" / "spei03.nc"
cdf = pd.read_csv(ROOT / "data" / "interim" / "sx_county_centroids.csv")

ds = xr.open_dataset(SPEI)
var = list(ds.data_vars)[0]
da = ds[var]
latc, lonc = da.lat.values, da.lon.values
t_index = pd.to_datetime(da.time.values)
# SPEI 全时间序列每格点较大，只把需要的历史窗口(2012+)一次性读入
mask = t_index.year >= 2012
da_sub = da.isel(time=np.where(mask)[0])
latc, lonc = da_sub.lat.values, da_sub.lon.values
t_index_sub = pd.to_datetime(da_sub.time.values)
arr = da_sub.values   # (time, lat, lon)

rows = []
for r in cdf.itertuples():
    li = int(np.abs(latc - r.lat).argmin())
    oi = int(np.abs(lonc - r.lon).argmin())
    vals = arr[:, li, oi]
    s = pd.Series(vals, index=t_index_sub)
    for y, g in s.groupby(s.index.year):
        rows.append({
            "county": r.county, "adcode": r.adcode, "year": int(y),
            "spei3_aprjun": float(g[(g.index.month >= 4) & (g.index.month <= 6)].mean()),
            "spei3_junaug": float(g[(g.index.month >= 6) & (g.index.month <= 8)].mean()),
            "spei3_growing": float(g[(g.index.month >= 4) & (g.index.month <= 9)].mean()),
        })

df = pd.DataFrame(rows)
out = ROOT / "data" / "interim" / "spei_sx_county_annual.csv"
df.to_csv(out, index=False)
print("已输出:", out, "| 行:", len(df))

# SPEI-3 指标非空诊断
for c in ["spei3_aprjun", "spei3_junaug", "spei3_growing"]:
    print(f"  {c}: 非空 {df[c].notna().mean()*100:.1f}%")
