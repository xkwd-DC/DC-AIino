"""
8b — MODIS NDVI/LST → 耕地像元加权省域月度面板

相比 05_aggregate_modis_to_province.py（全省域均值）：
- 用 CLCD 30m 耕地掩膜做像元加权
- 只统计耕地区域的 MODIS 值
- 新增 cropland_pixel_ratio 列（耕地区域占比）

输入：
  /mnt/data/DC/modis_ndvi/<year>/.../*_NDVI_doy*.tif
  /mnt/data/DC/modis_lst/<year>/.../*_LST_*.tif
  /mnt/data/DC/gis_cropland/CLCD_v01_2022_albert.tif
  data/raw/gis_province/tianditu/province_2024_GS2024-0650.geojson

输出：data/interim/modis_province_monthly_v4.parquet
"""
from __future__ import annotations

import argparse
import logging
import re
import sys
from datetime import date, timedelta
from pathlib import Path

import geopandas as gpd
import numpy as np
import pandas as pd
import rasterio
from rasterio import mask as rio_mask
from rasterio.warp import reproject, Resampling
from tqdm import tqdm

PROJECT_ROOT = Path(__file__).resolve().parents[2]
MODIS_NDVI_ROOT = Path("/mnt/data/DC/modis_ndvi")
MODIS_LST_ROOT = Path("/mnt/data/DC/modis_lst")
CLCD_PATH = Path("/mnt/data/DC/gis_cropland/CLCD_v01_2022_albert.tif")
PROVINCE_GEOJSON = PROJECT_ROOT / "data" / "raw" / "gis_province" / "tianditu" / "province_2024_GS2024-0650.geojson"
DEFAULT_OUT = PROJECT_ROOT / "data" / "interim" / "modis_province_monthly_v4.parquet"

# CLCD crop classes (from Yang & Huang 2021):
# 1 = cropland, 2 = forest, 3 = shrub, 4 = grassland,
# 5 = water, 6 = snow/ice, 7 = barren, 8 = impervious, 9 = wetland
CROP_CLASS = 1

NDVI_SCALE = 0.0001
LST_SCALE = 0.02
NDVI_NODATA = -3000
LST_NODATA = 0

DOY_RE = re.compile(r"doy(\d{4})(\d{3})")


def doy_to_date(year: int, doy: int) -> date:
    return date(year, 1, 1) + timedelta(days=doy - 1)


def list_tifs(root: Path, year: int, pattern: str) -> list[Path]:
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


def zonal_cropland_weighted(
    tif_path: Path,
    gdf: gpd.GeoDataFrame,
    scale: float,
    nodata: int,
    clcd_src: rasterio.DatasetReader,
) -> pd.DataFrame:
    """
    单 TIF × 31 省 → cropland-weighted mean/std/count.
    
    For each province:
    1. Mask MODIS raster with province geometry
    2. Read CLCD within same extent (reprojected to MODIS CRS)
    3. Create cropland boolean mask (CLCD == 1)
    4. Compute weighted stats using only cropland pixels
    """
    with rasterio.open(tif_path) as modis_src:
        modis_crs = modis_src.crs
        
        rows = []
        for _, prov in gdf.iterrows():
            geom = prov.geometry
            
            # Check if geometry is valid
            if geom is None or geom.is_empty:
                rows.append({
                    "province_code": prov.province_code,
                    "province": prov.name,
                    "mean": None, "std": None, "valid_count": 0,
                    "cropland_pixel_ratio": 0.0,
                })
                continue
            
            try:
                # Mask MODIS with province geometry
                modis_arr, modis_transform = rio_mask.mask(
                    modis_src, [geom], crop=True, nodata=nodata
                )
                modis_arr = modis_arr[0]  # single band
                
                if modis_arr.size == 0:
                    rows.append({
                        "province_code": prov.province_code,
                        "province": prov.name,
                        "mean": None, "std": None, "valid_count": 0,
                        "cropland_pixel_ratio": 0.0,
                    })
                    continue
                
                # Read CLCD for the same extent
                # Reproject province geometry to CLCD CRS for reading
                clcd_window = None
                try:
                    # Get the CLCD data in the MODIS extent using reprojection
                    from rasterio.windows import from_bounds
                    modis_bounds = rasterio.transform.array_bounds(
                        modis_arr.shape[0], modis_arr.shape[1], modis_transform
                    )
                    
                    # Transform bounds to CLCD CRS
                    clcd_bounds = rasterio.warp.transform_bounds(
                        modis_crs, clcd_src.crs, *modis_bounds
                    )
                    
                    # Read CLCD window
                    clcd_window = rasterio.windows.from_bounds(
                        *clcd_bounds, transform=clcd_src.transform
                    )
                    clcd_window = clcd_window.round_offsets().round_lengths()
                    
                    clcd_data = clcd_src.read(1, window=clcd_window)
                    
                    # Reproject CLCD to MODIS CRS and shape
                    clcd_reproj = np.zeros_like(modis_arr, dtype=np.uint8)
                    reproject(
                        source=clcd_data,
                        destination=clcd_reproj,
                        src_transform=rasterio.windows.transform(clcd_window, clcd_src.transform),
                        src_crs=clcd_src.crs,
                        dst_transform=modis_transform,
                        dst_crs=modis_crs,
                        resampling=Resampling.nearest,
                    )
                    
                    # Create cropland mask (1 = crop, 0 = non-crop)
                    crop_mask = (clcd_reproj == CROP_CLASS)
                    
                    # Apply nodata mask on MODIS
                    if nodata != 0:
                        valid_modis = (modis_arr != nodata) & (~np.isnan(modis_arr))
                    else:
                        valid_modis = ~np.isnan(modis_arr)
                    
                    # Combined: valid MODIS AND cropland
                    crop_valid = crop_mask & valid_modis
                    total_valid = valid_modis
                    
                    crop_count = int(crop_valid.sum())
                    total_count = int(total_valid.sum())
                    
                    if crop_count > 0:
                        crop_vals = modis_arr[crop_valid] * scale
                        crop_mean = float(np.mean(crop_vals))
                        crop_std = float(np.std(crop_vals))
                    else:
                        crop_mean = None
                        crop_std = None
                    
                    cropland_ratio = crop_count / total_count if total_count > 0 else 0.0
                    
                except Exception as e:
                    logging.debug("CLCD warp failed for %s: %s", prov.name, e)
                    crop_mean = None
                    crop_std = None
                    crop_count = 0
                    cropland_ratio = 0.0
                
                rows.append({
                    "province_code": prov.province_code,
                    "province": prov.name,
                    "mean": crop_mean,
                    "std": crop_std,
                    "valid_count": crop_count,
                    "cropland_pixel_ratio": round(cropland_ratio, 6),
                })
                
            except Exception as e:
                logging.warning("zonal failed for %s: %s", prov.name, e)
                rows.append({
                    "province_code": prov.province_code,
                    "province": prov.name,
                    "mean": None, "std": None, "valid_count": 0,
                    "cropland_pixel_ratio": 0.0,
                })
    
    return pd.DataFrame(rows)


def aggregate_ndvi_cropland(
    year: int, gdf: gpd.GeoDataFrame, clcd_src: rasterio.DatasetReader
) -> pd.DataFrame:
    files = list_tifs(MODIS_NDVI_ROOT, year, "*_NDVI_doy*.tif")
    if not files:
        logging.warning("%s 没找到 NDVI TIF", year)
        return pd.DataFrame()
    logging.info("NDVI %s: %d 月度文件", year, len(files))

    out = []
    for f in tqdm(files, desc=f"NDVI-crop {year}"):
        m = DOY_RE.search(f.name)
        if not m:
            continue
        file_year, doy = int(m.group(1)), int(m.group(2))
        month = doy_to_date(file_year, doy).month
        df = zonal_cropland_weighted(f, gdf, NDVI_SCALE, NDVI_NODATA, clcd_src)
        df["year"] = file_year
        df["month"] = month
        df = df.rename(columns={
            "mean": "ndvi_mean", "std": "ndvi_std",
            "valid_count": "ndvi_valid_count"
        })
        out.append(df)
    return pd.concat(out, ignore_index=True) if out else pd.DataFrame()


def aggregate_lst_cropland(
    year: int, gdf: gpd.GeoDataFrame, band: str, clcd_src: rasterio.DatasetReader
) -> pd.DataFrame:
    pattern = f"*LST_{band}_1km_doy*.tif"
    files = list_tifs(MODIS_LST_ROOT, year, pattern)
    if not files:
        logging.warning("%s 没找到 LST %s TIF", year, band)
        return pd.DataFrame()
    logging.info("LST-%s %s: %d 个 8-day 文件", band, year, len(files))

    rows_per_granule = []
    for f in tqdm(files, desc=f"LST-{band}-crop {year}"):
        m = DOY_RE.search(f.name)
        if not m:
            continue
        file_year, doy = int(m.group(1)), int(m.group(2))
        if file_year != year:
            continue
        granule_date = doy_to_date(file_year, doy)
        month = granule_date.month
        df = zonal_cropland_weighted(f, gdf, LST_SCALE, LST_NODATA, clcd_src)
        df["year"] = file_year
        df["month"] = month
        df["doy"] = doy
        rows_per_granule.append(df)

    if not rows_per_granule:
        return pd.DataFrame()
    
    all_granules = pd.concat(rows_per_granule, ignore_index=True)
    monthly = (
        all_granules.dropna(subset=["mean"])
        .groupby(["province_code", "province", "year", "month"], as_index=False)
        .agg(
            mean=("mean", "mean"),
            std=("std", "mean"),
            valid_count=("valid_count", "sum"),
            cropland_pixel_ratio=("cropland_pixel_ratio", "mean"),
        )
    )
    return monthly


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="MODIS → 耕地加权省域月度面板")
    parser.add_argument("--year", type=int)
    parser.add_argument("--years", type=str, help="年份范围 START-END")
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--dry-run", action="store_true", help="只验证路径，不实际处理")
    parser.add_argument("--verbose", "-v", action="store_true")
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
        datefmt="%H:%M:%S",
    )

    # Pre-flight checks
    if not PROVINCE_GEOJSON.exists():
        logging.error("省界文件缺失: %s", PROVINCE_GEOJSON)
        logging.error("请按 data/raw/gis_province/tianditu/README.md 手动下载")
        return 2
    if not CLCD_PATH.exists():
        logging.error("CLCD 缺失: %s", CLCD_PATH)
        return 2

    if args.year is not None:
        years = [args.year]
    elif args.years:
        lo, hi = args.years.split("-", 1)
        years = list(range(int(lo), int(hi) + 1))
    else:
        years = list(range(2011, 2024))

    if args.dry_run:
        logging.info("dry-run: 年份=%s", years)
        logging.info("geojson=%s (exists=%s)", PROVINCE_GEOJSON, PROVINCE_GEOJSON.exists())
        logging.info("CLCD=%s (%s MB)", CLCD_PATH, CLCD_PATH.stat().st_size / 1e6)
        # Check first year TIFs
        for y in years[:1]:
            ndvi_files = list_tifs(MODIS_NDVI_ROOT, y, "*_NDVI_doy*.tif")
            lst_files = list_tifs(MODIS_LST_ROOT, y, "*_LST_Day_1km_doy*.tif")
            logging.info("%s: NDVI=%d TIFs, LST_Day=%d TIFs", y, len(ndvi_files), len(lst_files))
        return 0

    gdf = load_provinces()
    logging.info("加载 %d 个内陆省", len(gdf))

    # Open CLCD once (read-only, all years use same 2022 CLCD)
    clcd_src = rasterio.open(CLCD_PATH)
    logging.info("CLCD: CRS=%s, shape=%s, crop_class=%d", clcd_src.crs, clcd_src.shape, CROP_CLASS)

    all_rows = []
    for year in years:
        ndvi_df = aggregate_ndvi_cropland(year, gdf, clcd_src)
        lst_day_df = aggregate_lst_cropland(year, gdf, "Day", clcd_src)
        lst_night_df = aggregate_lst_cropland(year, gdf, "Night", clcd_src)

        if ndvi_df.empty:
            logging.warning("%s 跳过（无 NDVI 数据）", year)
            continue

        merged = ndvi_df[["province_code", "province", "year", "month",
                          "ndvi_mean", "ndvi_std", "ndvi_valid_count", "cropland_pixel_ratio"]]

        if not lst_day_df.empty:
            lst_day = lst_day_df.rename(columns={
                "mean": "lst_day_mean_k", "std": "lst_day_std_k",
                "valid_count": "lst_day_valid_count"
            })
            merged = merged.merge(
                lst_day[["province_code", "year", "month",
                         "lst_day_mean_k", "lst_day_std_k", "lst_day_valid_count"]],
                on=["province_code", "year", "month"], how="left",
            )
        else:
            for c in ["lst_day_mean_k", "lst_day_std_k", "lst_day_valid_count"]:
                merged[c] = None

        if not lst_night_df.empty:
            lst_night = lst_night_df.rename(columns={
                "mean": "lst_night_mean_k", "std": "lst_night_std_k",
                "valid_count": "lst_night_valid_count"
            })
            merged = merged.merge(
                lst_night[["province_code", "year", "month",
                           "lst_night_mean_k", "lst_night_std_k", "lst_night_valid_count"]],
                on=["province_code", "year", "month"], how="left",
            )
        else:
            for c in ["lst_night_mean_k", "lst_night_std_k", "lst_night_valid_count"]:
                merged[c] = None

        all_rows.append(merged)

    clcd_src.close()

    if not all_rows:
        logging.error("无任何年份成功聚合")
        return 1

    final = pd.concat(all_rows, ignore_index=True).sort_values(
        ["province_code", "year", "month"]
    ).reset_index(drop=True)

    cols = [
        "province_code", "province", "year", "month",
        "ndvi_mean", "ndvi_std",
        "lst_day_mean_k", "lst_night_mean_k",
        "cropland_pixel_ratio",
    ]
    extras = [c for c in final.columns if c not in cols]
    final_out = final[cols + extras]

    args.out.parent.mkdir(parents=True, exist_ok=True)
    final_out.to_parquet(args.out, index=False)
    logging.info("✅ 写入 %s (%d 行 × %d 列)", args.out, len(final_out), len(final_out.columns))

    # Compare with old (non-cropland-weighted) if available
    old_path = PROJECT_ROOT / "data" / "interim" / "modis_province_monthly.parquet"
    if old_path.exists():
        old = pd.read_parquet(old_path)
        merged_cmp = final_out.merge(
            old[["province_code", "year", "month", "ndvi_mean"]],
            on=["province_code", "year", "month"],
            suffixes=("_v4", "_v3"),
            how="inner"
        )
        if len(merged_cmp) > 0:
            delta = merged_cmp["ndvi_mean_v4"] - merged_cmp["ndvi_mean_v3"]
            print(f"\n=== v4 vs v3 NDVI 对比 ({len(merged_cmp)} rows) ===")
            print(f"  Δ mean: {delta.mean():.4f}")
            print(f"  Δ std:  {delta.std():.4f}")
            print(f"  Δ min:  {delta.min():.4f}")
            print(f"  Δ max:  {delta.max():.4f}")
            print(f"  Δ > 0.05: {(delta.abs() > 0.05).sum()} rows")
            print(f"  cropland_pixel_ratio mean: {final_out['cropland_pixel_ratio'].mean():.4f}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
