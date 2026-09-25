"""
ERA5-Land (0.1°, CDS) → 山西县日尺度因子。
逐年请求生长季(4-9月)逐小时 2m温度+总降水 → 日均高/日降水 → 县提取 → 因子。
用法: python fetch_era5land_sx.py 2018        (只拉某年, 便于分批)
      python fetch_era5land_sx.py 2018 2023   (区间)
产出: data/interim/era5land_sx_daily_factors.parquet
"""
import cdsapi, zipfile, os, sys, time
from pathlib import Path
import xarray as xr
import pandas as pd
import numpy as np

ROOT = Path(r"D:\DC\DC-AIino")
RAW = ROOT / "data" / "raw" / "era5land"
RAW.mkdir(parents=True, exist_ok=True)
cdf = pd.read_csv(ROOT / "data" / "interim" / "sx_county_centroids.csv")

AREA = [41.5, 110.0, 34.0, 115.5]           # [lat_top(N), lon_left(W), lat_bottom(S), lon_right(E)]
MONTHS = ["04", "05", "06", "07", "08", "09"]
HOURS = [f"{h:02d}:00" for h in range(0, 24, 3)]   # 8次/日, 近似日最高温, 降成本
VARS = ["2m_temperature"]                           # 降水继续用 NASA, 降成本

lo, hi = int(sys.argv[1]), int(sys.argv[2]) if len(sys.argv) > 2 else int(sys.argv[1])


def pull(year):
    fn = RAW / f"era5land_2t_tp_{year}.zip"
    if fn.exists():
        print(f"  {year} 已存在, 跳过"); return fn
    req = cdsapi.Client().retrieve("reanalysis-era5-land", {
        "product_type": "reanalysis", "variable": VARS,
        "year": str(year), "month": MONTHS, "day": [f"{d:02d}" for d in range(1, 32)],
        "time": HOURS, "area": AREA, "data_format": "netcdf",
    })
    req.download(str(fn))
    print(f"  {year} 下载完成 {fn.stat().st_size/1e6:.1f} MB")
    return fn


def county_yearly(fn, year):
    with zipfile.ZipFile(fn) as z:
        nc = [n for n in z.namelist() if n.endswith(".nc")][0]
        z.extract(nc, str(RAW))
        ds = xr.open_dataset(RAW / nc)
    t2m = ds["t2m"] if "t2m" in ds else ds["2m_temperature"]   # K; 转℃
    tp = ds["tp"] if "tp" in ds else None
    latc, lonc = t2m.lat.values, t2m.lon.values
    time_idx = t2m.indexes["time"] if hasattr(t2m, "indexes") else pd.DatetimeIndex(t2m.time.values)
    rows = []
    for r in cdf.itertuples():
        li = int(np.abs(latc - r.lat).argmin()); oi = int(np.abs(lonc - r.lon).argmin())
        t = pd.Series(t2m.isel(latitude=li, longitude=oi).values - 273.15,
                      index=pd.to_datetime(t2m.time.values))     # ℃
        # 日聚合
        tmax_day = t.resample("1D").max()
        prec_day = (pd.Series(tp.isel(latitude=li, longitude=oi).values * 1000.0,
                             index=pd.to_datetime(tp.time.values)).resample("1D").sum()
                    if tp is not None else pd.Series(dtype=float))
        # 生长季(4-9月)因子
        mask = (tmax_day.index.month >= 4) & (tmax_day.index.month <= 9)
        gs_tmax = tmax_day[mask]
        gs_prec = prec_day[mask]
        rows.append({
            "county": r.county, "adcode": r.adcode, "year": year,
            "era_tmax_mean_gs": float(gs_tmax.mean()),
            "era_tmax_max_gs": float(gs_tmax.max()),
            "era_heat_days35": int((gs_tmax >= 35).sum()),
            "era_rainstorm_days": int((gs_prec >= 50).sum()) if len(gs_prec) else 0,
            "era_prec_sum_gs": float(gs_prec.sum()) if len(gs_prec) else np.nan,
        })
    ds.close()
    return rows


all_rows = []
for y in range(lo, hi + 1):
    print(f"== {y} 拉取 ==")
    fn = pull(y)
    all_rows.extend(county_yearly(fn, y))
    time.sleep(1)

df = pd.DataFrame(all_rows)
out = ROOT / "data" / "interim" / "era5land_sx_daily_factors.parquet"
df.to_parquet(out, index=False)
print("输出:", out, "| 行:", len(df))
print(df.head(5).to_string(index=False))
