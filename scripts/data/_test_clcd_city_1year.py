"""Test CLCD city cropland ratio for a single year."""
import time, sys
from pathlib import Path
import geopandas as gpd
import numpy as np
import rasterio
from rasterio.windows import Window, from_bounds
from rasterio.warp import transform_bounds
from math import ceil

CITY_GEOJSON = 'data/raw/gis_province/cities_10provinces_GS2024.geojson'
CLCD_DIR = 'data/raw/gis_cropland'
YEAR = int(sys.argv[1]) if len(sys.argv) > 1 else 2022

gdf = gpd.read_file(CITY_GEOJSON)
PROV_ADCODE = {230000:'黑龙江',410000:'河南',370000:'山东',220000:'吉林',
               340000:'安徽',430000:'湖南',130000:'河北',510000:'四川',
               320000:'江苏',420000:'湖北'}
provinces = []
for _, r in gdf.iterrows():
    parent = r.get('parent', {})
    if isinstance(parent, dict):
        provinces.append(PROV_ADCODE.get(parent.get('adcode', 0), '?'))
    else:
        provinces.append('?')
gdf['province'] = provinces
gdf['city'] = gdf['name']
gdf.set_crs('EPSG:4326', allow_override=True, inplace=True)
print(f'Loaded {len(gdf)} cities')

fpath = f'{CLCD_DIR}/CLCD_v01_{YEAR}_albert.tif'
src = rasterio.open(fpath)
print(f'Raster shape: {src.shape}')

t0 = time.time()
results = []
CROP_CLASS = 1
TILE_SIZE = 2048
for idx, (_, row) in enumerate(gdf.iterrows()):
    bounds = row.geometry.bounds
    clcd_bounds = transform_bounds('EPSG:4326', src.crs, *bounds)
    win = from_bounds(*clcd_bounds, transform=src.transform)
    col_off = int(win.col_off)
    row_off = int(win.row_off)
    w = int(win.width)
    h = int(win.height)
    total = 0
    crop = 0
    for ti in range(max(1, ceil(h / TILE_SIZE))):
        for tj in range(max(1, ceil(w / TILE_SIZE))):
            tw = min(TILE_SIZE, h - ti * TILE_SIZE)
            th = min(TILE_SIZE, w - tj * TILE_SIZE)
            if tw <= 0 or th <= 0:
                continue
            tw2 = Window(col_off + tj * TILE_SIZE, row_off + ti * TILE_SIZE, th, tw)
            data = src.read(1, window=tw2)
            total += data.size
            crop += int(np.sum(data == CROP_CLASS))
    ratio = crop / total if total > 0 else 0.0
    results.append({
        'province': row['province'], 'city': row['city'],
        'cropland_ratio': round(ratio, 6),
    })
    if (idx + 1) % 30 == 0:
        elapsed = time.time() - t0
        print(f'  {idx+1}/{len(gdf)} cities done ({elapsed:.1f}s)')

src.close()
elapsed = time.time() - t0
print(f'\nDone {len(results)} cities in {elapsed:.1f}s')

print('\nSample:')
for r in results[:8]:
    print(f"  {r['province']:8s} {r['city']:10s} ratio={r['cropland_ratio']:.4f}")

# Quick summary
import pandas as pd
df = pd.DataFrame(results)
print(f'\nAvg cropland ratio: {df["cropland_ratio"].mean():.4f}')
print(f'Min: {df["cropland_ratio"].min():.4f} (city: {df.loc[df["cropland_ratio"].idxmin(), "city"]})')
print(f'Max: {df["cropland_ratio"].max():.4f} (city: {df.loc[df["cropland_ratio"].idxmax(), "city"]})')
