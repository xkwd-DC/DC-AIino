"""Turn the cached NASA POWER monthly JSON into annual city climate rows."""

from __future__ import annotations

import csv
import json
from collections import defaultdict
from pathlib import Path

CACHE = Path(r"D:\DC\_scan\climate_cache3")
CITIES = Path(r"D:\DC\_scan\cities2.csv")
OUT = Path(r"D:\DC\_scan\city_climate.csv")
DAYS = [31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31]


def annual(payload: dict) -> dict[int, tuple[float, float, float]]:
    params = payload["properties"]["parameter"]
    temp, prec, dew = params["T2M"], params["PRECTOTCORR"], params["T2MDEW"]
    buckets: dict[int, list[list[float]]] = defaultdict(list)
    for key, value in temp.items():
        if len(key) != 6 or not key.isdigit() or value is None:
            continue
        year, month = int(key[:4]), int(key[4:6])
        p, d = prec.get(key), dew.get(key)
        if p is None or d is None or not 1 <= month <= 12:
            continue
        buckets[year].append([value, p * DAYS[month - 1], d])
    out = {}
    for year, rows in buckets.items():
        if len(rows) < 12:
            continue
        out[year] = (
            round(sum(r[0] for r in rows) / len(rows), 2),
            round(sum(r[1] for r in rows), 1),
            round(sum(r[2] for r in rows) / len(rows), 2),
        )
    return out


def main() -> int:
    with CITIES.open(encoding="utf-8", newline="") as fh:
        cities = list(csv.DictReader(fh))
    rows = []
    missing = 0
    for city in cities:
        path = CACHE / f"{city['key']}.json"
        if not path.exists():
            missing += 1
            continue
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            missing += 1
            continue
        for year, (t, p, d) in sorted(annual(payload).items()):
            rows.append([city["province"], city["city"], year, t, p, d])
    with OUT.open("w", newline="", encoding="utf-8-sig") as fh:
        writer = csv.writer(fh)
        writer.writerow(["省份", "地级市", "年份", "年度平均气温(°C)", "年度总降水量(mm)", "年度平均露点温度(°C)"])
        writer.writerows(rows)
    print(f"rows={len(rows)} missing_cities={missing} -> {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
