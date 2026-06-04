"""
8b-pre: Preprocess CLCD to MODIS 1km grid — memory-safe chunked version.
"""
import rasterio
from rasterio.warp import reproject, Resampling, calculate_default_transform
from rasterio.enums import Compression
from rasterio.windows import Window
import numpy as np
from pathlib import Path
from math import ceil

CLCD_SRC = Path("/mnt/data/DC/gis_cropland/CLCD_v01_2022_albert.tif")
CLCD_OUT = Path("/home/slz/workspace/DC-AIino/data/raw/gis_cropland/CLCD_cropland_1km_epsg4326.tif")
CROP_CLASS = 1

print(f"Source: {CLCD_SRC} ({CLCD_SRC.stat().st_size / 1e6:.0f} MB)")

with rasterio.open(CLCD_SRC) as src:
    print(f"Source CRS: {src.crs}, shape: {src.shape}, dtype: {src.dtypes[0]}")
    
    dst_crs = "EPSG:4326"
    resolution = 0.008333333333333  # ~0.00833° = ~1km at equator
    
    # Calculate output extent
    transform, width, height = calculate_default_transform(
        src.crs, dst_crs,
        src.width, src.height,
        *src.bounds,
        resolution=resolution
    )
    
    print(f"Output: {width} × {height}, resolution: {resolution}°")
    est_mb = width * height * 1 / (1024 * 1024)
    print(f"Est output file size: {est_mb:.0f} MB (uint8, 1 band)")
    
    # Build output — windows approach
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
    
    print(f"Creating output raster...")
    
    # Process in source-row chunks
    src_height = src.height
    chunk_size = 2000  # process 2000 source rows at a time
    
    total_crop = 0
    total_px = 0
    
    with rasterio.open(CLCD_OUT, 'w', **out_profile) as dst:
        for row_start in range(0, src_height, chunk_size):
            row_end = min(row_start + chunk_size, src_height)
            win = Window(0, row_start, src.width, row_end - row_start)
            
            # Read chunk from source
            src_data = src.read(1, window=win)
            
            # Binary cropland mask
            crop_mask = (src_data == CROP_CLASS).astype(np.uint8)
            del src_data
            
            # For each output row affected by this chunk, reproject slice by slice
            src_window = rasterio.windows.Window(0, row_start, src.width, row_end - row_start)
            src_window_transform = rasterio.windows.transform(src_window, src.transform)
            
            # Find which output rows this slice maps to
            # We'll reproject the whole chunk into a temp array and write
            # First estimate the destination window
            dst_window = rasterio.windows.from_bounds(
                *rasterio.windows.bounds(src_window, src.transform),
                transform=transform
            )
            dst_window = dst_window.round_offsets().round_lengths()
            dst_window = Window(
                max(0, int(dst_window.col_off)),
                max(0, int(dst_window.row_off)),
                min(width, int(dst_window.width)),
                min(height, int(dst_window.height))
            )
            
            if dst_window.width <= 0 or dst_window.height <= 0:
                continue
            
            dst_chunk = np.zeros((dst_window.height, dst_window.width), dtype=np.uint8)
            
            reproject(
                source=crop_mask,
                destination=dst_chunk,
                src_transform=src_window_transform,
                src_crs=src.crs,
                dst_transform=rasterio.windows.transform(dst_window, transform),
                dst_crs=dst_crs,
                resampling=Resampling.mode,
            )
            
            dst.write(dst_chunk, 1, window=dst_window)
            
            total_crop += int(dst_chunk.sum())
            total_px += dst_chunk.size
            
            if (row_start // chunk_size) % 5 == 0:
                print(f"  Processed source rows {row_start}-{row_end} / {src_height}  (crop%={total_crop/total_px*100:.2f})")
            
            del crop_mask, dst_chunk

    out_pct = total_crop / total_px * 100 if total_px > 0 else 0
    print(f"\nOutput cropland: {total_crop:,} / {total_px:,} ({out_pct:.2f}%)")
    
    size_mb = CLCD_OUT.stat().st_size / 1e6
    print(f"Done: {size_mb:.1f} MB at {CLCD_OUT}")
