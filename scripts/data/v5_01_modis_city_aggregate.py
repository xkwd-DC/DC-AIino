"""MODIS NDVI/LST → 10 粮食主产省地级市月度面板（v5）。

复用 05_aggregate_modis_to_province.py 的聚合逻辑，
只把输入 GeoJSON 从省级换成 10 省 148 地级市边界。

输入：
  /mnt/data/DC/modis_ndvi/<year>/.../*_NDVI_doy*.tif
  /mnt/data/DC/modis_lst/<year>/.../*_LST_{Day,Night}_1km_doy*.tif
  data/raw/gis_province/cities_10provinces_GS2024.geojson

输出：data/interim/modis_city_monthly_v5.parquet

CLI:
    python scripts/data/v5_01_modis_city_aggregate.py --year 2022
    python scripts/data/v5_01_modis_city_aggregate.py --years 2011-2023
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
CITY_GEOJSON = PROJECT_ROOT / "data" / "raw" / "gis_province" / "cities_10provinces_GS2024.geojson"
DEFAULT_OUT = PROJECT_ROOT / "data" / "interim" / "modis_city_monthly_v5.parquet"

NDVI_SCALE = 0.0001
LST_SCALE = 0.02
NDVI_NODATA = -3000
LST_NODATA = 0  # MOD11A2 LST nodata 用 0

DOY_RE = re.compile(r"doy(\d{4})(\d{3})")

# 10 粮食主产省 adcode（从 GeoJSON parent.adcode 匹配）
# adcode = 省级 code（前两位跟 00 后缀不同）
TEN_PROVINCE_ADCODES = {230000, 410000, 370000, 220000, 340000,
                        430000, 130000, 510000, 320000, 420000}

# adcode → 省名
PROVINCE_NAME = {
    230000: "黑龙江", 410000: "河南", 370000: "山东",
    220000: "吉林", 340000: "安徽", 430000: "湖南",
    130000: "河北", 510000: "四川", 320000: "江苏", 420000: "湖北",
}


def doy_to_date(year: int, doy: int) -> date:
    return date(year, 1, 1) + timedelta(days=doy - 1)


def list_tifs(root: Path, year: int, pattern: str) -> list[Path]:
    year_dir = root / str(year)
    if not year_dir.exists():
        return []
    return sorted(year_dir.rglob(pattern))


def load_cities() -> gpd.GeoDataFrame:
    """加载 10 省 148 地级市 GeoJSON，返回带 province/city 列的 GeoDataFrame。"""
    gdf = gpd.read_file(CITY_GEOJSON)
    # geopandas 已将 GeoJSON properties 展开为列
    # 列：adcode, name, center, centroid, childrenNum, level, parent( dict ), subFeatureIndex, acroutes
    province_list = []
    for _, row in gdf.iterrows():
        parent = row["parent"]
        if isinstance(parent, dict):
            parent_adcode = parent.get("adcode", 0)
            province_list.append(PROVINCE_NAME.get(parent_adcode, "?"))
        else:
            province_list.append("?")

    gdf = gdf.copy()
    gdf["province"] = province_list
    gdf["city"] = gdf["name"]
    gdf.set_crs("EPSG:4326", allow_override=True, inplace=True)
    gdf["city_id"] = gdf["province"] + "_" + gdf["city"]
    logging.info("加载地级市边界: %d 个（10 省）", len(gdf))
    return gdf


def zonal_for_tif(tif: Path, gdf: gpd.GeoDataFrame, scale: float, nodata: int) -> pd.DataFrame:
    """单 TIF × 148 地级市 → mean / std / valid_count。"""
    stats = zonal_stats(
        gdf.geometry,
        str(tif),
        stats=["mean", "std", "count"],
        nodata=nodata,
        all_touched=False,
        geojson_out=False,
    )
    rows = []
    for city_row, s in zip(gdf.itertuples(index=False), stats):
        mean_raw = s["mean"]
        std_raw = s["std"]
        rows.append({
            "province": city_row.province,
            "city": city_row.city,
            "city_id": city_row.city_id,
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

    monthly = (
        all_granules.dropna(subset=["mean"])
        .groupby(["province", "city", "city_id", "year", "month"], as_index=False)
        .agg(mean=("mean", "mean"), std=("std", "mean"), valid_count=("valid_count", "sum"))
    )
    return monthly


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="MODIS NDVI/LST → 地级市月度面板 (v5)")
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

    gdf = load_cities()
    logging.info("加载 %d 个地级市", len(gdf))

    all_rows = []
    for year in years:
        ndvi_df = aggregate_ndvi(year, gdf)
        lst_day_df = aggregate_lst(year, gdf, "Day")
        lst_night_df = aggregate_lst(year, gdf, "Night")

        if ndvi_df.empty:
            logging.warning("%s 跳过（无 NDVI 数据）", year)
            continue

        merged = ndvi_df[["province", "city", "city_id", "year", "month",
                          "ndvi_mean", "ndvi_std", "ndvi_valid_count"]]

        if not lst_day_df.empty:
            lst_day = lst_day_df.rename(
                columns={"mean": "lst_day_mean_k", "std": "lst_day_std_k", "valid_count": "lst_day_valid_count"}
            )
            merged = merged.merge(
                lst_day[["city_id", "year", "month", "lst_day_mean_k", "lst_day_std_k", "lst_day_valid_count"]],
                on=["city_id", "year", "month"], how="left",
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
                lst_night[["city_id", "year", "month", "lst_night_mean_k", "lst_night_std_k", "lst_night_valid_count"]],
                on=["city_id", "year", "month"], how="left",
            )
        else:
            merged["lst_night_mean_k"] = None
            merged["lst_night_std_k"] = None
            merged["lst_night_valid_count"] = 0

        max_count = max(int(merged["ndvi_valid_count"].max() or 0), 1)
        merged["valid_pixel_ratio"] = merged["ndvi_valid_count"] / max_count
        all_rows.append(merged)

    if not all_rows:
        logging.error("无任何年份成功聚合")
        return 1

    final = pd.concat(all_rows, ignore_index=True).sort_values(["province", "city", "year", "month"]).reset_index(drop=True)

    cols = [
        "province", "city", "city_id", "year", "month",
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
    print("=== 抽样（河南 郑州市 2022） ===")
    sample = final_out[(final_out["province"] == "河南") & (final_out["city"] == "郑州市") & (final_out["year"] == 2022)]
    if not sample.empty:
        print(sample[["month", "ndvi_mean", "ndvi_std", "lst_day_mean_k", "lst_night_mean_k", "valid_pixel_ratio"]].to_string(index=False))
    else:
        print("（无抽样数据）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
