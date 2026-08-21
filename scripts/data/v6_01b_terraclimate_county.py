#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""v6 Step 1b：TerraClimate → 10 主产省县级年度气候面板（主方案）。

数据源：TerraClimate 4.6km 全球月网格（气候学标准再分析产品，免费无 key）。
选它而非 Open-Meteo ERA5 的原因：国内网络下 archive-api keyless 限流 ~3次/分钟
（1,196 县逐县拉取不可行）；TerraClimate 文件服务器可直连（11MB/年/变量）。

变量（与 v4 口径对齐）：
  (tmax+tmin)/2 → temp = 年均温 °C
  prec          → prec = 年降水量 mm
  srad          → sun  = 年均太阳辐射 MJ/m²/day（v4 的 sun 为日照时数，
                        此处为辐射量，XGBoost 尺度无关，论文中注明）

步骤：
  1. 下载 2012-2023 × {tmax,tmin,ppt,srad,pet} = 60 文件 (~5.5GB) → data/raw/terraclimate/
     注: TerraClimate 降水变量文件名为 ppt（prec 会 404）
  2. 网格中心点与县级多边形 sjoin（一次性权重映射，~150k 点）
  3. 每 (变量,年) 按月×县聚合 → 年值

输出: data/interim/terraclimate_county_yearly_v6.parquet
"""
import concurrent.futures as cf
import logging
import subprocess
import sys
import time
from pathlib import Path

import geopandas as gpd
import netCDF4
import numpy as np
import pandas as pd
from shapely.geometry import Point

PROJECT_ROOT = Path(__file__).resolve().parents[2]
COUNTIES = PROJECT_ROOT / "data" / "raw" / "gis_province" / "counties_10provinces_GS2024.geojson"
PANEL = PROJECT_ROOT / "data" / "interim" / "paper_panel_v6.parquet"
NC_DIR = PROJECT_ROOT / "data" / "raw" / "terraclimate"
OUT = PROJECT_ROOT / "data" / "interim" / "terraclimate_county_yearly_v6.parquet"

BASE = "https://climate.northwestknowledge.net/TERRACLIMATE-DATA/TerraClimate_{var}_{year}.nc"
VARS = ["tmax", "tmin", "ppt", "srad", "pet"]  # ppt = 降水 (prec 文件不存在)
YEARS = range(2012, 2024)
TIMEOUT = 120


def _curl_one(url: str, fp: Path) -> bool:
    """单文件 curl 断点续传，netCDF4 可打开才算完整。"""
    for attempt in range(20):
        subprocess.run(
            ["curl.exe", "-sL", "-C", "-", "--max-time", "900",
             "-o", str(fp), url], capture_output=True)
        try:
            with netCDF4.Dataset(fp):
                pass
            return True
        except Exception:
            logging.warning("%s 不完整 (%d MB, attempt %d), 续传重试",
                            fp.name, fp.stat().st_size // 1024 // 1024 if fp.exists() else 0, attempt + 1)
            time.sleep(3)
    return False


def download() -> None:
    """4 线程并行 curl -C - 断点续传下载（代理下大文件易断且速度 ~1MB/s）。"""
    NC_DIR.mkdir(parents=True, exist_ok=True)
    jobs: list[tuple[str, Path]] = []
    for var in VARS:
        for year in YEARS:
            fp = NC_DIR / f"TerraClimate_{var}_{year}.nc"
            if fp.exists():
                try:
                    with netCDF4.Dataset(fp):
                        pass
                    continue
                except Exception:
                    try:
                        fp.unlink()  # 损坏文件删除重下
                    except OSError:
                        logging.warning("%s 被占用, 稍后重试", fp.name)
                        time.sleep(5)
                        try:
                            fp.unlink()
                        except OSError:
                            pass
            jobs.append((BASE.format(var=var, year=year), fp))
    if not jobs:
        logging.info("全部已下载且完整")
        return
    logging.info("待下载 %d 文件 (4 线程并行)", len(jobs))
    with cf.ThreadPoolExecutor(max_workers=4) as ex:
        futs = {ex.submit(_curl_one, url, fp): fp.name for url, fp in jobs}
        for fut in cf.as_completed(futs):
            ok = fut.result()
            logging.info("完成 %s (%s)", futs[fut], "OK" if ok else "FAILED")


def build_cell_map() -> tuple[np.ndarray, np.ndarray, pd.DataFrame]:
    """网格中心点 → 县 映射（一次性）。返回 (lat_grid, lon_grid, cell→county df)。"""
    gdf = gpd.read_file(COUNTIES)
    gdf = gdf.to_crs("EPSG:4326")
    for col in ["adcode", "code", "区县代码", "id"]:
        if col in gdf.columns:
            gdf = gdf.rename(columns={col: "区县代码"})
            break
    if "区县代码" not in gdf.columns:
        raise KeyError(f"geojson 缺少区县代码列: {list(gdf.columns)}")

    with netCDF4.Dataset(NC_DIR / "TerraClimate_tmax_2012.nc") as ds:
        lat = ds.variables["lat"][:]
        lon = ds.variables["lon"][:]
    lon2d, lat2d = np.meshgrid(lon, lat)
    pts = gpd.GeoDataFrame(
        {"lon": lon2d.ravel(), "lat": lat2d.ravel()},
        geometry=[Point(x, y) for x, y in zip(lon2d.ravel(), lat2d.ravel())],
        crs="EPSG:4326",
    )
    joined = gpd.sjoin(pts, gdf[["区县代码", "geometry"]], how="inner", predicate="within")
    logging.info("网格-县匹配: %d 格点", len(joined))
    return lat, lon, joined


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s", datefmt="%H:%M:%S")
    download()
    lat, lon, joined = build_cell_map()

    joined["j"] = np.searchsorted(lat, joined["lat"])
    joined["i"] = np.searchsorted(lon, joined["lon"])
    panel = pd.read_parquet(PANEL)[["区县代码", "省份", "城市", "区县"]].drop_duplicates("区县代码")

    rows: list[dict] = []
    for var in VARS:
        for year in YEARS:
            fp = NC_DIR / f"TerraClimate_{var}_{year}.nc"
            with netCDF4.Dataset(fp) as ds:
                data = ds.variables[var][:]  # (12, j, i), masked
            vals = data[:, joined["j"].values, joined["i"].values]  # (12, n_cells)
            df = pd.DataFrame(vals.T, index=joined.index)
            df["区县代码"] = joined["区县代码"].values
            m = df.groupby("区县代码").mean().reset_index()
            for _, r in m.iterrows():
                rows.append({"区县代码": int(r["区县代码"]), "var": var, "year": year,
                             **{f"m{mth + 1}": float(r[mth + 1]) for mth in range(12)}})
            logging.info("聚合 %s %d", var, year)

    wide = pd.DataFrame(rows)
    annual = []
    for (cid, var), g in wide.groupby(["区县代码", "var"]):
        g = g.set_index("year")
        if var in ("ppt", "pet"):
            vals = g[[f"m{i}" for i in range(1, 13)]].sum(axis=1)
        else:
            vals = g[[f"m{i}" for i in range(1, 13)]].mean(axis=1)
        for y, v in vals.items():
            annual.append({"区县代码": int(cid), "year": y, var: float(v)})

    out = pd.DataFrame(annual).pivot_table(index=["区县代码", "year"], columns="var", values=None)
    out = out.reset_index()
    if isinstance(out.columns, pd.MultiIndex):
        # pivot 变量列按字母序 → 用第二级名还原列名，避免与 VARS 顺序不一致
        out.columns = [c[0] if c[1] == "" else c[1] for c in out.columns]
    out["temp"] = (out["tmax"] + out["tmin"]) / 2
    out["prec"] = out["ppt"]
    out["sun"] = out["srad"]
    out = out.merge(panel, on="区县代码", how="left")
    out = out[["区县代码", "province", "city", "county", "year", "temp", "prec", "sun"]]
    out = out.sort_values(["区县代码", "year"]).reset_index(drop=True)
    out.to_parquet(OUT, index=False)
    logging.info("✅ 写入 %s (%d 行, %d 县)", OUT, len(out), out["区县代码"].nunique())
    print(out.head(3).to_string(index=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
