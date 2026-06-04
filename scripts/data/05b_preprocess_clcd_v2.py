"""
8b-pre: Preprocess CLCD to 1km EPSG:4326 — stream-based, low memory.
Reads source in tiles, reprojects tile-by-tile via rasterio.warp.reproject.
"""
import rasterio
from rasterio.warp import reproject, Resampling, calculate_default_transform
from rasterio.enums import Compression
from rasterio.windows import Window
import numpy as np
from pathlib import Path
import gc

CLCD_SRC = Path("/mnt/data/DC/gis_cropland/CLCD_v01_2022_albert.tif")
CLCD_OUT = Path("/home/slz/workspace/DC-AIino/data/raw/gis_cropland/CLCD_cropland_1km_epsg4326.tif")
CROP_CLASS = 1

print(f"Source: {CLCD_SRC} ({CLCD_SRC.stat().st_size / 1e6:.0f} MB)")

with rasterio.open(CLCD_SRC) as src:
    print(f"Source shape: {src.shape}, dtype: {src.dtypes[0]}")
    
    dst_crs = "EPSG:4326"
    # ~1km at equator: 0.008333333333333°
    xres = 0.008333333333333
    yres = 0.008333333333333
    
    # Estimate output bounds (Albers → WGS84)
    transform, width, height = calculate_default_transform(
        src.crs, dst_crs, src.width, src.height,
        *src.bounds, resolution=xres
    )
    print(f"Output: {width} × {height}, res={xres}°")
    
    profile = {
        'driver': 'GTiff',
        'dtype': 'uint8',
        'count': 1,
        'width': width,
        'height': height,
        'crs': dst_crs,
        'transform': transform,
        'compress': 'LZW',
        'nodata': 0,
        'BIGTIFF': 'YES',
        'tiled': True,
        'blockxsize': 256,
        'blockysize': 256,
    }

    # ---- Strategy: build output row-by-row using virtual reprojection ----
    # Instead of reading full source, we read source in strips of ~2000 rows
    # and reproject into a memory-mapped window of the output.
    
    print("Writing output in strips...")
    src_h = src.height
    strip_rows = 2000  # source rows per strip
    total_crop, total_px = 0, 0
    
    # Pre-compute: for each output row, which source strip(s) does it need?
    # Simple approach: iterate source strips, reproject into dst chunks.
    
    out = rasterio.open(CLCD_OUT, 'w', **profile)
    
    try:
        for y0 in range(0, src_h, strip_rows):
            y1 = min(y0 + strip_rows, src_h)
            win = Window(0, y0, src.width, y1 - y0)
            
            # Read and binarise
            strip = src.read(1, window=win)
            crop = (strip == CROP_CLASS).astype(np.uint8)
            del strip
            gc.collect()
            
            # Compute destination bounds for this strip
            left, bottom, right, top = rasterio.windows.bounds(
                Window(0, y0, src.width, y1 - y0), src.transform
            )
            
            # Find what output window covers these bounds
            from rasterio.windows import from_bounds
            try:
                dst_win = from_bounds(left, bottom, right, top, transform)
            except Exception:
                # fallback: calculate manually
                col_off = max(0, int((left - transform.c) / transform.a))
                row_off = max(0, int((top - transform.f) / transform.e))
                col_off = min(col_off, width - 1)
                row_off = min(row_off, height - 1)
                # rough estimate of extent
                src_x_extent = abs(transform.a) * width
                src_y_extent = abs(transform.e) * height
                ratio_x = (right - left) / src_x_extent if src_x_extent > 0 else 0.01
                ratio_y = (bottom - top) / src_y_extent if src_y_extent > 0 else 0.01
                w = max(1, int(width * ratio_x))
                h = max(1, int(height * ratio_y))
                dst_win = Window(col_off, row_off, min(w, width - col_off), min(h, height - row_off))
            
            dst_win = dst_win.round_offsets().round_lengths()
            dw = max(1, int(dst_win.width))
            dh = max(1, int(dst_win.height))
            dc = max(0, int(dst_win.col_off))
            dr = max(0, int(dst_win.row_off))
            dw = min(dw, width - dc)
            dh = min(dh, height - dr)
            
            if dw <= 0 or dh <= 0:
                del crop
                gc.collect()
                continue
            
            dst_part = np.zeros((dh, dw), dtype=np.uint8)
            
            src_win_tfm = rasterio.windows.transform(Window(0, y0, src.width, y1 - y0), src.transform)
            dst_win_tfm = rasterio.windows.transform(Window(dc, dr, dw, dh), transform)
            
            reproject(
                source=crop,
                destination=dst_part,
                src_transform=src_win_tfm,
                src_crs=src.crs,
                dst_transform=dst_win_tfm,
                dst_crs=dst_crs,
                resampling=Resampling.mode,
            )
            
            out.write(dst_part, 1, window=Window(dc, dr, dw, dh))
            
            total_crop += int(dst_part.sum())
            total_px += dst_part.size
            
            pct = total_crop / total_px * 100 if total_px > 0 else 0
            if (y0 // strip_rows) % 5 == 0:
                print(f"  Strip {y0}-{y1}/{src_h} -> output window ({dc},{dr},{dw},{dh})  crop%={pct:.2f}")
            
            del crop, dst_part
            gc.collect()
    
    finally:
        out.close()

    print(f"\nOutput cropland: {total_crop:,} / {total_px:,} ({total_crop/total_px*100:.2f}%)")
    size_mb = CLCD_OUT.stat().st_size / 1e6
    print(f"Done: {size_mb:.1f} MB → {CLCD_OUT}")
