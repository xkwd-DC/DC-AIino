"""Write the city centroid list used by the climate fetch (index-based keys)."""

from __future__ import annotations

import csv
from collections import defaultdict
from pathlib import Path

PANEL = Path(r"D:\DC\DC-AIino\data\raw\statistical_yearbook_extracted\county_panel_2000_2022_interpolated.csv")
OUT = Path(r"D:\DC\_scan\cities.csv")
MAIN = ["河北省", "内蒙古自治区", "辽宁省", "吉林省", "黑龙江省", "江苏省", "安徽省",
        "江西省", "山东省", "河南省", "湖北省", "湖南省", "四川省"]


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
            if len(row) <= i_lat or row[i_prov] not in MAIN:
                continue
            try:
                lon, lat = float(row[i_lon]), float(row[i_lat])
            except ValueError:
                continue
            item = agg[(row[i_prov], row[i_city])]
            item[0] += lon
            item[1] += lat
            item[2] += 1

    rows = []
    for index, ((prov, city), (lon_sum, lat_sum, n)) in enumerate(sorted(agg.items()), 1):
        if not n:
            continue
        rows.append([f"{index:03d}", prov, city, f"{lon_sum / n:.4f}", f"{lat_sum / n:.4f}"])

    with OUT.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.writer(fh)
        writer.writerow(["key", "province", "city", "lon", "lat"])
        writer.writerows(rows)
    print(f"{len(rows)} cities -> {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
