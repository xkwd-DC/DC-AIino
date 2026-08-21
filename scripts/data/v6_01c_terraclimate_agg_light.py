#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""v6 Step 1c：TerraClimate 县级年度气候聚合（轻量版，替代 v6_01b 的 sjoin）。

v6_01b 的 build_cell_map 构造全网格 840k 格点（1400 lon × 600 lat）做
geopandas sjoin，内存/时间开销大且易中断。本脚本用 panel 已有的县治
lon/lat 直接 searchsorted 到 0.05° 网格最近点：匹配 O(log n)、内存
<200MB、覆盖 100%（有坐标的县）。

口径差异：县治最近格点 vs 多边形内格点均值 —— TerraClimate 4.6km 网格
下差异可忽略，论文中注明"以县治最近格点代表县域气候"。

输出: data/interim/terraclimate_county_yearly_v6.parquet（与 v6_01b 同 schema）
"""
import logging
import sys
from pathlib import Path

import netCDF4
import numpy as np
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[2]
PANEL = PROJECT_ROOT / "data" / "interim" / "paper_panel_v6.parquet"
NC_DIR = PROJECT_ROOT / "data" / "raw" / "terraclimate"
OUT = PROJECT_ROOT / "data" / "interim" / "terraclimate_county_yearly_v6.parquet"

VARS = ["tmax", "tmin", "ppt", "srad", "pet"]
YEARS = range(2012, 2024)


def build_cell_map(panel: pd.DataFrame) -> tuple[np.ndarray, np.ndarray, np.ndarray, int, int, int, int]:
    """panel lon/lat → 网格最近点索引 + 中国范围裁剪窗口。

    返回 (区县代码, jj, ii, j0, i0, j1, i1)：jj/ii 为窗口内相对索引，
    [j0:j1, i0:i1] 为读文件时的裁剪切片（全网格 3.7 千万格点不能全读）。
    """
    with netCDF4.Dataset(NC_DIR / "TerraClimate_tmax_2012.nc") as ds:
        lat = np.asarray(ds.variables["lat"][:], dtype=float)
        lon = np.asarray(ds.variables["lon"][:], dtype=float)
    logging.info("grid: %d lat x %d lon (%.2f-%.2f / %.2f-%.2f)",
                 len(lat), len(lon), lat.min(), lat.max(), lon.min(), lon.max())
    assert lon[0] < lon[-1], "TerraClimate lon 应升序"
    nj, ni = len(lat), len(lon)

    plon, plat = panel["lon"].values.astype(float), panel["lat"].values.astype(float)
    # lat 可能降序（TerraClimate 从北极向南）：统一在升序数组上 searchsorted，再映射回原索引
    lat_asc = lat if lat[0] < lat[-1] else lat[::-1]
    j = np.clip(np.searchsorted(lat_asc, plat), 1, nj - 1)
    j = np.where(np.abs(lat_asc[j] - plat) <= np.abs(lat_asc[j - 1] - plat), j, j - 1)
    if lat[0] > lat[-1]:
        j = nj - 1 - j  # 映射回原始（降序）数组索引
    i = np.clip(np.searchsorted(lon, plon), 1, ni - 1)
    i = np.where(np.abs(lon[i] - plon) <= np.abs(lon[i - 1] - plon), i, i - 1)

    # 中国范围裁剪窗口（10 主产省 lat≈15-53, lon≈70-135，留边距）
    # 返回原始数组坐标的切片边界（j0<j1, i0<i1 恒成立）
    if lat[0] > lat[-1]:
        j0 = nj - 1 - int(np.searchsorted(lat_asc, 60.0))
        j1 = nj - 1 - int(np.searchsorted(lat_asc, 10.0))
    else:
        j0 = int(np.searchsorted(lat_asc, 10.0))
        j1 = int(np.searchsorted(lat_asc, 60.0))
    i0 = int(np.searchsorted(lon, 65.0))
    i1 = int(np.searchsorted(lon, 145.0))
    jj = j - j0  # 窗口行偏移（原始数组坐标）
    ii = i - i0
    assert jj.min() >= 0 and jj.max() < j1 - j0 and ii.min() >= 0 and ii.max() < i1 - i0, \
        "窗口外有县点，检查裁剪范围"
    return panel["区县代码"].values.astype(int), jj, ii, j0, i0, j1, i1


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s", datefmt="%H:%M:%S")
    panel = pd.read_parquet(PANEL)[["区县代码", "省份", "城市", "区县", "lon", "lat"]] \
        .drop_duplicates("区县代码").dropna(subset=["lon", "lat"]).reset_index(drop=True)
    logging.info("counties with lon/lat: %d", len(panel))

    cid, jj, ii, j0, i0, j1, i1 = build_cell_map(panel)
    logging.info("cell map done: %d counties mapped (window %d x %d)", len(cid), j1 - j0, i1 - i0)

    # 逐 (var, year) 读取裁剪窗口 → 窗口内 numpy 配对索引抽取县列
    wide_rows: list[pd.DataFrame] = []
    for var in VARS:
        for year in YEARS:
            fp = NC_DIR / f"TerraClimate_{var}_{year}.nc"
            with netCDF4.Dataset(fp) as ds:
                data = np.ma.filled(ds.variables[var][:, j0:j1, i0:i1], np.nan)  # (12, Δj, Δi) float32
            vals = data[:, jj, ii].astype(np.float64)  # (12, n_counties) numpy 配对语义
            df = pd.DataFrame(vals.T, columns=[f"m{m + 1}" for m in range(12)])
            df["区县代码"] = cid
            df["var"] = var
            df["year"] = year
            wide_rows.append(df)
        logging.info("agg %s x12 done", var)
    wide = pd.concat(wide_rows, ignore_index=True)

    # 年度汇总: ppt/pet 按月求和, 其余按月均值
    m_cols = [f"m{m + 1}" for m in range(12)]
    parts = []
    for var in VARS:
        sub = wide[wide["var"] == var].drop(columns="var")
        if var in ("ppt", "pet"):
            annual = sub.groupby(["区县代码", "year"])[m_cols].sum().reset_index()
        else:
            annual = sub.groupby(["区县代码", "year"])[m_cols].mean().reset_index()
        annual["var"] = var
        parts.append(annual)
    annual = pd.concat(parts, ignore_index=True)

    # 长表 → 变量宽表（按 var 展开；先 pivot 出各 var 的年度均值）
    out = None
    for var in VARS:
        a = annual[annual["var"] == var][["区县代码", "year"]].copy()
        vals = annual[annual["var"] == var][m_cols]
        a[var] = vals.sum(axis=1).values if var in ("ppt", "pet") else vals.mean(axis=1).values
        out = a if out is None else out.merge(a, on=["区县代码", "year"], how="outer")
    out["temp"] = (out["tmax"] + out["tmin"]) / 2
    out["prec"] = out["ppt"]
    out["sun"] = out["srad"]
    out = out.merge(panel[["区县代码", "省份", "城市", "区县"]], on="区县代码", how="left")
    out = out[["区县代码", "省份", "城市", "区县", "year", "temp", "prec", "sun"]]
    out = out.sort_values(["区县代码", "year"]).reset_index(drop=True)
    out.to_parquet(OUT, index=False)
    logging.info("OK write %s (%d rows, %d counties)", OUT.name, len(out), out["区县代码"].nunique())
    print(out.head(3).to_string(index=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
