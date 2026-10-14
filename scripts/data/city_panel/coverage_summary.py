"""Coverage by province: data years, city counts, official vs estimate."""

from __future__ import annotations

import csv
from collections import defaultdict
from pathlib import Path

CSV_PATH = Path(r"D:\DC\deliverables\city-grain-data\主产区市级面板_2000_2024.csv")
MAIN = ["河北省", "内蒙古自治区", "辽宁省", "吉林省", "黑龙江省", "江苏省", "安徽省",
        "江西省", "山东省", "河南省", "湖北省", "湖南省", "四川省"]


def main() -> int:
    rows = list(csv.DictReader(CSV_PATH.open(encoding="utf-8-sig")))
    years: dict[str, set] = defaultdict(set)
    cities: dict[str, set] = defaultdict(set)
    official: dict[str, int] = defaultdict(int)
    estimate: dict[str, int] = defaultdict(int)
    for r in rows:
        prov = r["省份"]
        years[prov].add(int(r["年份"]))
        cities[prov].add(r["地级市"])
        if r["产量数据来源"] == "县级加总校准估算":
            estimate[prov] += 1
        else:
            official[prov] += 1
    lines = ["省份,城市数,有数据的年份数,年份区间,官方值条数,估算值条数"]
    for prov in MAIN:
        ys = sorted(years[prov])
        lines.append(
            f"{prov},{len(cities[prov])},{len(ys)},{ys[0]}-{ys[-1]},{official[prov]},{estimate[prov]}"
        )
    Path(r"D:\DC\_scan\coverage.csv").write_text("\n".join(lines), encoding="utf-8-sig")
    print("\n".join(lines))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
