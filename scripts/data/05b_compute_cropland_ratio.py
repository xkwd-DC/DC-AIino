"""
一次性脚本 — 计算各省 CLCD 耕地面积占比（静态，只跑一次）。

策略：
- 不在 MODIS CRS 里 reproject CLCD（那个 OOM 了）
- 直接在 CLCD 的 Albers 投影里用 province 几何 mask
- 输出：province_code × cropland_ratio（静态表）
- 05b 主脚本直接用这个表做修正

输出：data/interim/cropland_ratio_static.csv
"""
from __future__ import annotations

import logging
import sys
from pathlib import Path

import geopandas as gpd
import numpy as np
import pandas as pd
import rasterio
from rasterio import mask as rio_mask

PROJECT_ROOT = Path(__file__).resolve().parents[2]
CLCD_PATH = Path("/mnt/data/DC/gis_cropland/CLCD_v01_2022_albert.tif")
PROVINCE_GEOJSON = (
    PROJECT_ROOT
    / "data"
    / "raw"
    / "gis_province"
    / "tianditu"
    / "province_2024_GS2024-0650.geojson"
)
OUT_PATH = PROJECT_ROOT / "data" / "interim" / "cropland_ratio_static.csv"


def load_provinces() -> gpd.GeoDataFrame:
    gdf = gpd.read_file(PROVINCE_GEOJSON)
    gdf = gdf[gdf["name"] != "境界线"].copy()
    gdf = gdf[~gdf["name"].isin({"香港特别行政区", "澳门特别行政区", "台湾省"})].copy()
    gdf.set_crs("EPSG:4326", allow_override=True, inplace=True)
    gdf["province_code"] = gdf["gb"].str[-6:]
    return gdf


def main() -> int:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
        datefmt="%H:%M:%S",
    )

    gdf = load_provinces()
    logging.info("加载 %d 个内陆省", len(gdf))

    clcd = rasterio.open(CLCD_PATH)
    logging.info(
        "CLCD: shape=%s, CRS=%s, res=%s",
        clcd.shape, clcd.crs, clcd.res,
    )

    rows = []
    for _, prov in gdf.iterrows():
        geom = prov.geometry
        if geom is None or geom.is_empty:
            rows.append({
                "province_code": prov.province_code,
                "province": prov.name,
                "cropland_pixels": 0,
                "total_pixels": 0,
                "cropland_ratio": 0.0,
            })
            continue

        try:
            # Reproject province geometry to CLCD's Albers CRS
            geom_clcd = gpd.GeoSeries([geom], crs="EPSG:4326").to_crs(clcd.crs).iloc[0]

            # Mask CLCD with province boundary (in CLCD native CRS — no reproject)
            arr, _ = rio_mask.mask(clcd, [geom_clcd], crop=True, nodata=0)
            arr = arr[0]

            total_pixels = int(arr.size)
            crop_pixels = int(np.sum(arr == 1))  # CLCD class 1 = cropland
            ratio = round(crop_pixels / total_pixels, 6) if total_pixels > 0 else 0.0

            rows.append({
                "province_code": prov.province_code,
                "province": prov.name,
                "cropland_pixels": crop_pixels,
                "total_pixels": total_pixels,
                "cropland_ratio": ratio,
            })

            logging.info(
                "  %s: crop=%d/%d = %.4f", prov.name, crop_pixels, total_pixels, ratio,
            )

        except Exception as e:
            logging.warning("  %s: ERROR — %s", prov.name, e)
            rows.append({
                "province_code": prov.province_code,
                "province": prov.name,
                "cropland_pixels": 0,
                "total_pixels": 0,
                "cropland_ratio": 0.0,
            })

    clcd.close()

    df = pd.DataFrame(rows)
    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(OUT_PATH, index=False)
    logging.info("✅ 写入 %s（%d 省份）", OUT_PATH, len(df))
    print()
    print(df[["province", "cropland_ratio"]].to_string(index=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
