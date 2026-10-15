#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""v6 Step 1d：TerraClimate 土壤水分 → 县级年度面板（给面板补一路独立地表水分模态）。

⚠️ 语义：TerraClimate 的 `soil` 是 **土壤水分（soil moisture, mm）**，是月度状态量，
   不是土壤质地/有机质/土壤类型。对外表述一律用「土壤水分」，不要写成「土壤属性」。

口径：与 `v6_01c_terraclimate_agg_light.py` 保持一致 —— **县治最近格点**代表县域，
不改成多边形内均值（否则与面板里已有的 temp/prec/sun 口径不可比）。

生长季：沿用 `v6_09_build_seasonal_features.py` 的 `GS = 4-9 月`。

输出：`data/interim/terraclimate_soil_county_yearly.parquet`
    columns = 区县代码, 省份, 城市, 区县, year,
              soil_moisture_annual_mean, soil_moisture_gs_mean, soil_moisture_min_month

用法：
    python scripts/data/v6_01d_terraclimate_soil_county.py            # 下载 + 聚合
    python scripts/data/v6_01d_terraclimate_soil_county.py --no-download
"""

from __future__ import annotations

import argparse
import concurrent.futures as cf
import logging
import subprocess
import sys
import time
from pathlib import Path

import netCDF4
import numpy as np
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[2]
PANEL = PROJECT_ROOT / "data" / "interim" / "paper_panel_v7_prediction.parquet"
NC_DIR = PROJECT_ROOT / "data" / "raw" / "terraclimate"
OUT = PROJECT_ROOT / "data" / "interim" / "terraclimate_soil_county_yearly.parquet"

VAR = "soil"
YEARS = range(2012, 2024)
GS_MONTHS = [4, 5, 6, 7, 8, 9]  # 生长季（1-based 月份），口径见 v6_09
BASE = "https://climate.northwestknowledge.net/TERRACLIMATE-DATA/TerraClimate_{var}_{year}.nc"
GRID_REF = NC_DIR / "TerraClimate_tmax_2012.nc"  # 借已有文件取网格坐标


def _is_readable(fp: Path) -> bool:
    """文件存在、非空、且能被 netCDF4 打开并含目标变量才算完整。"""
    if not fp.exists() or fp.stat().st_size == 0:
        return False
    try:
        with netCDF4.Dataset(fp) as ds:
            return VAR in ds.variables
    except Exception:
        return False


def _curl_one(url: str, fp: Path) -> bool:
    """单文件 curl 断点续传；最多 20 轮，每轮后验证可打开性。"""
    for attempt in range(20):
        subprocess.run(
            ["curl.exe", "-sL", "-C", "-", "--max-time", "900", "-o", str(fp), url],
            capture_output=True,
        )
        if _is_readable(fp):
            return True
        logging.warning("%s 不完整 (%.1f MB, 第 %d 次尝试)，续传重试",
                        fp.name, fp.stat().st_size / 1e6 if fp.exists() else 0, attempt + 1)
        time.sleep(3)
    return False


def download() -> None:
    """4 线程并行下载 12 个 soil 文件。0 字节残留一律删掉重下。"""
    NC_DIR.mkdir(parents=True, exist_ok=True)
    jobs: list[tuple[str, Path]] = []
    for year in YEARS:
        fp = NC_DIR / f"TerraClimate_{VAR}_{year}.nc"
        if _is_readable(fp):
            continue
        if fp.exists():
            logging.info("删除残留损坏文件 %s (%.0f 字节)", fp.name, fp.stat().st_size)
            try:
                fp.unlink()
            except OSError:
                logging.warning("%s 被占用，跳过本次", fp.name)
                continue
        jobs.append((BASE.format(var=VAR, year=year), fp))
    if not jobs:
        logging.info("12 个 soil 文件已就绪且完整")
        return
    logging.info("待下载 %d 个文件（4 线程并行，合计约 %.1f GB）",
                 len(jobs), len(jobs) * 0.103)
    with cf.ThreadPoolExecutor(max_workers=4) as ex:
        futs = {ex.submit(_curl_one, url, fp): fp.name for url, fp in jobs}
        for fut in cf.as_completed(futs):
            logging.info("完成 %s (%s)", futs[fut], "OK" if fut.result() else "FAILED")


def build_cell_map(panel: pd.DataFrame):
    """县治 lon/lat → 网格最近点索引 + 中国范围裁剪窗口。

    与 `v6_01c` 完全同一套实现：searchsorted 最近点 + 裁剪窗口，
    避免 v6_01b 那种全网格 sjoin 的内存开销。
    """
    with netCDF4.Dataset(GRID_REF) as ds:
        lat = np.asarray(ds.variables["lat"][:], dtype=float)
        lon = np.asarray(ds.variables["lon"][:], dtype=float)
    logging.info("grid: %d lat x %d lon (%.2f~%.2f / %.2f~%.2f)",
                 len(lat), len(lon), lat.min(), lat.max(), lon.min(), lon.max())
    assert lon[0] < lon[-1], "TerraClimate lon 应升序"
    nj, ni = len(lat), len(lon)

    plon, plat = panel["lon"].values.astype(float), panel["lat"].values.astype(float)
    lat_asc = lat if lat[0] < lat[-1] else lat[::-1]
    j = np.clip(np.searchsorted(lat_asc, plat), 1, nj - 1)
    j = np.where(np.abs(lat_asc[j] - plat) <= np.abs(lat_asc[j - 1] - plat), j, j - 1)
    if lat[0] > lat[-1]:
        j = nj - 1 - j
    i = np.clip(np.searchsorted(lon, plon), 1, ni - 1)
    i = np.where(np.abs(lon[i] - plon) <= np.abs(lon[i - 1] - plon), i, i - 1)

    if lat[0] > lat[-1]:
        j0 = nj - 1 - int(np.searchsorted(lat_asc, 60.0))
        j1 = nj - 1 - int(np.searchsorted(lat_asc, 10.0))
    else:
        j0 = int(np.searchsorted(lat_asc, 10.0))
        j1 = int(np.searchsorted(lat_asc, 60.0))
    i0 = int(np.searchsorted(lon, 65.0))
    i1 = int(np.searchsorted(lon, 145.0))
    jj, ii = j - j0, i - i0
    assert jj.min() >= 0 and jj.max() < j1 - j0 and ii.min() >= 0 and ii.max() < i1 - i0, \
        "窗口外有县点，检查裁剪范围"
    return panel["区县代码"].values.astype(int), jj, ii, j0, i0, j1, i1


def main() -> int:
    parser = argparse.ArgumentParser(description="TerraClimate 土壤水分 → 县级年度面板")
    parser.add_argument("--no-download", action="store_true", help="跳过下载，只用本地已有 nc")
    parser.add_argument("--out", type=Path, default=OUT)
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s", datefmt="%H:%M:%S")
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except AttributeError:  # pragma: no cover
        pass

    if not args.no_download:
        download()

    panel = (pd.read_parquet(PANEL)[["区县代码", "省份", "城市", "区县", "lon", "lat"]]
             .drop_duplicates("区县代码").dropna(subset=["lon", "lat"]).reset_index(drop=True))
    logging.info("有经纬度的县: %d", len(panel))
    cid, jj, ii, j0, i0, j1, i1 = build_cell_map(panel)
    logging.info("格点映射完成: %d 县（窗口 %d × %d）", len(cid), j1 - j0, i1 - i0)

    m_cols = [f"m{m}" for m in range(1, 13)]
    monthly = []
    for year in YEARS:
        fp = NC_DIR / f"TerraClimate_{VAR}_{year}.nc"
        with netCDF4.Dataset(fp) as ds:
            data = np.ma.filled(ds.variables[VAR][:, j0:j1, i0:i1], np.nan)
        vals = data[:, jj, ii].astype(np.float64)  # (12, n_counties)
        df = pd.DataFrame(vals.T, columns=m_cols)
        df["区县代码"] = cid
        df["year"] = year
        monthly.append(df)
        logging.info("读取 %s %d（县均年值 %.1f mm）", VAR, year, float(np.nanmean(vals)))
    monthly = pd.concat(monthly, ignore_index=True)

    gs_cols = [f"m{m}" for m in GS_MONTHS]
    monthly["soil_moisture_annual_mean"] = monthly[m_cols].mean(axis=1)
    monthly["soil_moisture_gs_mean"] = monthly[gs_cols].mean(axis=1)
    monthly["soil_moisture_min_month"] = monthly[m_cols].min(axis=1)
    out = monthly[["区县代码", "year", "soil_moisture_annual_mean",
                   "soil_moisture_gs_mean", "soil_moisture_min_month"]] \
        .merge(panel[["区县代码", "省份", "城市", "区县"]], on="区县代码", how="left") \
        .sort_values(["区县代码", "year"]).reset_index(drop=True)

    args.out.parent.mkdir(parents=True, exist_ok=True)
    out.to_parquet(args.out, index=False)
    logging.info("✅ 写入 %s（%d 行，%d 县 × %d 年）",
                 args.out.name, len(out), out["区县代码"].nunique(), out["year"].nunique())
    print(out.head(4).to_string(index=False))
    print("\n值域检查（mm）:")
    print(out[["soil_moisture_annual_mean", "soil_moisture_gs_mean", "soil_moisture_min_month"]]
          .describe().round(2).to_string())
    return 0


if __name__ == "__main__":
    sys.exit(main())
