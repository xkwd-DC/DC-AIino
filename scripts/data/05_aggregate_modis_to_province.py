"""MODIS NDVI/LST → 省域月度面板。

输入：
  /mnt/data/DC/modis_ndvi/<year>/.../*_NDVI_doyYYYYDDD*.tif    （MOD13A3，月度）
  /mnt/data/DC/modis_lst/<year>/.../*_LST_Day_1km_doyYYYYDDD*.tif  （MOD11A2，8 天）
  /mnt/data/DC/modis_lst/<year>/.../*_LST_Night_1km_doyYYYYDDD*.tif
  data/raw/gis_province/tianditu/province_2024_GS2024-0650.geojson

输出：data/interim/modis_province_monthly.parquet
契约：docs/08_数据采集任务_石灵子.md §3.2，由 scripts/data/validate_modis_panel.py 校验

策略：
  - NDVI 月度直接 zonal_stats（per province × 12 月）
  - LST 8 天→月度：把每月 4 个 8-day 平均（按 DOY 起始日落到月份），再 zonal_stats
  - **没做耕地 mask**——v0 用全省域均值，后续可加 CLCD 30m 掩膜
  - 单位：NDVI raw×0.0001（[-0.2, 1.0]）；LST raw×0.02 → K（[273, 320]）

CLI:
    python scripts/data/05_aggregate_modis_to_province.py --year 2022
    python scripts/data/05_aggregate_modis_to_province.py --years 2011-2023  # 多年（需各年 MODIS 已下）
"""
from __future__ import annotations

import argparse
import logging
import re
import sys
from collections import defaultdict
from datetime import date, timedelta
from pathlib import Path

import geopandas as gpd
import numpy as np
import pandas as pd
import rasterio
from rasterstats import zonal_stats
from tqdm import tqdm

PROJECT_ROOT = Path(__file__).resolve().parents[2]
MODIS_NDVI_ROOT = Path("/mnt/data/DC/modis_ndvi")
MODIS_LST_ROOT = Path("/mnt/data/DC/modis_lst")
PROVINCE_GEOJSON = PROJECT_ROOT / "data" / "raw" / "gis_province" / "tianditu" / "province_2024_GS2024-0650.geojson"
DEFAULT_OUT = PROJECT_ROOT / "data" / "interim" / "modis_province_monthly.parquet"

NDVI_SCALE = 0.0001
LST_SCALE = 0.02
NDVI_NODATA = -3000
LST_NODATA = 0  # MOD11A2 LST nodata 用 0

DOY_RE = re.compile(r"doy(\d{4})(\d{3})")


def doy_to_date(year: int, doy: int) -> date:
    return date(year, 1, 1) + timedelta(days=doy - 1)


def list_tifs(root: Path, year: int, pattern: str) -> list[Path]:
    """递归找指定 year 子目录下匹配的 TIF。"""
    year_dir = root / str(year)
    if not year_dir.exists():
        return []
    return sorted(year_dir.rglob(pattern))


def load_provinces() -> gpd.GeoDataFrame:
    gdf = gpd.read_file(PROVINCE_GEOJSON)
    gdf = gdf[gdf["name"] != "境界线"].copy()
    gdf = gdf[~gdf["name"].isin({"香港特别行政区", "澳门特别行政区", "台湾省"})].copy()
    gdf.set_crs("EPSG:4326", allow_override=True, inplace=True)
    gdf["province_code"] = gdf["gb"].str[-6:]
    return gdf


def zonal_for_tif(tif: Path, gdf: gpd.GeoDataFrame, scale: float, nodata: int) -> pd.DataFrame:
    """单 TIF × 31 省 → mean / std / valid_count。"""
    stats = zonal_stats(
        gdf.geometry,
        str(tif),
        stats=["mean", "std", "count"],
        nodata=nodata,
        all_touched=False,
        geojson_out=False,
    )
    rows = []
    for prov_row, s in zip(gdf.itertuples(index=False), stats):
        mean_raw = s["mean"]
        std_raw = s["std"]
        rows.append({
            "province_code": prov_row.province_code,
            "province": prov_row.name,
            "mean": mean_raw * scale if mean_raw is not None else None,
            "std": std_raw * scale if std_raw is not None else None,
            "valid_count": int(s["count"]) if s["count"] is not None else 0,
        })
    return pd.DataFrame(rows)


def aggregate_ndvi(year: int, gdf: gpd.GeoDataFrame) -> pd.DataFrame:
    files = list_tifs(MODIS_NDVI_ROOT, year, "*_NDVI_doy*.tif")
    if not files:
        logging.warning("%s 没找到 NDVI TIF", year)
        return pd.DataFrame()
    logging.info("NDVI %s: %d 月度文件", year, len(files))

    out = []
    for f in tqdm(files, desc=f"NDVI {year}"):
        m = DOY_RE.search(f.name)
        if not m:
            logging.warning("跳过未识别命名 %s", f.name)
            continue
        file_year, doy = int(m.group(1)), int(m.group(2))
        month = doy_to_date(file_year, doy).month
        df = zonal_for_tif(f, gdf, NDVI_SCALE, NDVI_NODATA)
        df["year"] = file_year
        df["month"] = month
        df = df.rename(columns={"mean": "ndvi_mean", "std": "ndvi_std", "valid_count": "ndvi_valid_count"})
        out.append(df)
    return pd.concat(out, ignore_index=True) if out else pd.DataFrame()


def aggregate_lst(year: int, gdf: gpd.GeoDataFrame, band: str) -> pd.DataFrame:
    """LST 8 天→月度：先 zonal_stats 每个 8-day TIF，再按月份分组求均值。"""
    pattern = f"*LST_{band}_1km_doy*.tif"
    files = list_tifs(MODIS_LST_ROOT, year, pattern)
    if not files:
        logging.warning("%s 没找到 LST %s TIF", year, band)
        return pd.DataFrame()
    logging.info("LST %s %s: %d 个 8-day 文件", band, year, len(files))

    rows_per_granule = []
    for f in tqdm(files, desc=f"LST_{band} {year}"):
        m = DOY_RE.search(f.name)
        if not m:
            continue
        file_year, doy = int(m.group(1)), int(m.group(2))
        # 跳过跨年 granule（e.g. doy 2021361 落到 2021 那个月）
        if file_year != year:
            continue
        granule_date = doy_to_date(file_year, doy)
        month = granule_date.month
        df = zonal_for_tif(f, gdf, LST_SCALE, LST_NODATA)
        df["year"] = file_year
        df["month"] = month
        df["doy"] = doy
        rows_per_granule.append(df)

    if not rows_per_granule:
        return pd.DataFrame()
    all_granules = pd.concat(rows_per_granule, ignore_index=True)

    # 月度：每个 (province, year, month) 取 8-day 均值
    monthly = (
        all_granules.dropna(subset=["mean"])
        .groupby(["province_code", "province", "year", "month"], as_index=False)
        .agg(mean=("mean", "mean"), std=("std", "mean"), valid_count=("valid_count", "sum"))
    )
    return monthly


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="MODIS NDVI/LST → 省域月度面板")
    parser.add_argument("--year", type=int)
    parser.add_argument("--years", type=str, help="年份范围 START-END")
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--verbose", "-v", action="store_true")
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
        datefmt="%H:%M:%S",
    )

    if args.year is not None:
        years = [args.year]
    elif args.years:
        lo, hi = args.years.split("-", 1)
        years = list(range(int(lo), int(hi) + 1))
    else:
        years = list(range(2011, 2024))

    gdf = load_provinces()
    logging.info("加载 %d 个内陆省", len(gdf))

    all_rows = []
    for year in years:
        ndvi_df = aggregate_ndvi(year, gdf)
        lst_day_df = aggregate_lst(year, gdf, "Day")
        lst_night_df = aggregate_lst(year, gdf, "Night")

        if ndvi_df.empty:
            logging.warning("%s 跳过（无 NDVI 数据）", year)
            continue

        merged = ndvi_df[["province_code", "province", "year", "month",
                          "ndvi_mean", "ndvi_std", "ndvi_valid_count"]]

        if not lst_day_df.empty:
            lst_day = lst_day_df.rename(
                columns={"mean": "lst_day_mean_k", "std": "lst_day_std_k", "valid_count": "lst_day_valid_count"}
            )
            merged = merged.merge(
                lst_day[["province_code", "year", "month", "lst_day_mean_k", "lst_day_std_k", "lst_day_valid_count"]],
                on=["province_code", "year", "month"], how="left",
            )
        else:
            merged["lst_day_mean_k"] = None
            merged["lst_day_std_k"] = None
            merged["lst_day_valid_count"] = 0

        if not lst_night_df.empty:
            lst_night = lst_night_df.rename(
                columns={"mean": "lst_night_mean_k", "std": "lst_night_std_k", "valid_count": "lst_night_valid_count"}
            )
            merged = merged.merge(
                lst_night[["province_code", "year", "month", "lst_night_mean_k", "lst_night_std_k", "lst_night_valid_count"]],
                on=["province_code", "year", "month"], how="left",
            )
        else:
            merged["lst_night_mean_k"] = None
            merged["lst_night_std_k"] = None
            merged["lst_night_valid_count"] = 0

        # valid_pixel_ratio：以 NDVI 为基准（per 省域 1km 像元总数）
        max_count = max(int(merged["ndvi_valid_count"].max() or 0), 1)
        merged["valid_pixel_ratio"] = merged["ndvi_valid_count"] / max_count
        all_rows.append(merged)

    if not all_rows:
        logging.error("无任何年份成功聚合")
        return 1

    final = pd.concat(all_rows, ignore_index=True).sort_values(["province_code", "year", "month"]).reset_index(drop=True)

    # 输出列对齐 doc 08 §3.2
    cols = [
        "province_code", "province", "year", "month",
        "ndvi_mean", "ndvi_std",
        "lst_day_mean_k", "lst_night_mean_k",
        "valid_pixel_ratio",
    ]
    extras = [c for c in final.columns if c not in cols]
    final_out = final[cols + extras]

    args.out.parent.mkdir(parents=True, exist_ok=True)
    final_out.to_parquet(args.out, index=False)
    logging.info("✅ 写入 %s（%d 行 × %d 列）", args.out, len(final_out), len(final_out.columns))

    print()
    print("=== 抽样（河南 2022） ===")
    h = final_out[(final_out["province_code"] == "410000") & (final_out["year"] == 2022)]
    print(h[["month", "ndvi_mean", "ndvi_std", "lst_day_mean_k", "lst_night_mean_k", "valid_pixel_ratio"]].to_string(index=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
