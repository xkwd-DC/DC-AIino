
"""8b-light: Compute per-province cropland pixel ratio from CLCD.
Output: data/raw/gis_cropland/province_cropland_ratio.parquet
Strategy: Read CLCD strips in memory-safe chunks, accumulate pixel counts per province.
"""
import geopandas as gpd
import rasterio
from rasterio import mask as rio_mask
from rasterio.windows import Window
import numpy as np
import pandas as pd
from pathlib import Path
import gc

PROJ = Path("/home/slz/workspace/DC-AIino")
CLCD = Path("/mnt/data/DC/gis_cropland/CLCD_v01_2022_albert.tif")
GEOJSON = PROJ / "data/raw/gis_province/tianditu/province_2024_GS2024-0650.geojson"
OUT = PROJ / "data/raw/gis_cropland/province_cropland_ratio.parquet"

print(f"Loading provinces from {GEOJSON}")
gdf = gpd.read_file(GEOJSON)
gdf = gdf[gdf["name"] != "境界线"].copy()
gdf = gdf[~gdf["name"].isin({"香港特别行政区", "澳门特别行政区", "台湾省"})].copy()
gdf.set_crs("EPSG:4326", allow_override=True, inplace=True)
print(f"  {len(gdf)} provinces")

# Strategy: for each province, mask the CLCD directly
# CLCD = Albers Equal Area, 30m resolution
# For each province, read CLCD in that province's bounding box + reproject to Albers

with rasterio.open(CLCD) as src:
    print(f"CLCD: shape={src.shape}, CRS={src.crs.to_string()[:50]}")
    
    results = []
    for idx, prov in gdf.iterrows():
        name = prov["name"]
        code = prov.get("gb", "").split("_")[-1] if "_" in str(prov.get("gb","")) else ""
        
        # Reproject province geometry to CLCD CRS
        import geopandas as gpd
        prov_gdf = gpd.GeoDataFrame({"geometry": [prov.geometry]}, crs="EPSG:4326")
        geom_proj = prov_gdf.to_crs(src.crs).iloc[0].geometry
        
        try:
            # Mask CLCD with province
            arr, _ = rio_mask.mask(src, [geom_proj], crop=True, nodata=0)
            arr = arr[0]
            
            total_px = arr.size
            crop_px = int((arr == 1).sum())
            non_zero = int((arr > 0).sum())
            crop_ratio = crop_px / non_zero if non_zero > 0 else 0.0
            
            print(f"  {name:8s}: CLCD(arr)={arr.shape}, crop_px={crop_px:,}/{non_zero:,} ({crop_ratio:.4f})")
            
            results.append({
                "province": name,
                "province_code": code,
                "cropland_pixel_ratio": round(crop_ratio, 6),
                "clcd_crop_count": crop_px,
                "clcd_valid_count": non_zero,
                "clcd_total_count": total_px,
            })
        except Exception as e:
            print(f"  {name:8s}: FAILED - {e}")
            results.append({
                "province": name,
                "province_code": code,
                "cropland_pixel_ratio": 0.0,
                "clcd_crop_count": 0,
                "clcd_valid_count": 0,
                "clcd_total_count": 0,
            })

df_out = pd.DataFrame(results)
df_out.to_parquet(OUT, index=False)
print(f"\nDone: {OUT}  ({len(df_out)} provinces)")
print(df_out[["province", "cropland_pixel_ratio"]].to_string())

