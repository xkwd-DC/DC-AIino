"""Aggregate the county panel to prefecture cities and measure bias vs official data."""

from __future__ import annotations

import csv
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from normalize_names import norm  # noqa: E402

PANEL = Path(r"D:\DC\DC-AIino\data\raw\statistical_yearbook_extracted\county_panel_2000_2022_interpolated.csv")
OFFICIAL = Path(r"D:\DC\deliverables\city-grain-data\全国市级粮食产量_长表.csv")
OUT = Path(r"D:\DC\_scan\city_agg.csv")
MAIN = {"河北省", "内蒙古自治区", "辽宁省", "吉林省", "黑龙江省", "江苏省", "安徽省",
        "江西省", "山东省", "河南省", "湖北省", "湖南省", "四川省"}


def num(text: str) -> float | None:
    text = (text or "").strip().replace(",", "")
    if not text:
        return None
    try:
        return float(text)
    except ValueError:
        return None


def main() -> int:
    agg: dict[tuple[str, str, int], list[float]] = defaultdict(lambda: [0.0, 0.0, 0.0, 0])
    with PANEL.open(encoding="utf-8-sig", newline="") as fh:
        reader = csv.reader(fh)
        header = next(reader)
        i_prov = header.index("所属省份")
        i_city = header.index("所属城市")
        i_year = header.index("年份")
        i_grain = header.index("粮食总产量(吨)")
        i_sown = header.index("农作物总播种面积(千公顷)")
        i_crop = header.index("常用耕地面积(公顷)")
        i_mach = header.index("农业机械总动力(万千瓦特)")
        for row in reader:
            if len(row) <= max(i_grain, i_sown, i_crop, i_mach) or row[i_prov] not in MAIN:
                continue
            year = num(row[i_year])
            if year is None:
                continue
            key = (norm(row[i_prov]), norm(row[i_city]), int(year))
            slot = agg[key]
            grain = num(row[i_grain]) or 0.0
            sown = num(row[i_sown]) or 0.0
            crop = num(row[i_crop]) or 0.0
            mach = num(row[i_mach]) or 0.0
            if grain:
                slot[0] += grain
                slot[3] += 1
            slot[1] += sown
            slot[2] += crop
            if mach:
                slot.append(mach) if False else None

    # county-level machinery is cumulative; recompute separately as max-per-city not meaningful
    rows = []
    for (prov, city, year), (grain_t, sown_kha, crop_ha, n) in sorted(agg.items()):
        if not n:
            continue
        rows.append({
            "省份": prov, "地级市": city, "年份": year,
            "县级加总_粮食产量_万吨": round(grain_t / 10000, 2),
            "县级加总_播种面积_千公顷": round(sown_kha, 2),
            "县级加总_耕地面积_公顷": round(crop_ha, 1),
            "覆盖县数": n,
        })
    print(f"aggregated city-year rows: {len(rows)}")

    official = {}
    with OFFICIAL.open(encoding="utf-8-sig", newline="") as fh:
        for row in csv.DictReader(fh):
            official[(row["省份"], row["地级市"], int(row["年份"]))] = float(row["粮食产量(万吨)"])

    diffs = []
    for row in rows:
        key = (row["省份"], row["地级市"], row["年份"])
        if key in official and row["县级加总_粮食产量_万吨"] > 0:
            off = official[key]
            diffs.append((key, off, row["县级加总_粮食产量_万吨"], row["县级加总_粮食产量_万吨"] / off))
    ratios = sorted(d[3] for d in diffs)
    print(f"overlap pairs: {len(diffs)}")
    if ratios:
        mid = ratios[len(ratios) // 2]
        print(f"加总/官方 比值: 中位 {mid:.3f}  最小 {ratios[0]:.3f}  最大 {ratios[-1]:.3f}")
        for key, off, aggv, ratio in sorted(diffs, key=lambda x: x[3])[:3]:
            print(f"   低 {key[0]}{key[1]}{key[2]}: 官方 {off} vs 加总 {aggv} ({ratio:.2f})")
        for key, off, aggv, ratio in sorted(diffs, key=lambda x: -x[3])[:3]:
            print(f"   高 {key[0]}{key[1]}{key[2]}: 官方 {off} vs 加总 {aggv} ({ratio:.2f})")

    with OUT.open("w", newline="", encoding="utf-8-sig") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)
    print(f"-> {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
