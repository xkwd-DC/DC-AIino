#!/usr/bin/env python3
"""v5 Step 2：用多年 CLCD 逐年计算 10 粮食主产省地级市耕地面积比例。

对 2011-2023，每年读对应 CLCD 栅格，分块统计 148 个地级市的 cropland_ratio。
输出 city_cropland_ratio_yearly_v5.parquet（148 市 × 13 年 = 1924 行）。

逻辑复用 08c_calc_cropland_ratio_yearly.py，仅改输入 GeoJSON。
"""

import logging
import sys
from math import ceil
from pathlib import Path

import geopandas as gpd
import numpy as np
import pandas as pd
import rasterio
from rasterio.windows import Window, from_bounds
from rasterio.warp import transform_bounds

PROJECT_ROOT = Path(__file__).resolve().parents[2]
CLCD_DIR = PROJECT_ROOT / "data" / "raw" / "gis_cropland"
CITY_GEOJSON = PROJECT_ROOT / "data" / "raw" / "gis_province" / "cities_10provinces_GS2024.geojson"
OUT_PATH = PROJECT_ROOT / "data" / "interim" / "city_cropland_ratio_yearly_v5.parquet"

CROP_CLASS = 1
TILE_SIZE = 2048

YEARS = list(range(2011, 2024))


def count_cropland_in_window(
    src: rasterio.DatasetReader, window: Window
) -> tuple[int, int]:
    data = src.read(1, window=window)
    total = data.size
    crop = int(np.sum(data == CROP_CLASS))
    return total, crop


def count_cropland_for_city(
    province: str, city: str, geom, src: rasterio.DatasetReader
) -> dict:
    try:
        bounds_wgs84 = geom.bounds
        clcd_bounds = transform_bounds("EPSG:4326", src.crs, *bounds_wgs84)
        win = from_bounds(*clcd_bounds, transform=src.transform)
        col_off = int(win.col_off)
        row_off = int(win.row_off)
        width = int(win.width)
        height = int(win.height)

        total_pixels = 0
        cropland_pixels = 0
        n_col_tiles = max(1, ceil(width / TILE_SIZE))
        n_row_tiles = max(1, ceil(height / TILE_SIZE))

        for ti in range(n_row_tiles):
            for tj in range(n_col_tiles):
                tw = min(TILE_SIZE, height - ti * TILE_SIZE)
                th = min(TILE_SIZE, width - tj * TILE_SIZE)
                if tw <= 0 or th <= 0:
                    continue
                tile_win = Window(
                    col_off + tj * TILE_SIZE,
                    row_off + ti * TILE_SIZE,
                    th, tw,
                )
                t, c = count_cropland_in_window(src, tile_win)
                total_pixels += t
                cropland_pixels += c

        cropland_ratio = cropland_pixels / total_pixels if total_pixels > 0 else 0.0
        return {
            "province": province,
            "city": city,
            "cropland_ratio": round(cropland_ratio, 6),
            "total_pixels": total_pixels,
            "cropland_pixels": cropland_pixels,
        }
    except Exception as e:
        logging.warning("Failed for %s/%s: %s", province, city, e)
        return {
            "province": province,
            "city": city,
            "cropland_ratio": 0.0,
            "total_pixels": 0,
            "cropland_pixels": 0,
        }


def check_year_complete(year: int) -> bool:
    fname = f"CLCD_v01_{year}_albert.tif"
    fpath = CLCD_DIR / fname
    partial = CLCD_DIR / (fname + ".partial")
    if fpath.exists():
        return True
    if partial.exists():
        logging.warning("%s 的 .partial 存在（下载未完成）", year)
    return False


def load_cities() -> gpd.GeoDataFrame:
    """加载地级市 GeoJSON，返回带 province/city 列的 GeoDataFrame。"""
    gdf = gpd.read_file(CITY_GEOJSON)
    PROVINCE_ADCODE = {230000: "黑龙江", 410000: "河南", 370000: "山东",
                       220000: "吉林", 340000: "安徽", 430000: "湖南",
                       130000: "河北", 510000: "四川", 320000: "江苏", 420000: "湖北"}
    provinces = []
    for _, row in gdf.iterrows():
        parent = row.get("parent", {})
        if isinstance(parent, dict):
            adcode = parent.get("adcode", 0)
            provinces.append(PROVINCE_ADCODE.get(adcode, "?"))
        else:
            provinces.append("?")
    gdf = gdf.copy()
    gdf["province"] = provinces
    gdf["city"] = gdf["name"]
    gdf.set_crs("EPSG:4326", allow_override=True, inplace=True)
    logging.info("加载地级市边界: %d 个", len(gdf))
    return gdf


def main() -> int:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
        datefmt="%H:%M:%S",
    )

    logging.info("读取地级市边界...")
    gdf = load_cities()
    logging.info("加载 %d 个地级市", len(gdf))

    all_results = []
    completed_years = []
    skipped_years = []

    for year in YEARS:
        if not check_year_complete(year):
            skipped_years.append(year)
            continue

        fname = f"CLCD_v01_{year}_albert.tif"
        fpath = CLCD_DIR / fname
        logging.info("处理 CLCD %s (%s)...", year, fname)

        src = rasterio.open(fpath)
        logging.info("  shape=%s", src.shape)

        for _, city_row in gdf.iterrows():
            prov = city_row["province"]
            city = city_row["city"]
            result = count_cropland_for_city(prov, city, city_row.geometry, src)
            result["year"] = year
            all_results.append(result)

        src.close()
        completed_years.append(year)

    if skipped_years:
        logging.warning("以下年份未下载完成，已跳过: %s", skipped_years)

    if not all_results:
        logging.error("没有成功处理任何年份（CLCD 下载可能尚未完成）")
        logging.info("检查下载目录: %s", CLCD_DIR)
        return 1

    df = pd.DataFrame(all_results)
    df = df.sort_values(["year", "province", "city"]).reset_index(drop=True)
    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(OUT_PATH, index=False)
    logging.info("✅ 写入 %s (%d rows)", OUT_PATH, len(df))

    # Summary: year-over-year cropland change for 10 provinces aggregate
    print("\n=== 10 省 aggregate 耕地比例变化（2011 vs 2023） ===")
    df_sum = df.groupby(["year", "province"])[["cropland_ratio"]].mean().reset_index()
    d11 = df_sum[df_sum["year"] == 2011][["province", "cropland_ratio"]].set_index("province")
    d23 = df_sum[df_sum["year"] == 2023][["province", "cropland_ratio"]].set_index("province")
    if len(d11) > 0 and len(d23) > 0:
        merged = d11.join(d23, lsuffix="_2011", rsuffix="_2023")
        merged["Δ"] = merged["cropland_ratio_2023"] - merged["cropland_ratio_2011"]
        merged["Δ%"] = merged["Δ"] / merged["cropland_ratio_2011"] * 100
        merged = merged.sort_values("Δ", ascending=False)
        for idx, r in merged.iterrows():
            direction = "↑" if r["Δ"] > 0 else ("↓" if r["Δ"] < 0 else "→")
            print(f"  {idx:12s}  {r['cropland_ratio_2011']:.4f} → {r['cropland_ratio_2023']:.4f}  {direction} {r['Δ']:+.4f} ({r['Δ%']:+.1f}%)")

    print("\n已完成年份:", completed_years)
    print("跳过年份:", skipped_years)
    return 0


if __name__ == "__main__":
    sys.exit(main())
