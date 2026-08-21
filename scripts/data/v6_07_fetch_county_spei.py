#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""v6 Step 7：县级 SPEI-3 面板（SPEIbase v2.10, 0.5° 全球网格）—— 替换省级 SPEI。

1. 下载 spei03.nc（~6GB, requests Range 断点续传）→ data/raw/spei/
2. 县治最近格点（与 v6_01c 同款窗口裁剪，防内存击穿）
3. 月度序列 → 年度聚合（口径与 00c 省级一致）：
   spei_annual_mean        = 1-12 月均值
   spei_growing_season_mean = 4-10 月均值（生长季）

SPEIbase 网格：lat 90→-90 降序（720 格），lon 0→359.5 升序（1440 格），
变量 spei（3 个月尺度，最适合作物风险，见 00c 说明）。

输出: data/interim/spei_county_annual_v6.csv
      列: 区县代码, province, city, county, year, spei_annual_mean, spei_growing_season_mean
"""
import logging
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import requests

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.stderr.reconfigure(encoding="utf-8", errors="replace")

import netCDF4
from netCDF4 import num2date

PROJECT_ROOT = Path(__file__).resolve().parents[2]
PANEL = PROJECT_ROOT / "data" / "interim" / "paper_panel_v6.parquet"
NC_DIR = PROJECT_ROOT / "data" / "raw" / "spei"
NC_LOCAL = NC_DIR / "spei03.nc"
OUT = PROJECT_ROOT / "data" / "interim" / "spei_county_annual_v6.csv"

SPEI_URL = "https://digital.csic.es/bitstream/10261/364137/3/spei03.nc"
CHUNK = 1024 * 1024

YEARS = range(2012, 2024)
GROWING_MONTHS = [4, 5, 6, 7, 8, 9, 10]


def download() -> None:
    """断点续传 + 断线重试下载 spei03.nc（~380MB，代理下大文件易断）。"""
    import time
    NC_DIR.mkdir(parents=True, exist_ok=True)
    for attempt in range(1, 11):
        if NC_LOCAL.exists() and NC_LOCAL.stat().st_size > 10**8:
            logging.info("spei03.nc 已存在 (%.1f GB)，跳过", NC_LOCAL.stat().st_size / 2**30)
            return
        partial = NC_LOCAL.with_suffix(".nc.partial")
        already = partial.stat().st_size if partial.exists() else 0
        headers = {"Range": f"bytes={already}-"} if already > 0 else {}
        logging.info("下载 spei03.nc → %s (attempt %d, 续传 %d MB)", NC_LOCAL, attempt, already // 2**20)
        try:
            with requests.get(SPEI_URL, headers=headers, stream=True, timeout=180) as resp:
                resp.raise_for_status()
                total = int(resp.headers.get("Content-Length", 0)) + already
                done = already
                last_pct = -1
                with partial.open("ab" if already > 0 else "wb") as fp:
                    for c in resp.iter_content(chunk_size=CHUNK):
                        if c:
                            fp.write(c)
                            done += len(c)
                            pct = int(done / total * 10) if total else 0
                            if pct != last_pct:
                                last_pct = pct
                                logging.info("  下载 %d%% (%.2f / %.2f GB)", pct * 10, done / 2**30, total / 2**30)
            partial.rename(NC_LOCAL)
            logging.info("下载完成: %.2f GB", NC_LOCAL.stat().st_size / 2**30)
            return
        except requests.RequestException as e:
            logging.warning("attempt %d 下载中断 (%s)，5s 后续传重试", attempt, e)
            time.sleep(5)
    raise RuntimeError("spei03.nc 下载失败（10 次尝试均断线）")


def build_cell_map(panel: pd.DataFrame) -> tuple[np.ndarray, np.ndarray, np.ndarray, int, int, int, int]:
    """panel lon/lat → SPEI 网格最近点 + 裁剪窗口。返回 (区县代码, jj, ii, j0, i0, j1, i1)。"""
    with netCDF4.Dataset(NC_LOCAL) as ds:
        lat = np.asarray(ds.variables["lat"][:], dtype=float)
        lon = np.asarray(ds.variables["lon"][:], dtype=float)
    nj, ni = len(lat), len(lon)
    logging.info("SPEI 网格: %d lat x %d lon (lat %.1f→%.1f, lon %.1f→%.1f)",
                 nj, ni, lat[0], lat[-1], lon[0], lon[-1])
    assert lon[0] < lon[-1], "SPEIbase lon 应升序"

    plon, plat = panel["lon"].values.astype(float), panel["lat"].values.astype(float)
    # lat/lon 均升序（SPEIbase: -89.75→89.75 / -179.75→179.75）
    j = np.clip(np.searchsorted(lat, plat), 1, nj - 1)
    j = np.where(np.abs(lat[j] - plat) <= np.abs(lat[j - 1] - plat), j, j - 1)
    i = np.clip(np.searchsorted(lon, plon), 1, ni - 1)
    i = np.where(np.abs(lon[i] - plon) <= np.abs(lon[i - 1] - plon), i, i - 1)

    # 中国范围裁剪窗口（10 主产省 lat 20-55, lon 95-140，留边距）
    j0 = int(np.searchsorted(lat, 20.0))
    j1 = int(np.searchsorted(lat, 55.0))
    i0 = int(np.searchsorted(lon, 95.0))
    i1 = int(np.searchsorted(lon, 140.0))
    jj, ii = j - j0, i - i0
    assert jj.min() >= 0 and jj.max() < j1 - j0 and ii.min() >= 0 and ii.max() < i1 - i0, \
        "窗口外有县点，检查裁剪范围"
    return panel["区县代码"].values.astype(int), jj, ii, j0, i0, j1, i1


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s", datefmt="%H:%M:%S")
    download()

    panel = pd.read_parquet(PANEL)[["区县代码", "省份", "城市", "区县", "lon", "lat"]] \
        .drop_duplicates("区县代码").dropna(subset=["lon", "lat"]).reset_index(drop=True)
    cid, jj, ii, j0, i0, j1, i1 = build_cell_map(panel)
    logging.info("cell map done: %d counties", len(cid))

    with netCDF4.Dataset(NC_LOCAL) as ds:
        var = ds.variables["spei"]
        t_units = ds.variables["time"].units
        t_cal = ds.variables["time"].calendar if "calendar" in ds.variables["time"].ncattrs() else "standard"
        dates = num2date(ds.variables["time"][:], units=t_units, calendar=t_cal)
        years = np.array([d.year for d in dates])
        months = np.array([d.month for d in dates])
    t_lo = int(np.searchsorted(years, 2012))
    t_hi = int(np.searchsorted(years, 2024))
    logging.info("时间窗口: %d 月 (2012-%d 到 2023-%d)", t_hi - t_lo, years[t_lo], years[t_hi - 1])

    # 空间窗口读取（float32: 144月 × Δj × Δi ≈ 250MB）
    with netCDF4.Dataset(NC_LOCAL) as ds:
        data = ds.variables["spei"][t_lo:t_hi, j0:j1, i0:i1]  # (n_month, Δj, Δi)
    logging.info("读入窗口数据: %s, 内存 %.1f MB", data.shape, data.nbytes / 2**20)
    vals = np.ma.filled(data[:, jj, ii], np.nan).astype(np.float64)  # (n_month, n_counties)
    del data

    m_years = years[t_lo:t_hi]
    m_months = months[t_lo:t_hi]
    gs_mask = np.isin(m_months, GROWING_MONTHS)
    rows = []
    for k, code in enumerate(cid):
        for y in YEARS:
            mask = (m_years == y)
            if mask.sum() < 6:
                continue
            ann = vals[mask, k]
            gs = vals[mask & gs_mask, k]
            rows.append({
                "区县代码": code,
                "spei_annual_mean": round(float(np.nanmean(ann)), 4) if np.isfinite(ann).mean() > 0.5 else np.nan,
                "spei_growing_season_mean": round(float(np.nanmean(gs)), 4) if np.isfinite(gs).mean() > 0.5 else np.nan,
                "year": y,
            })
    out = pd.DataFrame(rows)
    out = out.merge(panel[["区县代码", "省份", "城市", "区县"]], on="区县代码", how="left")
    out = out[["区县代码", "省份", "城市", "区县", "year", "spei_annual_mean", "spei_growing_season_mean"]]
    out = out.sort_values(["区县代码", "year"]).reset_index(drop=True)
    out.to_csv(OUT, index=False, encoding="utf-8-sig")
    logging.info("OK write %s (%d rows, %d counties)", OUT.name, len(out), out["区县代码"].nunique())
    print(out.head(3).to_string(index=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
