"""
8b-pre: Preprocess CLCD to 1km EPSG:4326 — memory-safe streaming
Strategy: read source in strips, binarize, reproject strip by strip.
"""
import rasterio
from rasterio.warp import reproject, Resampling, calculate_default_transform
from rasterio.enums import Compression
from rasterio.windows import Window
import numpy as np
from pathlib import Path

SRC = Path("/mnt/data/DC/gis_cropland/CLCD_v01_2022_albert.tif")
DST = Path("/home/slz/workspace/DC-AIino/data/raw/gis_cropland/CLCD_cropland_1km_epsg4326.tif")

print(f"Source: {SRC}  ({SRC.stat().st_size / 1e6:.1f} MB)")

with rasterio.open(SRC) as src:
    print(f"Shape: {src.shape}, CRS: {src.crs.to_string()[:60]}, dtype: {src.dtypes[0]}")
    
    dst_crs = "EPSG:4326"
    res = 0.008333333333333  # ~1km
    xf, w, h = calculate_default_transform(src.crs, dst_crs, src.width, src.height, *src.bounds, resolution=res)
    print(f"Dst shape: {w}x{h} ({w*h:,} pixels, ~{w*h/1024/1024*1:.1f} MB uint8)")
    
    profile = {
        'driver': 'GTiff', 'dtype': 'uint8', 'count': 1,
        'width': w, 'height': h, 'crs': dst_crs, 'transform': xf,
        'compress': 'LZW', 'nodata': 0, 'BIGTIFF': 'YES',
        'tiled': True, 'blockxsize': 256, 'blockysize': 256,
        'interleave': 'band',
    }
    
    # Read source in 1000-row strips
    strip = 1000
    src_h = src.height
    total_crop = 0
    total_px = 0
    
    with rasterio.open(DST, 'w', **profile) as dst:
        for y0 in range(0, src_h, strip):
            y1 = min(y0 + strip, src_h)
            
            # Read and binarize
            win = Window(0, y0, src.width, y1 - y0)
            data = src.read(1, window=win)
            crop = (data == 1).astype(np.uint8)
            del data
            
            # Compute source window transform
            swin = Window(0, y0, src.width, y1 - y0)
            strans = rasterio.windows.transform(swin, src.transform)
            
            # Compute bounds, map to dst window
            l, b, r, t = rasterio.windows.bounds(swin, src.transform)
            # Clamp to dst bounds
            l = max(l, xf.c); b = max(b, xf.f + h * xf.e); r = min(r, xf.c + w * xf.a); t = min(t, xf.f)
            
            c0 = max(0, int((l - xf.c) / xf.a))
            r0 = max(0, int((t - xf.f) / xf.e))
            c1 = min(w, int((r - xf.c) / xf.a) + 1)
            r1 = min(h, int((b - xf.f) / xf.e) + 1)
            dw, dh = max(1, c1 - c0), max(1, r1 - r0)
            
            dst_part = np.zeros((dh, dw), dtype=np.uint8)
            dst_win_xf = rasterio.windows.transform(Window(c0, r0, dw, dh), xf)
            
            reproject(
                source=crop,
                destination=dst_part,
                src_transform=strans,
                src_crs=src.crs,
                dst_transform=dst_win_xf,
                dst_crs=dst_crs,
                resampling=Resampling.mode,
            )
            
            dst.write(dst_part, 1, window=Window(c0, r0, dw, dh))
            total_crop += int(dst_part.sum())
            total_px += dst_part.size
            
            if (y0 // strip) % 3 == 0:
                print(f"  strip {y0}-{y1}/{src_h} -> dst ({c0},{r0},{dw},{dh})  crop%={total_crop/total_px*100:.1f}")
            del crop, dst_part
    
    print(f"\nTotal: crop_px={total_crop:,} / {total_px:,} ({total_crop/total_px*100:.2f}%)")
    mb = DST.stat().st_size / 1e6
    print(f"Done: {mb:.1f} MB -> {DST}")
