#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""v6 Step 1d：TerraClimate 土壤水分（soil）→ 10 主产省县级年度面板。

背景
====
v6/v7 面板的 36/53 列里没有土壤模态。TerraClimate 同一套数据自带 ``soil``
变量（同源、同网格、同分辨率），当年只是没取，本次补上做「气象 vs 气象+土壤水分」
的双源异质对照。

⚠️ 口径提醒
===========
TerraClimate ``soil`` 是 **土壤水分（soil moisture, mm）**，即上層土壤含水量，
**不是**土壤质地 / 有机质 / pH 这类「土壤属性」。字段名一律写
``soil_moisture_*``，论文与 AIC 材料里不要称其为 soil properties。

实现
====
下载与聚合逻辑照抄既有脚本（避免重造轮子）：
  - 下载：``v6_01b_terraclimate_county.py::_curl_one``（curl -C - 断点续传 + 完整性校验）
  - 聚合：``v6_01c_terraclimate_agg_light.py::build_cell_map``（县治最近格点，O(log n)）

与 v6_01c 的唯一区别：变量换成 ``soil``，并按 12 个月值 → 年均值 /
生长季均值 / 最干月三个口径同时输出。

生长季窗口取 **4–9 月**，与 ``v6_09_build_seasonal_features.py`` 的 ``GS`` 口径
（``[3,4,5,6,7,8]``，0-based）严格对齐——否则「气象 + 土壤」双源对照里会混进
口径差，把口径差误读成模态贡献。

输入 : data/raw/terraclimate/TerraClimate_soil_2012..2023.nc（缺失则自动下载）
       data/interim/paper_panel_v7_prediction.parquet（取县治 lon/lat）
输出 : data/interim/terraclimate_soil_county_yearly.parquet
       data/interim/paper_panel_v7_soil.parquet（v7 副本 + soil 列）

用法 : python scripts/data/v6_01d_terraclimate_soil.py
       python scripts/data/v6_01d_terraclimate_soil.py --skip-download
"""
from __future__ import annotations

import argparse
import concurrent.futures as cf
import logging
import os
import subprocess
import sys
import time
from pathlib import Path

import netCDF4
import numpy as np
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[2]
PANEL_V7 = PROJECT_ROOT / "data" / "interim" / "paper_panel_v7_prediction.parquet"
NC_DIR = PROJECT_ROOT / "data" / "raw" / "terraclimate"
OUT_SOIL = PROJECT_ROOT / "data" / "interim" / "terraclimate_soil_county_yearly.parquet"
OUT_PANEL = PROJECT_ROOT / "data" / "interim" / "paper_panel_v7_soil.parquet"

VAR = "soil"  # TerraClimate 土壤水分（mm）
YEARS = range(2012, 2024)
GROWING_MONTHS = range(4, 10)  # 4–9 月，对齐 v6_09 的 GS（见模块 docstring）
BASE = "https://climate.northwestknowledge.net/TERRACLIMATE-DATA/TerraClimate_{var}_{year}.nc"

# ⚠️ 本机直连 climate.northwestknowledge.net 会超时（实测 curl 20s 无响应），
# 必须走本地代理。可用 DC_TERRACLIMATE_PROXY 覆盖；设为空串则强制直连。
PROXY = os.environ.get("DC_TERRACLIMATE_PROXY", "http://127.0.0.1:7890")

M_COLS = [f"m{m}" for m in range(1, 13)]
GS_COLS = [f"m{m}" for m in GROWING_MONTHS]  # m4..m9
OUT_COLS = ["soil_moisture_annual_mean", "soil_moisture_gs_mean", "soil_moisture_min_month"]


def _curl_cmd(url: str) -> list[str]:
    """统一的 curl 参数：静默、跟随跳转、断点续传、超时与重试都放宽。"""
    cmd = ["curl.exe", "-sSL", "-C", "-", "--max-time", "1800",
           "--connect-timeout", "30", "--retry", "5", "--retry-delay", "3", "-o"]
    if PROXY:
        cmd += ["--proxy", PROXY]
    return cmd


def _valid_nc(fp: Path) -> bool:
    """完整 = netCDF4 能打开、含 soil 变量、且**文件尾部的数据读得出来**。

    ⚠️ 不要用 HTTP 的 Content-Length 做判据。实测这台机器经 7890 代理拿到的
    HEAD `Content-Length` = 108,182,300，而完整 GET 下来的文件实际是
    109,319,042 字节（土壤 2012）——HEAD 的长度不可信，拿它做等值比较会把好文件
    判成"尺寸不符"并反复删掉重下。截断检测改用「读文件末端切片」：
    文件被截断时 HDF5 尾部元数据缺失，这一步必然抛异常。
    """
    if not fp.exists():
        return False
    try:
        with netCDF4.Dataset(fp) as ds:
            if VAR not in ds.variables:
                return False
            var = ds.variables[VAR]
            # 读最后一个时间步、右下角一个点：只取 1 个值，开销可忽略，但能证明文件完整
            np.asarray(var[-1, -1, -1])
        return True
    except Exception:
        return False


def _curl_one(url: str, fp: Path) -> bool:
    """单文件 curl 断点续传（沿用 v6_01b 的重试思路，补上代理与完整性校验）。"""
    for attempt in range(20):
        if _valid_nc(fp):
            return True
        subprocess.run(_curl_cmd(url) + [str(fp), url], capture_output=True)
        size_mb = fp.stat().st_size // 1024 // 1024 if fp.exists() else 0
        logging.warning("%s 校验未过 (%d MB, attempt %d)", fp.name, size_mb, attempt + 1)
        time.sleep(3)
    return False


def download() -> None:
    """4 线程并行下载缺失/损坏的 soil 文件（2012–2023，约 1.3 GB）。"""
    NC_DIR.mkdir(parents=True, exist_ok=True)
    jobs: list[tuple[str, Path]] = []
    for year in YEARS:
        fp = NC_DIR / f"TerraClimate_{VAR}_{year}.nc"
        url = BASE.format(var=VAR, year=year)
        if _valid_nc(fp):
            logging.info("%s 已存在且完整", fp.name)
            continue
        # 损坏文件先删，避免 curl -C - 在错的字节偏移上续传
        if fp.exists():
            try:
                fp.unlink()
            except OSError:
                logging.warning("%s 被占用（可能有别的进程正在写）, 稍后重试", fp.name)
                time.sleep(5)
                fp.unlink(missing_ok=True)
        jobs.append((url, fp))
    if not jobs:
        logging.info("soil 文件均已存在且完整")
        return
    logging.info("待下载 %d 个 soil 文件 (4 线程并行)", len(jobs))
    with cf.ThreadPoolExecutor(max_workers=4) as ex:
        futs = {ex.submit(_curl_one, url, fp): fp.name for url, fp in jobs}
        for fut in cf.as_completed(futs):
            ok = fut.result()
            logging.info("完成 %s (%s)", futs[fut], "OK" if ok else "FAILED")
            if not ok:
                raise SystemExit(f"下载失败且重试耗尽: {futs[fut]}")


def build_cell_map(panel: pd.DataFrame) -> tuple[np.ndarray, np.ndarray, np.ndarray, int, int, int, int]:
    """县治 lon/lat → TerraClimate 网格最近点索引 + 中国范围裁剪窗口。

    照抄 v6_01c 的实现：在升序 lat 数组上 searchsorted，再映射回原索引，
    以兼容 TerraClimate 自北向南的 lat 排列。返回窗口内相对索引以支持裁剪读取。
    """
    with netCDF4.Dataset(NC_DIR / f"TerraClimate_{VAR}_2012.nc") as ds:
        lat = np.asarray(ds.variables["lat"][:], dtype=float)
        lon = np.asarray(ds.variables["lon"][:], dtype=float)
    logging.info("grid: %d lat x %d lon (%.2f-%.2f / %.2f-%.2f)",
                 len(lat), len(lon), lat.min(), lat.max(), lon.min(), lon.max())
    assert lon[0] < lon[-1], "TerraClimate lon 应升序"
    nj, ni = len(lat), len(lon)

    plon, plat = panel["lon"].values.astype(float), panel["lat"].values.astype(float)
    desc = lat[0] > lat[-1]
    lat_asc = lat[::-1] if desc else lat
    j = np.clip(np.searchsorted(lat_asc, plat), 1, nj - 1)
    j = np.where(np.abs(lat_asc[j] - plat) <= np.abs(lat_asc[j - 1] - plat), j, j - 1)
    if desc:
        j = nj - 1 - j
    i = np.clip(np.searchsorted(lon, plon), 1, ni - 1)
    i = np.where(np.abs(lon[i] - plon) <= np.abs(lon[i - 1] - plon), i, i - 1)

    # 中国范围裁剪窗口（10 主产省 lat≈15-53, lon≈70-135，留边距）
    if desc:
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


def aggregate() -> pd.DataFrame:
    """逐 (年) 读取裁剪窗口 → 抽县列 → 12 个月值 → 年/生长季两个口径。"""
    panel = (
        pd.read_parquet(PANEL_V7)[["区县代码", "省份", "城市", "区县", "lon", "lat"]]
        .drop_duplicates("区县代码")
        .dropna(subset=["lon", "lat"])
        .reset_index(drop=True)
    )
    all_counties = pd.read_parquet(PANEL_V7)["区县代码"].nunique()
    logging.info("有坐标的县 %d / 面板全部县 %d（差值为缺坐标县，需在报告中列出）",
                 len(panel), all_counties)

    cid, jj, ii, j0, i0, j1, i1 = build_cell_map(panel)
    logging.info("cell map 完成: %d 县 (窗口 %d x %d)", len(cid), j1 - j0, i1 - i0)

    rows: list[pd.DataFrame] = []
    for year in YEARS:
        fp = NC_DIR / f"TerraClimate_{VAR}_{year}.nc"
        with netCDF4.Dataset(fp) as ds:
            data = np.ma.filled(ds.variables[VAR][:, j0:j1, i0:i1], np.nan)  # (12, Δj, Δi)
        vals = data[:, jj, ii].astype(np.float64)  # (12, n_counties) numpy 配对索引
        df = pd.DataFrame(vals.T, columns=M_COLS)
        df["区县代码"] = cid
        df["year"] = year
        rows.append(df)
        logging.info("读取 %s %d", VAR, year)
    wide = pd.concat(rows, ignore_index=True)

    out = pd.DataFrame({
        "区县代码": wide["区县代码"],
        "year": wide["year"],
        "soil_moisture_annual_mean": wide[M_COLS].mean(axis=1),
        "soil_moisture_gs_mean": wide[GS_COLS].mean(axis=1),
        "soil_moisture_min_month": wide[M_COLS].min(axis=1),
    })
    out = out.merge(panel[["区县代码", "省份", "城市", "区县"]], on="区县代码", how="left")
    out = out[["区县代码", "year"] + OUT_COLS + ["省份", "城市", "区县"]]
    return out.sort_values(["区县代码", "year"]).reset_index(drop=True)


def merge_into_panel(soil: pd.DataFrame) -> pd.DataFrame:
    """v7 副本 + soil 两列。不覆盖任何既有文件。"""
    panel = pd.read_parquet(PANEL_V7)
    out = panel.merge(
        soil[["区县代码", "year"] + OUT_COLS],
        left_on=["区县代码", "年份"], right_on=["区县代码", "year"], how="left",
    ).drop(columns="year")
    tmp = OUT_PANEL.with_suffix(".parquet.tmp")
    out.to_parquet(tmp, index=False)
    tmp.replace(OUT_PANEL)  # 原子替换，避免半个文件
    return out


def sanity(soil: pd.DataFrame) -> None:
    """量级合理性：华北/东北 vs 南方，以及年内/年际范围。"""
    logging.info("soil_moisture_annual 描述: min=%.1f p50=%.1f max=%.1f 非空=%d/%d",
                 soil["soil_moisture_annual_mean"].min(), soil["soil_moisture_annual_mean"].median(),
                 soil["soil_moisture_annual_mean"].max(),
                 soil["soil_moisture_annual_mean"].notna().sum(), len(soil))
    by_prov = (soil.groupby("省份")[["soil_moisture_annual_mean", "soil_moisture_gs_mean",
                                     "soil_moisture_min_month"]]
               .mean().sort_values("soil_moisture_annual_mean"))
    logging.info("各省均值:\n%s", by_prov.to_string())


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="TerraClimate soil → 县级年度面板")
    parser.add_argument("--skip-download", action="store_true", help="跳过下载，只用本地 nc")
    parser.add_argument("--agg-only", action="store_true", help="只聚合，不合并进面板")
    args = parser.parse_args(argv)
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:  # noqa: BLE001 —— Windows GBK 控制台兜底
            pass
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s",
                        datefmt="%H:%M:%S")

    if not args.skip_download:
        download()
    missing = [y for y in YEARS if not _valid_nc(NC_DIR / f"TerraClimate_{VAR}_{y}.nc")]
    if missing:
        raise SystemExit(f"缺少 soil 文件: {missing}（去掉 --skip-download 重跑）")

    soil = aggregate()
    sanity(soil)
    soil.to_parquet(OUT_SOIL, index=False)
    logging.info("写入 %s (%d 行, %d 县, %d 年)",
                 OUT_SOIL.name, len(soil), soil["区县代码"].nunique(), soil["year"].nunique())

    if not args.agg_only:
        merged = merge_into_panel(soil)
        n = merged["soil_moisture_annual_mean"].notna().sum()
        logging.info("写入 %s (%d 行, soil_moisture 非空 %d = %.1f%%)",
                     OUT_PANEL.name, len(merged), n, 100.0 * n / len(merged))
    return 0


if __name__ == "__main__":
    sys.exit(main())
