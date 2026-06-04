#!/usr/bin/env python3
"""8b Step 0 v2：逐省算 CLCD 耕地面积比例 — 分块读取，防 OOM。

对每个省：
1. 计算 CLCD CRS 下的 bounding box window
2. 用 win.split() 分成 2048×2048 的块
3. 逐块统计 crop_class 像素数，累加

这样内存峰值 ≈ 2 个 2048×2048 uint8 块 ≈ 8MB 左右。

输出：data/interim/province_cropland_ratio.parquet
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
CLCD_PATH = Path("/mnt/data/DC/gis_cropland/CLCD_v01_2022_albert.tif")
PROVINCE_GEOJSON = PROJECT_ROOT / "data" / "raw" / "gis_province" / "tianditu" / "province_2024_GS2024-0650.geojson"
OUT_PATH = PROJECT_ROOT / "data" / "interim" / "province_cropland_ratio.parquet"

CROP_CLASS = 1
SKIP_NAMES = {"香港特别行政区", "澳门特别行政区", "台湾省", "境界线"}
TILE_SIZE = 2048  # 分块大小，控制在 ~4MB/块


def count_cropland_in_window(
    src: rasterio.DatasetReader, window: Window
) -> tuple[int, int]:
    """对单个 Window 统计总像素数和 cropland 像素数。"""
    data = src.read(1, window=window)
    total = data.size
    crop = int(np.sum(data == CROP_CLASS))
    return total, crop


def count_cropland_for_province(name: str, geom, src: rasterio.DatasetReader) -> dict:
    """分块统计一个省的 CLCD 总像素和耕地像素。"""
    try:
        bounds_wgs84 = geom.bounds
        clcd_bounds = transform_bounds("EPSG:4326", src.crs, *bounds_wgs84)

        win = from_bounds(*clcd_bounds, transform=src.transform)

        # Round to integer pixel boundaries
        col_off = int(win.col_off)
        row_off = int(win.row_off)
        width = int(win.width)
        height = int(win.height)

        total_pixels = 0
        cropland_pixels = 0

        # Scan in tiles
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
                    th,
                    tw,
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


def main() -> int:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
        datefmt="%H:%M:%S",
    )

    logging.info("读取省界: %s", PROVINCE_GEOJSON)
    gdf = gpd.read_file(PROVINCE_GEOJSON)
    gdf = gdf[~gdf["name"].isin(SKIP_NAMES)].copy()
    gdf["province_code"] = gdf["gb"].str[-6:]
    gdf.set_crs("EPSG:4326", allow_override=True, inplace=True)
    logging.info("加载 %d 个省", len(gdf))

    logging.info("打开 CLCD: %s", CLCD_PATH)
    src = rasterio.open(CLCD_PATH)
    logging.info("CLCD shape=%s, tile_size=%d", src.shape, TILE_SIZE)

    results = []
    for _, prov in gdf.iterrows():
        name = prov["name"]
        logging.info("处理 %s (%s)...", name, prov["province_code"])
        result = count_cropland_for_province(name, prov.geometry, src)
        result["province_code"] = prov["province_code"]
        results.append(result)
        logging.info(
            "  → 耕地 %d / %d = %.4f",
            result["cropland_pixels"],
            result["total_pixels"],
            result["cropland_ratio"],
        )

    src.close()

    df = pd.DataFrame(results)
    df = df.sort_values("province").reset_index(drop=True)
    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(OUT_PATH, index=False)
    logging.info("✅ 写入 %s (%d rows)", OUT_PATH, len(df))

    # Summary
    print("\n=== 各省耕地面积比例 ===")
    for _, r in df.iterrows():
        bar = "█" * int(r["cropland_ratio"] * 50)
        print(f"  {r['province']:12s}  {r['cropland_ratio']:.4f}  {bar}")

    # Show provinces with zero cropland
    zero = df[df["cropland_ratio"] == 0]
    if len(zero) > 0:
        logging.warning("以下省份耕地比例为 0（请确认）：%s", list(zero["province"]))

    return 0


if __name__ == "__main__":
    sys.exit(main())
