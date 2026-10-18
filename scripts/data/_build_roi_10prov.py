#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""用天地图省界直接拼 10 主产省的 AppEEARS ROI（不依赖 geopandas）。

输入：data/raw/gis_province/tianditu/province_2024_GS2024-0650.geojson
输出：data/interim/china_roi_for_appeears.geojson

为什么不用 _build_china_roi.py：
  那个脚本要 geopandas + shapely；当前数据 venv 没装，且我们只需要 10 省，
  不需要 dissolve，直接把 10 个省级 Polygon/MultiPolygon 拼成 MultiPolygon 即可。
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "data" / "raw" / "gis_province" / "tianditu" / "province_2024_GS2024-0650.geojson"
DST = ROOT / "data" / "interim" / "china_roi_for_appeears.geojson"

PROVINCES = {
    "河北省", "河南省", "山东省", "江苏省", "安徽省",
    "湖北省", "湖南省", "四川省", "吉林省", "黑龙江省",
}


def main() -> int:
    data = json.loads(SRC.read_text(encoding="utf-8"))
    polys: list = []
    hit: list[str] = []
    for f in data["features"]:
        name = f.get("properties", {}).get("name")
        if name not in PROVINCES:
            continue
        hit.append(name)
        g = f.get("geometry") or {}
        if g.get("type") == "Polygon":
            polys.append(g["coordinates"])
        elif g.get("type") == "MultiPolygon":
            polys.extend(g["coordinates"])

    missing = PROVINCES - set(hit)
    if missing:
        raise SystemExit(f"[FATAL] 省界缺: {missing}")

    feature = {
        "type": "Feature",
        "properties": {
            "name": "10 major grain provinces (tianditu GS(2024)0650)",
            "provinces": sorted(hit),
            "polygon_count": len(polys),
        },
        "geometry": {"type": "MultiPolygon", "coordinates": polys},
    }
    out = {
        "type": "FeatureCollection",
        "name": "china_10prov_roi",
        "crs": {"type": "name", "properties": {"name": "urn:ogc:def:crs:OGC:1.3:CRS84"}},
        "features": [feature],
    }
    DST.parent.mkdir(parents=True, exist_ok=True)
    DST.write_text(json.dumps(out, ensure_ascii=False), encoding="utf-8")
    print(f"✅ {DST} | 省 {len(hit)} | Polygon 部件 {len(polys)} | {DST.stat().st_size/1024:.1f} KB")
    print("包含:", "、".join(sorted(hit)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
