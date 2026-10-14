"""Extract city-level grain output from the regional statistical yearbooks.

Source: 《中国区域经济统计年鉴》2000-2014, table "主要农产品产量", which lists
粮食产量 (10 000 tons) for every prefecture-level unit, grouped by province.
"""

from __future__ import annotations

import csv
import re
import sys
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from zip_over_parts import open_split_zip  # noqa: E402

NS = {"m": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
COL_RE = re.compile(r"([A-Z]+)")

# 分卷包内每个年鉴 Excel 的文件大小 -> 年鉴年份（数据年份通常为年鉴年份 - 1）
YB_SIZES = {
    3785839: 2000,
    3590323: 2002,
    3850017: 2003,
    4082818: 2004,
    3525845: 2005,
    3681149: 2006,
    3587620: 2007,
    3604117: 2008,
    3862523: 2009,
    3758034: 2011,
    2343482: 2012,
    3415309: 2013,
    3532025: 2014,
}

PROVINCES = {
    "北京市", "天津市", "河北省", "山西省", "内蒙古自治区", "辽宁省", "吉林省",
    "黑龙江省", "上海市", "江苏省", "浙江省", "安徽省", "福建省", "江西省",
    "山东省", "河南省", "湖北省", "湖南省", "广东省", "广西壮族自治区", "海南省",
    "重庆市", "四川省", "贵州省", "云南省", "西藏自治区", "陕西省", "甘肃省",
    "青海省", "宁夏回族自治区", "新疆维吾尔自治区",
}
MUNI = {"北京市", "天津市", "上海市", "重庆市"}
CITY_SUFFIX = ("市", "盟", "地区", "自治州")
SKIP_NAMES = {"其他", "直报单位", "地区", "全省", "合计"}


def decode(name: str) -> str:
    try:
        return name.encode("cp437").decode("gbk")
    except (UnicodeEncodeError, UnicodeDecodeError):
        return name


def col_index(ref: str) -> int:
    letters = COL_RE.match(ref).group(1)
    value = 0
    for ch in letters:
        value = value * 26 + (ord(ch) - 64)
    return value - 1


def sheet_rows(xlsx: Path):
    import xml.etree.ElementTree as ET

    with zipfile.ZipFile(xlsx) as zf:
        strings: list[str] = []
        with zf.open("xl/sharedStrings.xml") as stream:
            for event, elem in ET.iterparse(stream, events=("end",)):
                if elem.tag == f"{{{NS['m']}}}si":
                    strings.append("".join(t.text or "" for t in elem.iter(f"{{{NS['m']}}}t")))
                    elem.clear()
        with zf.open("xl/worksheets/sheet1.xml") as stream:
            for event, elem in ET.iterparse(stream, events=("end",)):
                if elem.tag != f"{{{NS['m']}}}row":
                    continue
                row: list[str] = []
                for cell in elem.findall("m:c", NS):
                    idx = col_index(cell.get("r", "A1"))
                    if idx >= len(row):
                        row.extend([""] * (idx + 1 - len(row)))
                    kind = cell.get("t")
                    if kind == "inlineStr":
                        text = "".join(t.text or "" for t in cell.iter(f"{{{NS['m']}}}t"))
                    else:
                        node = cell.find("m:v", NS)
                        text = node.text if node is not None and node.text else ""
                        if kind == "s" and text.isdigit():
                            text = strings[int(text)]
                    row[idx] = text.replace("\n", "")
                yield row
                elem.clear()


def parse_table(xlsx: Path, fallback_year: int) -> list[tuple[int, str, str, float]]:
    grain_col = None
    year = fallback_year
    current_prov = ""
    out: list[tuple[int, str, str, float]] = []

    for row in sheet_rows(xlsx):
        if not row:
            continue
        if grain_col is None:
            for i, cell in enumerate(row):
                if "粮食" in cell:
                    grain_col = i
                    break
            title = " ".join(row)
            match = re.search(r"\((\d{4})\s*年", title)
            if match:
                year = int(match.group(1))
            if grain_col is not None:
                continue
        name = row[0].strip() if row else ""
        if not name:
            continue
        if name in PROVINCES:
            current_prov = name
            continue
        if name in SKIP_NAMES or "续表" in name or "开发区" in name:
            continue
        if not name.endswith(CITY_SUFFIX):
            continue
        if grain_col >= len(row):
            continue
        raw = row[grain_col].strip().replace(",", "")
        if not re.fullmatch(r"-?\d+(\.\d+)?", raw):
            continue
        if current_prov in MUNI and name != current_prov:
            continue
        out.append((year, current_prov, name, float(raw)))
    return out


def main() -> int:
    chunks = Path(r"D:\DC\DC-AIino\data\raw\statistical_yearbook_chunks")
    work = Path(r"D:\DC\_scan\yb2\raw")
    work.mkdir(parents=True, exist_ok=True)

    # 1) pull the regional yearbook zips out of the split archive
    parts = sorted(chunks.glob("*.part*.zip"))
    with open_split_zip(parts) as zf:
        for info in zf.infolist():
            if info.is_dir() or info.file_size not in YB_SIZES:
                continue
            target = work / f"yb{YB_SIZES[info.file_size]}.zip"
            if target.exists() and target.stat().st_size == info.file_size:
                continue
            with zf.open(info) as src, target.open("wb") as dst:
                while True:
                    chunk = src.read(1 << 20)
                    if not chunk:
                        break
                    dst.write(chunk)
    print(f"yearbook zips: {len(list(work.glob('yb*.zip')))}")

    # 2) parse the grain table from every yearbook
    records: list[tuple[int, str, str, float, str]] = []
    tmp = work / "tmp.xlsx"
    for zp in sorted(work.glob("yb*.zip")):
        with zipfile.ZipFile(zp) as zf:
            # 市级表位于「03 地级统计资料」；02 段是省级表，不能混用
            candidates = []
            for info in zf.infolist():
                if info.is_dir():
                    continue
                name = decode(info.filename)
                if "农产品产量" not in name:
                    continue
                if not name.lstrip().startswith("03"):
                    continue
                if zf.read(info)[:2] != b"PK":  # 老式 .xls 需另行转换
                    continue
                candidates.append((name, info))
            if not candidates:
                print(f"  {zp.name}: no city-level xlsx grain table (skipped)")
                continue
            name, info = max(candidates, key=lambda item: item[1].file_size)
            tmp.write_bytes(zf.read(info))
            match = re.search(r"yb(\d{4})", zp.name)
            fallback = (int(match.group(1)) - 1) if match else 0
            rows = parse_table(tmp, fallback)
            years = sorted({r[0] for r in rows})
            provs = sorted({r[1] for r in rows})
            print(f"  {zp.name}: {name.split('/')[-1][:26]} -> {len(rows)} 条, 年份 {years}, 省级单位 {len(provs)}")
            for year, prov, city, value in rows:
                records.append((year, prov, city, value, name))

    out = Path(r"D:\DC\_scan\city_yield_raw.csv")
    with out.open("w", newline="", encoding="utf-8-sig") as fh:
        writer = csv.writer(fh)
        writer.writerow(["年份", "省份", "地级市", "粮食产量(万吨)", "来源文件"])
        for row in sorted(records):
            writer.writerow(row)
    print(f"total records: {len(records)} -> {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
