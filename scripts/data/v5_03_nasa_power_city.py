#!/usr/bin/env python3
"""v5 Step 3：NASA POWER → 10 粮食主产省地级市年度气象面板。

对 148 个地级市，用市域 centroid/repr_point 拉取 NASA POWER 点数据。
无需账号。

变量映射：
  T2M (°C) → temp (年均温 °C)
  PRECTOTCORR (mm/day) → prec (年降水量 mm)
  ALLSKY_SFC_SW_DWN → sun (日照估算)

输出格式：
  data/interim/nasa_power_city_yearly_v5.parquet（148 市 × 13 年）
"""

import argparse
import json
import logging
import sys
import time
from pathlib import Path

import geopandas as gpd
import numpy as np
import pandas as pd
import requests

PROJECT_ROOT = Path(__file__).resolve().parents[2]
CITY_GEOJSON = PROJECT_ROOT / "data" / "raw" / "gis_province" / "cities_10provinces_GS2024.geojson"
OUT_PATH = PROJECT_ROOT / "data" / "interim" / "nasa_power_city_yearly_v5.parquet"
CENTROIDS_PATH = PROJECT_ROOT / "data" / "interim" / "city_centroids_v5.csv"

POWER_BASE = "https://power.larc.nasa.gov/api/temporal/daily/point"
REQUEST_DELAY = 0.1  # 节流，避免封 IP
TIMEOUT = 30

# 10 省 adcode → 省名
PROVINCE_NAME = {
    230000: "黑龙江", 410000: "河南", 370000: "山东",
    220000: "吉林", 340000: "安徽", 430000: "湖南",
    130000: "河北", 510000: "四川", 320000: "江苏", 420000: "湖北",
}

PARAMETERS = "T2M,PRECTOTCORR,ALLSKY_SFC_SW_DWN"
START_YEAR = 2011
END_YEAR = 2023


def compute_centroids(gdf: gpd.GeoDataFrame) -> pd.DataFrame:
    """计算每个地级市的 representative point（省界内点，非 centroid 可能落海外）。"""
    rows = []
    for _, row in gdf.iterrows():
        pt = row.geometry.representative_point()
        rows.append({
            "province": row["province"],
            "city": row["city"],
            "lon": round(pt.x, 6),
            "lat": round(pt.y, 6),
        })
    return pd.DataFrame(rows)


def fetch_power_year(lon: float, lat: float, year: int) -> dict | None:
    """拉取单年 NASA POWER 数据。返回 {T2M, PRECTOTCORR, ALLSKY_SFC_SW_DWN} 年均值。"""
    params = {
        "parameters": PARAMETERS,
        "community": "RE",
        "start": f"{year}0101",
        "end": f"{year}1231",
        "format": "JSON",
        "longitude": lon,
        "latitude": lat,
    }
    try:
        resp = requests.get(POWER_BASE, params=params, timeout=TIMEOUT)
        resp.raise_for_status()
        data = resp.json()
        props = data.get("properties", {}).get("parameter", {})
        if not props:
            return None

        result = {"year": year}
        for param in ["T2M", "PRECTOTCORR", "ALLSKY_SFC_SW_DWN"]:
            daily = props.get(param, {})
            vals = [v for v in daily.values() if v is not None]
            result[param] = round(np.mean(vals), 4) if vals else None
        return result
    except Exception as e:
        logging.warning("POWER fetch error (%.4f, %.4f, %s): %s", lon, lat, year, e)
        return None


def fetch_power_all_years(lon: float, lat: float, prov: str, city: str) -> list[dict]:
    """拉取 2011-2023 全周期。"""
    rows = []
    for year in range(START_YEAR, END_YEAR + 1):
        result = fetch_power_year(lon, lat, year)
        if result:
            result["province"] = prov
            result["city"] = city
            rows.append(result)
        time.sleep(REQUEST_DELAY)
    return rows


def load_cities() -> gpd.GeoDataFrame:
    gdf = gpd.read_file(CITY_GEOJSON)
    provinces = []
    for _, row in gdf.iterrows():
        parent = row.get("parent", {})
        if isinstance(parent, dict):
            provinces.append(PROVINCE_NAME.get(parent.get("adcode", 0), "?"))
        else:
            provinces.append("?")
    gdf = gdf.copy()
    gdf["province"] = provinces
    gdf["city"] = gdf["name"]
    gdf.set_crs("EPSG:4326", allow_override=True, inplace=True)
    return gdf


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="NASA POWER → 地级市年度气象 (v5)")
    parser.add_argument("--test", action="store_true", help="仅测 3 个城市")
    parser.add_argument("--resume", type=str, help="从之前中断的 CSV 恢复")
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
        datefmt="%H:%M:%S",
    )

    logging.info("加载地级市 GeoJSON...")
    gdf = load_cities()
    logging.info("加载 %d 个地级市", len(gdf))

    if args.resume:
        existing = pd.read_csv(args.resume)
        done_cities = set(existing["city_id"].unique())
        logging.info("已完成的 city_id 数量: %d", len(done_cities))
    else:
        done_cities = set()

    # 计算中心点并保存
    centroids = compute_centroids(gdf)
    centroids_path = PROJECT_ROOT / "data" / "interim" / "city_centroids_v5.csv"
    centroids_path.parent.mkdir(parents=True, exist_ok=True)
    centroids.to_csv(centroids_path, index=False)
    logging.info("中心点已保存: %s", centroids_path)

    cities_to_process = centroids
    if args.test:
        cities_to_process = centroids.head(3)
    elif args.resume:
        cities_to_process = centroids[~centroids["city"].isin(done_cities)]

    all_rows = []
    total = len(cities_to_process)
    for i, (_, city_row) in enumerate(cities_to_process.iterrows()):
        prov = city_row["province"]
        city = city_row["city"]
        lon = city_row["lon"]
        lat = city_row["lat"]
        logging.info("[%d/%d] %s %s (%.4f, %.4f)", i + 1, total, prov, city, lon, lat)
        rows = fetch_power_all_years(lon, lat, prov, city)
        all_rows.extend(rows)
        logging.info("  → %d 年数据", len(rows))

    if not all_rows:
        logging.warning("未获取到任何数据")
        return 0

    df = pd.DataFrame(all_rows)
    # 转换列名
    df = df.rename(columns={
        "T2M": "temp_mean_c",
        "PRECTOTCORR": "prec_mm_day",
        "ALLSKY_SFC_SW_DWN": "solar_rad_kwh_m2_day",
    })
    df["city_id"] = df["province"] + "_" + df["city"]
    df = df.sort_values(["province", "city", "year"]).reset_index(drop=True)

    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(OUT_PATH, index=False)
    logging.info("✅ 写入 %s (%d 行 × %d 列)", OUT_PATH, len(df), len(df.columns))

    print("\n=== 抽样（河南 郑州市） ===")
    sample = df[(df["province"] == "河南") & (df["city"] == "郑州市")]
    print(sample[["year", "temp_mean_c", "prec_mm_day"]].to_string(index=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
