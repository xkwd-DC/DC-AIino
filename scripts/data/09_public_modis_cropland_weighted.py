#!/usr/bin/env python3
"""v4w：用公开数据做一版可验证的耕地加权 MODIS 面板（不改原 v4）。

背景
----
原 v4 的 8b 只新增了 ``cropland_ratio``，NDVI / LST 仍是全省域均值。
本机又拿不到 CLCD 30 m 原始栅格（Zenodo DNS 被拦）和 MODIS HDF
（Earthdata 账号为空），所以这里走一条公开数据替代路线：

  NDVI   MOD13A1 500 m 16-day（Terra，Planetary Computer COG）
  LST    MYD11A2 1 km 8-day（Aqua，Planetary Computer COG）
  耕地   ESA CCI LC 300 m 2020（class 10–20=1，30=0.5，40=0.25）

输出单独写到 ``modis_province_monthly_v4w.parquet``，不覆盖
``modis_province_monthly.parquet`` 或 ``paper_panel_v4.parquet``。
报告会明确写：这是 **ESA CCI 掩膜 + MODIS 公开 COG** 的试算，
不是 CLCD 30 m 的最终口径。

用法
----
    python scripts/data/09_public_modis_cropland_weighted.py --year 2022 --months 6
    python scripts/data/09_public_modis_cropland_weighted.py --year 2022
    python scripts/data/09_public_modis_cropland_weighted.py --year 2022 --provinces 河南,山东,新疆

网络只访问：
  - planetarycomputer.microsoft.com（STAC + SAS）
  - modiseuwest.blob.core.windows.net / landcoverdata.blob.core.windows.net（COG）
"""
from __future__ import annotations

import argparse
import logging
import re
import sys
import time
from datetime import date, timedelta
from pathlib import Path

import geopandas as gpd
import numpy as np
import pandas as pd
import rasterio
import requests
from rasterio.features import bounds as geom_bounds
from rasterio.features import geometry_mask
from rasterio.warp import Resampling, reproject, transform_bounds, transform_geom
from rasterio.windows import from_bounds
from shapely.geometry import shape
from tqdm import tqdm

PROJECT_ROOT = Path(__file__).resolve().parents[2]
PROVINCE_GEOJSON = (
    PROJECT_ROOT
    / "data"
    / "raw"
    / "gis_province"
    / "tianditu"
    / "province_2024_GS2024-0650.geojson"
)
PANEL_V4 = PROJECT_ROOT / "data" / "interim" / "paper_panel_v4.parquet"
MODIS_V3 = PROJECT_ROOT / "data" / "interim" / "modis_province_monthly.parquet"
DEFAULT_OUT = PROJECT_ROOT / "data" / "interim" / "modis_province_monthly_v4w.parquet"
DEFAULT_REPORT = PROJECT_ROOT / "reports" / "modis_v4w_pilot.md"
DEFAULT_PARTS_DIR = PROJECT_ROOT / "data" / "interim" / "v4w_parts"
CACHE_DIR = PROJECT_ROOT / "data" / "interim" / "cropfrac_cache"

STAC_SEARCH = "https://planetarycomputer.microsoft.com/api/stac/v1/search"
SAS_SIGN = "https://planetarycomputer.microsoft.com/api/sas/v1/sign"

CHINA_BBOX = [73.0, 18.0, 135.0, 54.0]
NDVI_COLLECTION = "modis-13A1-061"
LST_COLLECTION = "modis-11A2-061"
LC_COLLECTION = "esa-cci-lc"

NDVI_ASSET = "500m_16_days_NDVI"
NDVI_SCALE = 0.0001
NDVI_NODATA = -3000
LST_SCALE = 0.02
LST_NODATA = 0

# ESA CCI LC LCCS classes:
#   10-20 cropland / mosaic cropland, 30 mosaic cropland (>50%), 40 mosaic natural veg
CROP_WEIGHTS = {10: 1.0, 11: 1.0, 12: 1.0, 20: 1.0, 30: 0.5, 40: 0.25}

DOY_RE = re.compile(r"A(\d{4})(\d{3})")
TILE_RE = re.compile(r"h(\d{2})v(\d{2})")
_SAS_QUERY_CACHE: dict[str, str] = {}


def sign_href(href: str, retries: int = 4) -> str:
    from urllib.parse import urlparse

    parsed = urlparse(href)
    container = "/".join(parsed.path.split("/")[:2])
    cache_key = f"{parsed.scheme}://{parsed.netloc}{container}"
    if cache_key in _SAS_QUERY_CACHE:
        return f"{href}?{_SAS_QUERY_CACHE[cache_key]}"

    last_err: Exception | None = None
    for attempt in range(retries):
        try:
            resp = requests.get(SAS_SIGN, params={"href": href}, timeout=60)
            if resp.status_code == 429:
                time.sleep(8 * (attempt + 1))
                continue
            resp.raise_for_status()
            payload = resp.json()
            if "href" in payload:
                signed = payload["href"]
                _SAS_QUERY_CACHE[cache_key] = urlparse(signed).query
                return signed
            last_err = KeyError(payload)
        except Exception as exc:  # noqa: BLE001 - retry the network boundary
            last_err = exc
        time.sleep(1.5 * (attempt + 1))
    raise RuntimeError(f"SAS 签名失败: {href[:120]}") from last_err


def stac_search(
    collection: str,
    bbox: list[float],
    start: date,
    end: date,
    limit: int = 500,
) -> list[dict]:
    body = {
        "collections": [collection],
        "bbox": bbox,
        "datetime": f"{start.isoformat()}T00:00:00Z/{end.isoformat()}T23:59:59Z",
        "limit": limit,
    }
    resp = requests.post(STAC_SEARCH, json=body, timeout=90)
    resp.raise_for_status()
    return resp.json().get("features", [])


def load_provinces() -> gpd.GeoDataFrame:
    gdf = gpd.read_file(PROVINCE_GEOJSON)
    gdf = gdf[gdf["name"] != "境界线"].copy()
    gdf = gdf[~gdf["name"].isin({"香港特别行政区", "澳门特别行政区", "台湾省"})].copy()
    gdf.set_crs("EPSG:4326", allow_override=True, inplace=True)
    gdf["province_code"] = gdf["gb"].astype(str).str[-6:]
    return gdf.reset_index(drop=True)


def item_tile(item_id: str) -> str | None:
    match = TILE_RE.search(item_id)
    return f"h{match.group(1)}v{match.group(2)}" if match else None


def item_date(item_id: str) -> date | None:
    match = DOY_RE.search(item_id)
    if not match:
        return None
    year, doy = int(match.group(1)), int(match.group(2))
    return date(year, 1, 1) + timedelta(days=doy - 1)


def crop_fraction_for_tile(
    ds: rasterio.DatasetReader,
    tile: str,
    resolution_tag: str,
) -> np.ndarray:
    """把 ESA CCI LC 2020 耕地类别投影到 MODIS tile 网格，返回 0–1 权重。"""
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    cache_path = CACHE_DIR / f"esa_cci_2020_{resolution_tag}_{tile}.npy"
    if cache_path.exists():
        return np.load(cache_path)

    tile_bbox = transform_bounds(ds.crs, "EPSG:4326", *ds.bounds)
    items = stac_search(LC_COLLECTION, list(tile_bbox), date(2020, 1, 1), date(2020, 12, 31))
    if not items:
        raise RuntimeError(f"{tile}: 找不到 ESA CCI LC 2020")

    weight_sum = np.zeros((ds.height, ds.width), dtype=np.float32)
    valid_sum = np.zeros((ds.height, ds.width), dtype=np.float32)

    for item in items:
        with rasterio.open(sign_href(item["assets"]["lccs_class"]["href"])) as cci:
            left = max(tile_bbox[0], cci.bounds.left)
            right = min(tile_bbox[2], cci.bounds.right)
            bottom = max(tile_bbox[1], cci.bounds.bottom)
            top = min(tile_bbox[3], cci.bounds.top)
            if left >= right or bottom >= top:
                continue
            cwin = from_bounds(left, bottom, right, top, transform=cci.transform)
            cwin = cwin.round_offsets().round_lengths()
            classes = cci.read(1, window=cwin)

            weights = np.zeros(classes.shape, dtype=np.float32)
            for cls, weight in CROP_WEIGHTS.items():
                weights[classes == cls] = weight
            valid = (classes > 0).astype(np.float32)

            warped_w = np.zeros(weight_sum.shape, dtype=np.float32)
            warped_v = np.zeros(valid_sum.shape, dtype=np.float32)
            src_transform = cci.window_transform(cwin)
            reproject(
                source=weights,
                destination=warped_w,
                src_transform=src_transform,
                src_crs=cci.crs,
                dst_transform=ds.transform,
                dst_crs=ds.crs,
                resampling=Resampling.average,
            )
            reproject(
                source=valid,
                destination=warped_v,
                src_transform=src_transform,
                src_crs=cci.crs,
                dst_transform=ds.transform,
                dst_crs=ds.crs,
                resampling=Resampling.average,
            )
            weight_sum += warped_w
            valid_sum += warped_v

    crop_fraction = np.divide(
        weight_sum,
        valid_sum,
        out=np.zeros_like(weight_sum),
        where=valid_sum > 0,
    )
    np.clip(crop_fraction, 0.0, 1.0, out=crop_fraction)
    np.save(cache_path, crop_fraction)
    return crop_fraction


def weighted_stats(
    values: np.ndarray,
    valid: np.ndarray,
    weights: np.ndarray,
    scale: float,
) -> tuple[float | None, float | None, int, float, float]:
    """返回 weighted mean/std、有效像元数、耕地权重占比、有效像元占比。"""
    weight_valid = valid & (weights > 0)
    valid_count = int(weight_valid.sum())
    if valid_count == 0:
        return None, None, 0, 0.0, float(valid.mean())

    x = values[weight_valid].astype(np.float64) * scale
    w = weights[weight_valid].astype(np.float64)
    w_sum = float(w.sum())
    mean = float((x * w).sum() / w_sum)
    var = float((w * (x - mean) ** 2).sum() / w_sum)
    crop_ratio = float(w_sum / max(int(valid.sum()), 1))
    return mean, var**0.5, valid_count, crop_ratio, float(valid.mean())


def province_masks_for_tile(
    gdf: gpd.GeoDataFrame,
    ds: rasterio.DatasetReader,
) -> dict[str, tuple[dict, np.ndarray]]:
    tile_bbox = transform_bounds(ds.crs, "EPSG:4326", *ds.bounds)
    masks: dict[str, tuple[dict, np.ndarray]] = {}
    for row in gdf.itertuples(index=False):
        b = row.geometry.bounds
        if b[2] <= tile_bbox[0] or b[0] >= tile_bbox[2]:
            continue
        if b[3] <= tile_bbox[1] or b[1] >= tile_bbox[3]:
            continue
        geom = transform_geom("EPSG:4326", ds.crs, row.geometry)
        mask = geometry_mask(
            [geom],
            out_shape=(ds.height, ds.width),
            transform=ds.transform,
            invert=True,
            all_touched=False,
        )
        if mask.any():
            masks[row.province_code] = (geom, mask)
    return masks


def collect_month(
    year: int,
    month: int,
    collection: str,
    id_prefix: str,
    asset_names: list[str],
    scale: float,
    nodata: int,
    gdf: gpd.GeoDataFrame,
    max_tiles: int | None,
    composite_days: int,
) -> dict[tuple[str, int, int], dict[str, float | int | None]]:
    start = date(year, month, 1)
    end = (start.replace(day=28) + timedelta(days=4)).replace(day=1) - timedelta(days=1)
    items = stac_search(collection, CHINA_BBOX, start, end)
    items = [it for it in items if it["id"].startswith(id_prefix)]
    by_tile: dict[str, list[dict]] = {}
    for item in items:
        tile = item_tile(item["id"])
        if not tile:
            continue
        item_geom = shape(item["geometry"])
        if not gdf.geometry.intersects(item_geom).any():
            continue
        by_tile.setdefault(tile, []).append(item)

    if max_tiles is not None:
        by_tile = dict(list(by_tile.items())[:max_tiles])

    records: dict[tuple[str, int, int], dict[str, list[float]]] = {}
    for tile, tile_items in tqdm(by_tile.items(), desc=f"{id_prefix} {year}-{month:02d}"):
        tile_items.sort(key=lambda it: it["id"])
        with rasterio.open(sign_href(tile_items[0]["assets"][asset_names[0]]["href"])) as ds:
            resolution_tag = "500m" if ds.width >= 2000 else "1km"
            crop_fraction = crop_fraction_for_tile(ds, tile, resolution_tag)
            masks = province_masks_for_tile(gdf, ds)
            if not masks:
                continue

            for item in tile_items:
                d = item_date(item["id"])
                if d is not None:
                    d = d + timedelta(days=composite_days // 2)
                if d is None or d.year != year or d.month != month:
                    continue
                for asset_name in asset_names:
                    with rasterio.open(sign_href(item["assets"][asset_name]["href"])) as band_ds:
                        values = band_ds.read(1)
                        if band_ds.width != ds.width or band_ds.height != ds.height:
                            logging.warning("%s %s 尺寸不一致，跳过", item["id"], asset_name)
                            continue
                        if nodata != 0:
                            valid = (values != nodata) & (values >= -2000) & (values <= 10000)
                        else:
                            valid = (values > 0) & (values < 65535)
                        for code, (_, mask) in masks.items():
                            mean, std, count, crop_ratio, _ = weighted_stats(
                                values, valid & mask, crop_fraction, scale
                            )
                            if mean is None:
                                continue
                            key = (code, year, month)
                            rec = records.setdefault(key, {})
                            rec.setdefault(f"{asset_name}_values", []).append(mean)
                            rec.setdefault(f"{asset_name}_stds", []).append(std)
                            rec[f"{asset_name}_valid_count"] = count
                            rec[f"{asset_name}_crop_ratio"] = crop_ratio

    out: dict[tuple[str, int, int], dict[str, float | int | None]] = {}
    for key, rec in records.items():
        row: dict[str, float | int | None] = {}
        for asset_name in asset_names:
            values = rec.get(f"{asset_name}_values", [])
            stds = rec.get(f"{asset_name}_stds", [])
            if values:
                row[f"{asset_name}_mean"] = float(np.mean(values))
                row[f"{asset_name}_std"] = float(np.mean([s for s in stds if s is not None]))
            else:
                row[f"{asset_name}_mean"] = None
                row[f"{asset_name}_std"] = None
            row[f"{asset_name}_valid_count"] = rec.get(f"{asset_name}_valid_count", 0)
            row[f"{asset_name}_crop_ratio"] = rec.get(f"{asset_name}_crop_ratio", 0.0)
        out[key] = row
    return out


def write_report(
    out: pd.DataFrame,
    year: int,
    report_path: Path,
) -> None:
    report_path.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        f"# MODIS v4w 试算报告（{year}）",
        "",
        "> 口径：MOD13A1 500 m 16-day NDVI + MYD11A2 1 km 8-day LST + ESA CCI LC 300 m 2020 耕地权重。",
        "> 这是公开数据替代版，**不是** CLCD 30 m 的最终 v4。",
        "",
        "## 覆盖",
        "",
        f"- 行数：{len(out)}",
        f"- 省份：{out['province_code'].nunique()}",
        f"- 月份：{out['month'].nunique()}",
        "",
    ]

    if MODIS_V3.exists() and not out.empty:
        v3 = pd.read_parquet(MODIS_V3)
        keys = out[["province_code", "year", "month"]].drop_duplicates()
        v3 = v3.merge(keys, on=["province_code", "year", "month"], how="inner")
        if v3.empty:
            lines += ["## 对比", "", "v3 月度面板没有匹配到相同省份-月份。", ""]
            report_path.write_text("\n".join(lines), encoding="utf-8")
            return
        v3_annual = (
            v3.groupby("province_code", as_index=False)["ndvi_mean"]
            .mean()
            .rename(columns={"ndvi_mean": "v3_ndvi"})
        )
        v4w_annual = (
            out.groupby("province_code", as_index=False)["ndvi_mean"]
            .mean()
            .rename(columns={"ndvi_mean": "v4w_ndvi"})
        )
        cmp = v3_annual.merge(v4w_annual, on="province_code", how="inner")
        cmp["delta"] = cmp["v4w_ndvi"] - cmp["v3_ndvi"]
        cmp = cmp.sort_values("delta", ascending=False)
        lines += [
            "## 覆盖月份均值对比（v4w − v3）",
            "",
            "| province_code | v3 NDVI | v4w NDVI | Δ |",
            "|---|---:|---:|---:|",
        ]
        for row in cmp.head(15).itertuples(index=False):
            lines.append(
                f"| {row.province_code} | {row.v3_ndvi:.4f} | {row.v4w_ndvi:.4f} | {row.delta:+.4f} |"
            )
        lines += [
            "",
            f"- Δ 均值：{cmp['delta'].mean():+.4f}",
            f"- Δ 中位：{cmp['delta'].median():+.4f}",
            f"- 上浮省份数：{int((cmp['delta'] > 0).sum())} / {len(cmp)}",
            "",
        ]

    if "ndvi_crop_ratio" in out.columns and not out.empty:
        lines += [
            "## 耕地权重",
            "",
            f"- `ndvi_crop_ratio` 均值：{out['ndvi_crop_ratio'].mean():.4f}",
            f"- `ndvi_crop_ratio` 范围：{out['ndvi_crop_ratio'].min():.4f} – {out['ndvi_crop_ratio'].max():.4f}",
            "",
        ]

    report_path.write_text("\n".join(lines), encoding="utf-8")
    logging.info("报告写入 %s", report_path)


def records_to_frame(
    records: dict[tuple[str, int, int], dict[str, float | int | None]],
    gdf: gpd.GeoDataFrame,
) -> pd.DataFrame:
    name_by_code = dict(zip(gdf["province_code"], gdf["name"]))
    rows = []
    for (code, year, month), rec in records.items():
        rows.append(
            {
                "province_code": code,
                "province": name_by_code.get(code, ""),
                "year": year,
                "month": month,
                "ndvi_mean": rec.get(f"{NDVI_ASSET}_mean"),
                "ndvi_std": rec.get(f"{NDVI_ASSET}_std"),
                "ndvi_valid_count": rec.get(f"{NDVI_ASSET}_valid_count", 0),
                "ndvi_crop_ratio": rec.get(f"{NDVI_ASSET}_crop_ratio", 0.0),
                "lst_day_mean_k": rec.get("LST_Day_1km_mean"),
                "lst_day_std_k": rec.get("LST_Day_1km_std"),
                "lst_day_valid_count": rec.get("LST_Day_1km_valid_count", 0),
                "lst_night_mean_k": rec.get("LST_Night_1km_mean"),
                "lst_night_std_k": rec.get("LST_Night_1km_std"),
                "lst_night_valid_count": rec.get("LST_Night_1km_valid_count", 0),
                "lst_crop_ratio": rec.get("LST_Day_1km_crop_ratio", 0.0),
                "mask_source": "ESA_CCI_LC_300m_2020",
                "product_source": "MOD13A1_500m_16d + MYD11A2_1km_8d",
            }
        )
    return pd.DataFrame(rows)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="公开数据版耕地加权 MODIS 面板")
    parser.add_argument("--year", type=int, required=True)
    parser.add_argument("--months", type=str, default="1-12")
    parser.add_argument("--provinces", type=str, default="", help="逗号分隔的省名，默认全部 31 省")
    parser.add_argument("--max-tiles", type=int, default=None)
    parser.add_argument("--skip-lst", action="store_true", help="只算 NDVI，先快速验证")
    parser.add_argument("--parts-dir", type=Path, default=DEFAULT_PARTS_DIR)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--report", type=Path, default=DEFAULT_REPORT)
    parser.add_argument("--verbose", "-v", action="store_true")
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
        datefmt="%H:%M:%S",
    )

    lo, hi = args.months.split("-", 1) if "-" in args.months else (args.months, args.months)
    months = list(range(int(lo), int(hi) + 1))

    gdf = load_provinces()
    if args.provinces:
        wanted = [p.strip() for p in args.provinces.split(",") if p.strip()]
        gdf = gdf[gdf["name"].isin(wanted)].copy()
        if gdf.empty:
            logging.error("没有匹配到省份：%s", wanted)
            return 2
    logging.info("省份 %d 个，月份 %s，年份 %s", len(gdf), months, args.year)

    args.parts_dir.mkdir(parents=True, exist_ok=True)
    parts: list[pd.DataFrame] = []
    for month in months:
        part_path = args.parts_dir / f"v4w_{args.year}_{month:02d}.parquet"
        if part_path.exists():
            logging.info("复用断点 %s", part_path)
            parts.append(pd.read_parquet(part_path))
            continue

        ndvi = collect_month(
            args.year,
            month,
            NDVI_COLLECTION,
            "MOD13A1",
            [NDVI_ASSET],
            NDVI_SCALE,
            NDVI_NODATA,
            gdf,
            args.max_tiles,
            16,
        )
        records = dict(ndvi)
        if not args.skip_lst:
            lst = collect_month(
                args.year,
                month,
                LST_COLLECTION,
                "MYD11A2",
                ["LST_Day_1km", "LST_Night_1km"],
                LST_SCALE,
                LST_NODATA,
                gdf,
                args.max_tiles,
                8,
            )
            for key, row in lst.items():
                records.setdefault(key, {}).update(row)

        if not records:
            logging.warning("%s-%02d 没有记录", args.year, month)
            continue
        part = records_to_frame(records, gdf)
        part.to_parquet(part_path, index=False)
        logging.info("断点写入 %s（%d 行）", part_path, len(part))
        parts.append(part)

    if not parts:
        logging.error("没有产出任何省份-月记录")
        return 1

    out = (
        pd.concat(parts, ignore_index=True)
        .drop_duplicates(["province_code", "year", "month"], keep="last")
        .sort_values(["province_code", "year", "month"])
        .reset_index(drop=True)
    )
    args.out.parent.mkdir(parents=True, exist_ok=True)
    out.to_parquet(args.out, index=False)
    logging.info("写入 %s（%d 行 × %d 列）", args.out, len(out), len(out.columns))
    write_report(out, args.year, args.report)

    print(out.head(10).to_string(index=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
