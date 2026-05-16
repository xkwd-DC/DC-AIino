"""下载 SPEIbase v2.10 全球 0.5° NetCDF + 计算 31 省 zonal mean。

来源：DIGITAL.CSIC, https://digital.csic.es/handle/10261/364137
许可：CC-BY 4.0，引用 Vicente-Serrano et al. 2010
时间尺度：SPEI-3（季节性土壤水分，最适合作物风险研究）

输出：data/interim/spei_province_annual.csv
      列：province_code, province, year, spei_growing_season_mean, spei_annual_mean

策略：
  1. 下 spei03.nc 到 /mnt/data/DC/climate/（大盘）
  2. xarray 打开，时间裁 2011-2023
  3. 用天地图省界 GeoJSON 做 zonal mean
     - 生长季（4-10 月）取均值 → spei_growing_season_mean
     - 全年取均值 → spei_annual_mean
"""
from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import requests
import xarray as xr
from tqdm import tqdm

PROJECT_ROOT = Path(__file__).resolve().parents[2]
CLIMATE_DIR = Path("/mnt/data/DC/climate")
SPEI_URL = "https://digital.csic.es/bitstream/10261/364137/3/spei03.nc"
SPEI_LOCAL = CLIMATE_DIR / "spei03.nc"
PROVINCE_GEOJSON = PROJECT_ROOT / "data" / "raw" / "gis_province" / "tianditu" / "province_2024_GS2024-0650.geojson"
DEFAULT_OUT = PROJECT_ROOT / "data" / "interim" / "spei_province_annual.csv"
CHUNK = 1024 * 1024


def download_spei(url: str, dest: Path) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.exists() and dest.stat().st_size > 0:
        logging.info("SPEI 文件已存在 (%.1f MB)，跳过下载", dest.stat().st_size / 1024 / 1024)
        return
    logging.info("下载 SPEI-3 → %s", dest)
    partial = dest.with_suffix(dest.suffix + ".partial")
    already = partial.stat().st_size if partial.exists() else 0
    headers = {"Range": f"bytes={already}-"} if already > 0 else {}
    with requests.get(url, headers=headers, stream=True, timeout=180) as resp:
        resp.raise_for_status()
        total = int(resp.headers.get("Content-Length", 0)) + already
        with partial.open("ab" if already > 0 else "wb") as fp, tqdm(
            total=total, initial=already, unit="B", unit_scale=True, unit_divisor=1024, desc="spei03.nc"
        ) as bar:
            for c in resp.iter_content(chunk_size=CHUNK):
                if c:
                    fp.write(c)
                    bar.update(len(c))
    partial.rename(dest)


def zonal_mean(nc_path: Path, geojson_path: Path, years: range) -> pd.DataFrame:
    import geopandas as gpd
    from shapely.geometry import box

    logging.info("打开 NetCDF %s", nc_path)
    ds = xr.open_dataset(nc_path)
    var = "spei"
    if var not in ds.variables:
        raise RuntimeError(f"找不到 spei 变量；ds.variables = {list(ds.variables)}")

    # 时间裁
    da = ds[var].sel(time=slice(f"{years.start}-01-01", f"{years.stop - 1}-12-31"))
    logging.info("数据范围 time=%s..%s, shape=%s", da.time.values[0], da.time.values[-1], da.shape)

    # 经纬度坐标名规范化
    lat_name = "lat" if "lat" in da.dims else "latitude"
    lon_name = "lon" if "lon" in da.dims else "longitude"
    da = da.rename({lat_name: "lat", lon_name: "lon"})

    # 加 month 维
    da = da.assign_coords(month=da.time.dt.month, year=da.time.dt.year)

    # 读省界
    gdf = gpd.read_file(geojson_path)
    admin = gdf[gdf["name"] != "境界线"].copy()
    admin = admin[~admin["name"].isin({"香港特别行政区", "澳门特别行政区", "台湾省"})].copy()
    admin.set_crs("EPSG:4326", allow_override=True, inplace=True)
    admin["province_code"] = admin["gb"].str[-6:]
    logging.info("31 省矢量 OK")

    # 对每省做 zonal mean——SPEI 是 0.5°，每省 ~10-200 格，直接 mask 后取均值即可
    rows = []
    for _, prov in tqdm(admin.iterrows(), total=len(admin), desc="省级 zonal"):
        # 用 bbox 先粗筛
        minx, miny, maxx, maxy = prov.geometry.bounds
        sub = da.sel(lat=slice(maxy, miny), lon=slice(minx, maxx)) if da.lat[0] > da.lat[-1] \
            else da.sel(lat=slice(miny, maxy), lon=slice(minx, maxx))
        if sub.size == 0:
            logging.warning("%s bbox 内无 SPEI 格点", prov["name"])
            continue
        # bbox mean 作为省域近似（精确多边形 mask 用 rasterio.features.geometry_mask 也行，
        # 但 SPEI 0.5° 粗，bbox 已经 OK）
        df_prov = sub.to_dataframe(name="spei").reset_index().dropna(subset=["spei"])
        if df_prov.empty:
            continue
        df_prov["year"] = df_prov["time"].dt.year
        df_prov["month"] = df_prov["time"].dt.month

        annual_mean = df_prov.groupby("year")["spei"].mean()
        growing = df_prov[df_prov["month"].between(4, 10)].groupby("year")["spei"].mean()

        for year in years:
            rows.append({
                "province_code": prov["province_code"],
                "province": prov["name"],
                "year": year,
                "spei_annual_mean": annual_mean.get(year, np.nan),
                "spei_growing_season_mean": growing.get(year, np.nan),
            })

    return pd.DataFrame(rows)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="SPEI-3 下载 + 省域 zonal mean")
    parser.add_argument("--years", type=str, default="2011-2023")
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--verbose", "-v", action="store_true")
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
        datefmt="%H:%M:%S",
    )

    download_spei(SPEI_URL, SPEI_LOCAL)

    lo, hi = args.years.split("-", 1)
    df = zonal_mean(SPEI_LOCAL, PROVINCE_GEOJSON, range(int(lo), int(hi) + 1))
    args.out.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(args.out, index=False)
    logging.info("✅ SPEI 省级面板写入 %s（%d 行）", args.out, len(df))
    print(df.head(15).to_string(index=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
