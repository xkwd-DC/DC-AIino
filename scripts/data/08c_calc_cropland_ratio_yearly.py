#!/usr/bin/env python3
"""8c Step 1：用多年 CLCD 逐年计算各省耕地面积比例。

对 2011-2023，每年读对应 CLCD 栅格，分块统计各省 cropland_ratio。
输出 province_cropland_ratio_yearly.parquet（31 省 × 13 年 = 403 行）。

比起 05b_calc_cropland_ratio.py，多了 year 维度。
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
PROVINCE_GEOJSON = PROJECT_ROOT / "data" / "raw" / "gis_province" / "tianditu" / "province_2024_GS2024-0650.geojson"
OUT_PATH = PROJECT_ROOT / "data" / "interim" / "province_cropland_ratio_yearly.parquet"
# Also write static version (2022-based) for comparison
OUT_STATIC = PROJECT_ROOT / "data" / "interim" / "province_cropland_ratio.parquet"

CROP_CLASS = 1
SKIP_NAMES = {"香港特别行政区", "澳门特别行政区", "台湾省", "境界线"}
TILE_SIZE = 2048  # 每块 ~4MB

YEARS = list(range(2011, 2024))


def count_cropland_in_window(
    src: rasterio.DatasetReader, window: Window
) -> tuple[int, int]:
    data = src.read(1, window=window)
    total = data.size
    crop = int(np.sum(data == CROP_CLASS))
    return total, crop


def count_cropland_for_province(
    name: str, geom, src: rasterio.DatasetReader
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
            "province": name,
            "cropland_ratio": round(cropland_ratio, 6),
            "total_pixels": total_pixels,
            "cropland_pixels": cropland_pixels,
        }
    except Exception as e:
        logging.warning("Failed for %s: %s", name, e)
        return {
            "province": name,
            "cropland_ratio": 0.0,
            "total_pixels": 0,
            "cropland_pixels": 0,
        }


def check_year_complete(year: int) -> bool:
    """确认某年 CLCD 已完整下载。"""
    fname = f"CLCD_v01_{year}_albert.tif"
    fpath = CLCD_DIR / fname
    partial = CLCD_DIR / (fname + ".partial")
    if fpath.exists():
        return True
    if partial.exists():
        logging.warning("%s 的 .partial 存在（下载未完成）", year)
    return False


def main() -> int:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
        datefmt="%H:%M:%S",
    )

    logging.info("读取省界...")
    gdf = gpd.read_file(PROVINCE_GEOJSON)
    gdf = gdf[~gdf["name"].isin(SKIP_NAMES)].copy()
    gdf["province_code"] = gdf["gb"].str[-6:]
    gdf.set_crs("EPSG:4326", allow_override=True, inplace=True)
    logging.info("加载 %d 个省", len(gdf))

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

        for _, prov in gdf.iterrows():
            name = prov["name"]
            result = count_cropland_for_province(name, prov.geometry, src)
            result["year"] = year
            result["province_code"] = prov["province_code"]
            all_results.append(result)
            logging.info("  %s %s: 耕地 %.4f", year, name, result["cropland_ratio"])

        src.close()
        completed_years.append(year)

    if skipped_years:
        logging.warning("以下年份未下载完成，已跳过: %s", skipped_years)

    if not all_results:
        logging.error("没有成功处理任何年份（CLCD 下载可能尚未完成）")
        logging.info("检查下载目录: %s", CLCD_DIR)
        return 1

    df = pd.DataFrame(all_results)
    df = df.sort_values(["year", "province"]).reset_index(drop=True)
    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(OUT_PATH, index=False)
    logging.info("✅ 写入 %s (%d rows)", OUT_PATH, len(df))

    # Summary: year-over-year cropland change
    print("\n=== 各省耕地面积比例变化（2011 vs 2022） ===")
    df_2011 = df[df["year"] == 2011][["province", "cropland_ratio"]]
    df_2022 = df[df["year"] == 2022][["province", "cropland_ratio"]]
    if len(df_2011) > 0 and len(df_2022) > 0:
        merged = df_2011.merge(df_2022, on="province", suffixes=("_2011", "_2022"))
        merged["Δ"] = merged["cropland_ratio_2022"] - merged["cropland_ratio_2011"]
        merged["Δ%"] = merged["Δ"] / merged["cropland_ratio_2011"] * 100
        merged = merged.sort_values("Δ", ascending=False)
        for _, r in merged.iterrows():
            direction = "↑" if r["Δ"] > 0 else ("↓" if r["Δ"] < 0 else "→")
            print(f"  {r['province']:12s}  {r['cropland_ratio_2011']:.4f} → {r['cropland_ratio_2022']:.4f}  {direction} {r['Δ']:+.4f} ({r['Δ%']:+.1f}%)")

    print("\n已完成年份:", completed_years)
    print("跳过年份:", skipped_years)

    return 0


if __name__ == "__main__":
    sys.exit(main())
