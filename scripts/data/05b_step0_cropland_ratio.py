"""
05b-step0 — 用 rasterstats.zonal_stats 算省级 CLCD 耕地占比。

rasterstats 的 zonal_stats 使用 C 扩展，比 rasterio.mask 内存效率高。
只读 CLCD，不做任何 reproject（在 CLCD 的 Albers CRS 里算）。

输出：data/interim/cropland_ratio_static.csv
"""
from __future__ import annotations

import logging
import sys
from pathlib import Path

import geopandas as gpd
import pandas as pd
from rasterstats import zonal_stats

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

    # Reproject provinces to CLCD's CRS (Albers)
    with rasterio.open(CLCD_PATH) as clcd:
        target_crs = clcd.crs
        nodata = 0
    logging.info("CLCD CRS: %s", target_crs)

    gdf_albers = gdf.to_crs(target_crs)

    # zonal_stats: categorical=True → per-category counts
    stats = zonal_stats(
        gdf_albers.geometry,
        str(CLCD_PATH),
        categorical=True,
        nodata=0,
        geojson_out=False,
    )

    rows = []
    for prov, s in zip(gdf.itertuples(index=False), stats):
        total = sum(s.values())
        crop_count = s.get(1, 0)  # CLCD class 1 = cropland
        ratio = round(crop_count / total, 6) if total > 0 else 0.0
        rows.append({
            "province_code": prov.province_code,
            "province": prov.name,
            "cropland_pixels": crop_count,
            "total_pixels": total,
            "cropland_ratio": ratio,
        })
        logging.info("  %s: crop=%d/%d = %.4f", prov.name, crop_count, total, ratio)

    df = pd.DataFrame(rows)
    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(OUT_PATH, index=False)
    logging.info("✅ 写入 %s（%d 省份）", OUT_PATH, len(df))
    print()
    print(df[["province", "cropland_ratio"]].to_string(index=False))
    return 0


if __name__ == "__main__":
    import rasterio
    sys.exit(main())
