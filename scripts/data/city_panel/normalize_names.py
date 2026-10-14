"""Normalize city names, rebuild the city list, and remap the climate cache."""

from __future__ import annotations

import csv
import shutil
from collections import defaultdict
from pathlib import Path

PANEL = Path(r"D:\DC\DC-AIino\data\raw\statistical_yearbook_extracted\county_panel_2000_2022_interpolated.csv")
OLD_LIST = Path(r"D:\DC\_scan\cities.csv")
NEW_LIST = Path(r"D:\DC\_scan\cities2.csv")
CACHE_OLD = Path(r"D:\DC\_scan\climate_cache2")
CACHE_NEW = Path(r"D:\DC\_scan\climate_cache3")
MAIN = ["河北省", "内蒙古自治区", "辽宁省", "吉林省", "黑龙江省", "江苏省", "安徽省",
        "江西省", "山东省", "河南省", "湖北省", "湖南省", "四川省"]

FIX = {
    "巴彥淖尔市": "巴彦淖尔市",
    "荷泽市": "菏泽市",
    "准安市": "淮安市",
    "恩施上家族苗族自治州": "恩施土家族苗族自治州",
    "襄樊市": "襄阳市",
}
# 省直管市 / 已撤并市：年鉴与官方表里存在但县级面板无对应质心
FALLBACK = {
    ("湖北省", "仙桃市"): (113.4536, 30.3649),
    ("湖北省", "天门市"): (113.1659, 30.6634),
    ("湖北省", "潜江市"): (112.8994, 30.4212),
    ("河南省", "济源市"): (112.6021, 35.0690),
    ("山东省", "莱芜市"): (117.6778, 36.2144),
    ("安徽省", "巢湖市"): (117.8745, 31.6005),
}


def norm(name: str) -> str:
    text = (name or "").split("\n")[0].strip().replace("\r", "")
    return FIX.get(text, text)


def main() -> int:
    agg: dict[tuple[str, str], list[float]] = defaultdict(lambda: [0.0, 0.0, 0])
    with PANEL.open(encoding="utf-8-sig", newline="") as fh:
        reader = csv.reader(fh)
        header = next(reader)
        i_prov = header.index("所属省份")
        i_city = header.index("所属城市")
        i_lon = header.index("经度")
        i_lat = header.index("纬度")
        for row in reader:
            if len(row) <= i_lat:
                continue
            prov = norm(row[i_prov])
            if prov not in MAIN:
                continue
            city = norm(row[i_city])
            try:
                lon, lat = float(row[i_lon]), float(row[i_lat])
            except ValueError:
                continue
            item = agg[(prov, city)]
            item[0] += lon
            item[1] += lat
            item[2] += 1

    spots: dict[tuple[str, str], tuple[float, float]] = {
        k: (v[0] / v[2], v[1] / v[2]) for k, v in agg.items() if v[2]
    }
    for key, (lon, lat) in FALLBACK.items():
        spots.setdefault(key, (lon, lat))

    ordered = sorted(spots.items())
    CACHE_NEW.mkdir(parents=True, exist_ok=True)
    old_map = {}
    with OLD_LIST.open(encoding="utf-8", newline="") as fh:
        for row in csv.DictReader(fh):
            old_map[(row["province"], row["city"])] = row["key"]

    rows = []
    remapped = 0
    for index, ((prov, city), (lon, lat)) in enumerate(ordered, 1):
        key = f"{index:03d}"
        rows.append([key, prov, city, f"{lon:.4f}", f"{lat:.4f}"])
        old_key = old_map.get((prov, city))
        src = CACHE_OLD / f"{old_key}.json" if old_key else None
        dst = CACHE_NEW / f"{key}.json"
        if src and src.exists():
            shutil.copyfile(src, dst)
            remapped += 1

    with NEW_LIST.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.writer(fh)
        writer.writerow(["key", "province", "city", "lon", "lat"])
        writer.writerows(rows)
    todo = [r for r in rows if not (CACHE_NEW / f"{r[0]}.json").exists()]
    Path(r"D:\DC\_scan\todo_keys.txt").write_text("\n".join(r[0] for r in todo), encoding="utf-8")
    print(f"cities={len(rows)} cache_remapped={remapped} to_fetch={len(todo)}")
    for r in todo:
        print(f"   {r[0]} {r[1]} {r[2]} {r[3]} {r[4]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
