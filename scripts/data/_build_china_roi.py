"""从天地图省级矢量构建 AppEEARS 提交用的中国 ROI GeoJSON。

输入：data/raw/gis_province/tianditu/province_2024_GS2024-0650.geojson
输出：data/interim/china_roi_for_appeears.geojson

操作：
  1. 排除 8 条「境界线」feature（只保留 34 个行政区面）
  2. 全部 dissolve 为单个 (Multi)Polygon
  3. Douglas-Peucker 简化到 ~0.02° 容差，把顶点压到 ~5000 量级
  4. 输出为 EPSG:4326（AppEEARS 要 WGS84）—— CGCS2000(EPSG:4490) 与 WGS84
     在中国大陆经纬度差异 < 1 米，可直接当 WGS84 用

CLI:
    python scripts/data/_build_china_roi.py
    python scripts/data/_build_china_roi.py --tolerance 0.05  # 更激进简化
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

import geopandas as gpd
from shapely.geometry import mapping

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_INPUT = PROJECT_ROOT / "data" / "raw" / "gis_province" / "tianditu" / "province_2024_GS2024-0650.geojson"
DEFAULT_OUTPUT = PROJECT_ROOT / "data" / "interim" / "china_roi_for_appeears.geojson"


def build_roi(src: Path, dest: Path, *, tolerance_deg: float = 0.02) -> dict:
    logging.info("读 %s", src)
    gdf = gpd.read_file(src)
    logging.info("原始 features: %d", len(gdf))

    admin = gdf[gdf["name"] != "境界线"].copy()
    logging.info("排除境界线后 %d 个行政区", len(admin))

    # CGCS2000 与 WGS84 在中国境内差异可忽略，直接当 WGS84 用
    admin.set_crs("EPSG:4326", allow_override=True, inplace=True)

    union = admin.geometry.union_all()
    logging.info(
        "dissolve 后几何类型 %s，原始顶点数 ~%d",
        union.geom_type,
        sum(len(p.exterior.coords) for p in (union.geoms if union.geom_type == "MultiPolygon" else [union])),
    )

    simplified = union.simplify(tolerance_deg, preserve_topology=True)
    vert_count = sum(
        len(p.exterior.coords)
        for p in (simplified.geoms if simplified.geom_type == "MultiPolygon" else [simplified])
    )
    logging.info("化简 (tolerance=%.3f°) 后顶点数 ~%d", tolerance_deg, vert_count)
    logging.info("最终 bounds: %s", simplified.bounds)

    feature_collection = {
        "type": "FeatureCollection",
        "name": "china_admin_dissolved",
        "crs": {"type": "name", "properties": {"name": "urn:ogc:def:crs:OGC:1.3:CRS84"}},
        "features": [
            {
                "type": "Feature",
                "properties": {
                    "name": "China (34 admin units, tianditu GS(2024)0650, dissolved)",
                    "tolerance_deg": tolerance_deg,
                    "vertices_approx": vert_count,
                },
                "geometry": mapping(simplified),
            }
        ],
    }

    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(json.dumps(feature_collection, ensure_ascii=False), encoding="utf-8")
    logging.info("写入 %s (%.1f KB)", dest, dest.stat().st_size / 1024)
    return feature_collection


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="构建 AppEEARS 提交用中国 ROI")
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--tolerance", type=float, default=0.02, help="化简容差（°），默认 0.02 ≈ 2 km")
    parser.add_argument("--verbose", "-v", action="store_true")
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
        datefmt="%H:%M:%S",
    )

    if not args.input.exists():
        logging.error("找不到天地图省界文件 %s——先用 02_download_province_geojson.py 拿手动下", args.input)
        return 1

    build_roi(args.input, args.output, tolerance_deg=args.tolerance)
    return 0


if __name__ == "__main__":
    sys.exit(main())
