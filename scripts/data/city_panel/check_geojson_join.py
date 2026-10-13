"""Check whether the national city geojson names match the new city panel."""

from __future__ import annotations

import csv
import json
from pathlib import Path

GEO = Path(r"D:\DC\DC-AIino\data\raw\gis_province\tianditu\中国_市.geojson")
PANEL = Path(r"D:\DC\deliverables\city-grain-data\主产区市级面板_2000_2024.csv")


def norm(name: str) -> str:
    text = (name or "").strip().split("\n")[0]
    for suffix in ("市", "地区", "盟", "自治州", "特别行政区"):
        if text.endswith(suffix):
            return text[: -len(suffix)]
    return text


def main() -> int:
    data = json.loads(GEO.read_text(encoding="utf-8"))
    geo_names = {}
    for feature in data["features"]:
        props = feature.get("properties") or {}
        name = props.get("name") or ""
        gb = props.get("gb") or ""
        if name:
            geo_names[norm(name)] = (name, gb)

    cities = []
    with PANEL.open(encoding="utf-8-sig", newline="") as fh:
        for row in csv.DictReader(fh):
            cities.append((row["省份"], row["地级市"]))
    unique = sorted(set(cities))
    hit = [c for c in unique if norm(c[1]) in geo_names]
    miss = [c for c in unique if norm(c[1]) not in geo_names]

    lines = [
        f"边界库市级要素: {len(data['features'])} 个",
        f"面板市级单位: {len(unique)} 个",
        f"名称匹配: {len(hit)}  未匹配: {len(miss)}",
        "",
        "未匹配清单:",
    ]
    for prov, city in miss:
        lines.append(f"  {prov} {city}")
    Path(r"D:\DC\_scan\geo_join.txt").write_text("\n".join(lines), encoding="utf-8")
    print(f"geo={len(data['features'])} panel={len(unique)} matched={len(hit)} missed={len(miss)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
