#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""v10 Step 3：ERA5-Land 0.1° 日值 → 10 省 1,199 县极端指数。

补的是当前面板缺的**日尺度**：
  TX35（日最高温 ≥35℃ 天数）、生长季 Tmax 均值/极值、Tmin 极值、
  连续无雨日 CDD、R95p 日数、暴雨日数、生长季降水总量。

做法
====
1. 从 county.db 的 county_meta 取 1,199 县质心（lon/lat）；
2. 按年请求 ERA5-Land（0.1°，3 小时分辨率，生长季 4–9 月，2m 温度 + 总降水）；
3. 每县取最近格点，日聚合后算极端指数；
4. 逐年落盘，先跑 2012 试点，再扩到 2013–2023。

用法
====
    python scripts/data/v10_03_fetch_era5land_10prov.py --start-year 2012 --end-year 2012
    python scripts/data/v10_03_fetch_era5land_10prov.py --start-year 2012 --end-year 2023

注意
====
- 3 小时温度是日最高温的近似；若要严格 TX35，把 --hours 改成 hourly（数据量约 3 倍）。
- 先跑一年验证 CDS 请求和 NetCDF 结构，再批量；不要一上来拉 12 年。
"""
from __future__ import annotations

import argparse
import sys
import time
import zipfile
from pathlib import Path

import numpy as np
import pandas as pd
import xarray as xr

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

PROJECT_ROOT = Path(__file__).resolve().parents[2]
CENTROIDS = PROJECT_ROOT / "data" / "interim" / "county_centroids_1199.csv"
RAW = PROJECT_ROOT / "data" / "raw" / "era5land_10prov"
OUT = PROJECT_ROOT / "data" / "interim" / "era5land_10prov_daily_factors.parquet"

DEFAULT_AREA = [53.5, 97.5, 24.5, 135.5]  # [N, W, S, E]，覆盖 10 主产省
DEFAULT_MONTHS = ["04", "05", "06", "07", "08", "09"]
DEFAULT_HOURS = [f"{h:02d}:00" for h in range(0, 24, 3)]
VARS = ["2m_temperature", "total_precipitation"]


def pull(year: int, area: list[float], months: list[str], hours: list[str]) -> Path:
    RAW.mkdir(parents=True, exist_ok=True)
    fn = RAW / f"era5land_10prov_2t_tp_{year}.zip"
    if fn.exists() and fn.stat().st_size > 1024:
        print(f"  {year} 已存在，跳过下载")
        return fn

    import cdsapi

    print(f"  {year} 提交 CDS 请求 ...")
    client = cdsapi.Client()
    client.retrieve(
        "reanalysis-era5-land",
        {
            "product_type": "reanalysis",
            "variable": VARS,
            "year": str(year),
            "month": months,
            "day": [f"{d:02d}" for d in range(1, 32)],
            "time": hours,
            "area": area,
            "data_format": "netcdf",
        },
        str(fn),
    )
    print(f"  {year} 下载完成 {fn.stat().st_size / 1e6:.1f} MB")
    return fn


def _cdd_max(prec: pd.Series, threshold: float = 1.0) -> int:
    best = cur = 0
    for v in prec.values:
        if np.isfinite(v) and v < threshold:
            cur += 1
            best = max(best, cur)
        else:
            cur = 0
    return int(best)


def county_factors(fn: Path, year: int, months: list[str]) -> pd.DataFrame:
    with zipfile.ZipFile(fn) as z:
        nc = [n for n in z.namelist() if n.endswith(".nc")][0]
        z.extract(nc, str(fn.parent))
        ds = xr.open_dataset(fn.parent / nc)

    t2m = ds["t2m"] if "t2m" in ds else ds["2m_temperature"]
    tp = ds["tp"] if "tp" in ds else ds["total_precipitation"]
    latc, lonc = t2m.lat.values, t2m.lon.values
    t_index = pd.to_datetime(t2m.time.values)
    cdf = pd.read_csv(CENTROIDS)

    rows = []
    for r in cdf.itertuples():
        li = int(np.abs(latc - r.lat).argmin())
        oi = int(np.abs(lonc - r.lon).argmin())

        t = pd.Series(t2m.isel(latitude=li, longitude=oi).values - 273.15, index=t_index)
        p = pd.Series(tp.isel(latitude=li, longitude=oi).values * 1000.0, index=t_index)

        tmax = t.resample("1D").max()
        tmin = t.resample("1D").min()
        pday = p.resample("1D").sum()

        mask = tmax.index.month.isin([int(m) for m in months])
        tmax_gs = tmax[mask]
        tmin_gs = tmin[mask]
        p_gs = pday[mask]

        wet = p_gs[p_gs >= 1.0]
        p95 = float(wet.quantile(0.95)) if len(wet) else np.nan
        r95p_days = int((wet > p95).sum()) if np.isfinite(p95) else 0

        rows.append({
            "county_code": int(r.county_code),
            "year": year,
            "era_tmax_mean_gs": float(tmax_gs.mean()),
            "era_tmax_max_gs": float(tmax_gs.max()),
            "era_heat_days35": int((tmax_gs >= 35).sum()),
            "era_tmin_min_gs": float(tmin_gs.min()),
            "era_prec_sum_gs": float(p_gs.sum()),
            "era_wet_days": int((p_gs >= 1.0).sum()),
            "era_rainstorm_days": int((p_gs >= 50.0).sum()),
            "era_cdd_max": _cdd_max(p_gs),
            "era_prec_p95": p95,
            "era_r95p_days": r95p_days,
        })

    ds.close()
    return pd.DataFrame(rows)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--start-year", type=int, default=2012)
    ap.add_argument("--end-year", type=int, default=2012)
    ap.add_argument("--months", default=",".join(DEFAULT_MONTHS))
    ap.add_argument("--hours", default=",".join(DEFAULT_HOURS))
    ap.add_argument("--area", default=",".join(map(str, DEFAULT_AREA)))
    ap.add_argument("--out", type=Path, default=OUT)
    args = ap.parse_args()

    months = args.months.split(",")
    hours = args.hours.split(",")
    area = [float(x) for x in args.area.split(",")]
    if len(area) != 4:
        raise SystemExit("--area 必须是 N,W,S,E 四个值")

    all_rows = []
    for year in range(args.start_year, args.end_year + 1):
        print(f"\n== {year} ==")
        fn = pull(year, area, months, hours)
        df = county_factors(fn, year, months)
        all_rows.append(df)
        print(f"  {year}: {len(df)} 县，示例 {df.iloc[0].to_dict()}")
        # 每年落盘，避免批量跑到一半前功尽弃
        pd.concat(all_rows, ignore_index=True).to_parquet(args.out, index=False)
        time.sleep(1)

    print(f"\n✅ {args.out} | 行数 {sum(len(x) for x in all_rows)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
