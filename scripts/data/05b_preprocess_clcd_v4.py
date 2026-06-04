"""
8b-pre: Preprocess CLCD to 1km EPSG:4326 — fixed bounds transform.
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
    res = 0.008333333333333
    xf, w, h = calculate_default_transform(src.crs, dst_crs, src.width, src.height, *src.bounds, resolution=res)
    print(f"Dst shape: {w}x{h} (res={res}°)")
    
    profile = {
        'driver': 'GTiff', 'dtype': 'uint8', 'count': 1,
        'width': w, 'height': h, 'crs': dst_crs, 'transform': xf,
        'compress': 'LZW', 'nodata': 0, 'BIGTIFF': 'YES',
        'tiled': True, 'blockxsize': 256, 'blockysize': 256,
    }

    # Dest row mapping: source top → dst row 0, source bottom → dst row h
    # xf = (x_res, 0, x_origin, 0, -y_res, y_origin)
    # dst row = (y_origin - y) / y_res
    src_trans = src.transform
    dst_row0 = 0      # top of dst
    dst_rowN = h      # bottom of dst
    y_res_dst = -xf.e  # positive
    
    strip_h = 1000
    src_h = src.height
    total_crop, total_px = 0, 0

    def src_row_to_dst_row(src_row):
        """Map a source row center to destination row."""
        # Source row center in source CRS coordinates (Albers, meters)
        y_src = src_trans.f + (src_row + 0.5) * src_trans.e  # src_trans.e is negative
        # Transform to dst CRS
        from rasterio.warp import transform as rio_transform
        xs, ys = rio_transform(src.crs, dst_crs, [xf.c + 0.5 * xf.a], [y_src])
        y_dst = ys[0]
        # Destination row = (y_origin - y_dst) / y_res
        row = (xf.f - y_dst) / (-xf.e)
        return max(0, min(h-1, int(row)))
    
    with rasterio.open(DST, 'w', **profile) as dst:
        for y0 in range(0, src_h, strip_h):
            y1 = min(y0 + strip_h, src_h)
            
            # Read strip
            win = Window(0, y0, src.width, y1 - y0)
            data = src.read(1, window=win)
            crop = (data == 1).astype(np.uint8)
            del data
            
            # Source window transform
            swin = Window(0, y0, src.width, y1 - y0)
            strans = rasterio.windows.transform(swin, src.transform)
            
            # Map first and last source row to dst rows
            dr0 = src_row_to_dst_row(y0)
            dr1 = src_row_to_dst_row(y1 - 1) + 1  # inclusive → exclusive
            dh = min(h, dr1) - dr0
            if dh <= 0:
                del crop
                continue
            
            # Map left/right: full width of dst
            dst_part = np.zeros((dh, w), dtype=np.uint8)
            dst_win_xf = rasterio.windows.transform(Window(0, dr0, w, dh), xf)
            
            reproject(
                source=crop,
                destination=dst_part,
                src_transform=strans,
                src_crs=src.crs,
                dst_transform=dst_win_xf,
                dst_crs=dst_crs,
                resampling=Resampling.mode,
            )
            
            dst.write(dst_part, 1, window=Window(0, dr0, w, dh))
            total_crop += int(dst_part.sum())
            total_px += dst_part.size
            
            if (y0 // strip_h) % 5 == 0:
                print(f"  src[{y0:>6}-{y1:<6}] -> dst[{dr0:>4}-{dr1:<4}]  crop%={total_crop/max(1,total_px)*100:.1f}")
            del crop, dst_part
    
    print(f"\nTotal: crop_px={total_crop:,} / {total_px:,} ({total_crop/total_px*100:.2f}%)")
    mb = DST.stat().st_size / 1e6
    print(f"Done: {mb:.1f} MB -> {DST}")
