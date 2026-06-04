"""
8b-pre: Preprocess CLCD to MODIS 1km grid (one-time operation)

Output: /mnt/data/DC/gis_cropland/CLCD_cropland_1km_epsg4326.tif
  - Resampled from 30m to ~1km (0.01° ≈ MODIS resolution)
  - Reprojected from Albers (EPSG:4490) to EPSG:4326 (WGS84)
  - Binary: 1 = cropland, 0 = non-cropland
  - Same extent/CRS/resolution as MODIS TIFs for direct element-wise masking
"""
import rasterio
from rasterio.warp import reproject, Resampling, calculate_default_transform
from rasterio.enums import Compression
import numpy as np
from pathlib import Path

CLCD_SRC = Path("/mnt/data/DC/gis_cropland/CLCD_v01_2022_albert.tif")
CLCD_OUT = Path("/mnt/data/DC/gis_cropland/CLCD_cropland_1km_epsg4326.tif")
CROP_CLASS = 1

print(f"Source: {CLCD_SRC} ({CLCD_SRC.stat().st_size / 1e6:.0f} MB)")

with rasterio.open(CLCD_SRC) as src:
    print(f"Source CRS: {src.crs}, shape: {src.shape}, dtype: {src.dtypes[0]}")
    
    # Target: EPSG:4326 at ~0.01° resolution (≈1km MODIS)
    dst_crs = "EPSG:4326"
    
    # Calculate output transform and dimensions
    transform, width, height = calculate_default_transform(
        src.crs, dst_crs,
        src.width, src.height,
        *src.bounds,
        resolution=0.01  # ~1km at equator
    )
    
    print(f"Output: {width} × {height}, resolution ~0.01°")
    
    # Output profile
    out_profile = src.profile.copy()
    out_profile.update({
        'crs': dst_crs,
        'transform': transform,
        'width': width,
        'height': height,
        'dtype': 'uint8',
        'count': 1,
        'compress': Compression.lzw,
        'nodata': 0,
        'BIGTIFF': 'YES',
    })
    
    # Read source data
    print("Reading CLCD source...")
    src_data = src.read(1)
    
    # Create binary cropland mask
    crop_mask = (src_data == CROP_CLASS).astype(np.uint8)
    crop_pct = crop_mask.sum() / crop_mask.size * 100
    print(f"Cropland pixels: {crop_mask.sum():,} / {crop_mask.size:,} ({crop_pct:.2f}%)")
    
    # Allocate output
    dst_data = np.zeros((height, width), dtype=np.uint8)
    
    # Reproject with mode resampling (nearest for categorical)
    print("Reprojecting to EPSG:4326 (~1km)...")
    reproject(
        source=crop_mask,
        destination=dst_data,
        src_transform=src.transform,
        src_crs=src.crs,
        dst_transform=transform,
        dst_crs=dst_crs,
        resampling=Resampling.mode,  # nearest for binary mask
    )
    
    out_pct = dst_data.sum() / dst_data.size * 100
    print(f"Output cropland: {dst_data.sum():,} / {dst_data.size:,} ({out_pct:.2f}%)")
    
    # Write
    print(f"Writing {CLCD_OUT}...")
    with rasterio.open(CLCD_OUT, 'w', **out_profile) as dst:
        dst.write(dst_data, 1)
    
    size_mb = CLCD_OUT.stat().st_size / 1e6
    print(f"Done: {size_mb:.1f} MB")
