"""Validate the delivered workbook and print coverage + samples."""

from __future__ import annotations

import csv
import re
import xml.etree.ElementTree as ET
import zipfile
from collections import defaultdict
from pathlib import Path

XLSX = Path(r"D:\DC\deliverables\city-grain-data\主产区市级粮食产量与气候面板_2000_2024.xlsx")
CSV = Path(r"D:\DC\deliverables\city-grain-data\主产区市级面板_2000_2024.csv")
NS = {"m": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}


def main() -> int:
    with zipfile.ZipFile(XLSX) as zf:
        bad = zf.testzip()
        for name in zf.namelist():
            if name.endswith(".xml") or name.endswith(".rels"):
                ET.fromstring(zf.read(name))
        sheets = [n for n in zf.namelist() if n.startswith("xl/worksheets/")]
        sheet1 = ET.fromstring(zf.read("xl/worksheets/sheet1.xml"))
        rows = sheet1.findall(".//m:row", NS)
    print(f"xlsx ok={bad is None}  sheets={len(sheets)}  sheet1 rows={len(rows)}  size={XLSX.stat().st_size/1024:.0f} KB")

    data = list(csv.DictReader(CSV.open(encoding="utf-8-sig")))
    years = sorted({int(r["年份"]) for r in data})
    per_year = defaultdict(int)
    for r in data:
        per_year[int(r["年份"])] += 1
    print("每年行数:", " ".join(f"{y}:{per_year[y]}" for y in years))

    missing_climate = sum(1 for r in data if not r["年度平均气温(°C)"])
    print(f"缺少气候值的行: {missing_climate}")
    for prov in ["河北省", "黑龙江省", "四川省"]:
        for r in data:
            if r["省份"] == prov and r["年份"] in ("2024", "2013", "2010"):
                print(f"  {r['省份']} {r['地级市']} {r['年份']} 产量={r['粮食产量(万吨)']} 来源={r['产量数据来源']} "
                      f"气温={r['年度平均气温(°C)']} 降水={r['年度总降水量(mm)']} 露点={r['年度平均露点温度(°C)']}")
                break
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
