"""Robust extractor for prefecture-level grain output from the regional yearbooks.

Scans every table in the "03 地级统计资料" section of each yearbook, keeps the
ones whose header carries a 粮食 *output* column (万吨 / Grain), and pulls the
city rows. Handles continuation tables, pinyin suffixes and full-width digits.
"""

from __future__ import annotations

import csv
import re
import sys
import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from zip_over_parts import open_split_zip  # noqa: E402

NS = {"m": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
COL_RE = re.compile(r"([A-Z]+)")

YB_SIZES = {
    3785839: 2000, 3590323: 2002, 3850017: 2003, 4082818: 2004,
    3525845: 2005, 3681149: 2006, 3587620: 2007, 3604117: 2008,
    3862523: 2009, 3758034: 2011, 2343482: 2012, 3415309: 2013, 3532025: 2014,
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
SKIP = {"其他", "直报单位", "地区", "全省", "合计", "总计"}

FULLWIDTH = {ord(c): ord("0") + i for i, c in enumerate("０１２３４５６７８９")}
FULLWIDTH[ord("．")] = ord(".")
FULLWIDTH[ord("－")] = ord("-")


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


def sheet_rows(xlsx_bytes: bytes):
    import io

    with zipfile.ZipFile(io.BytesIO(xlsx_bytes)) as zf:
        strings: list[str] = []
        with zf.open("xl/sharedStrings.xml") as stream:
            for event, elem in ET.iterparse(stream, events=("end",)):
                if elem.tag == f"{{{NS['m']}}}si":
                    strings.append("".join(t.text or "" for t in elem.iter(f"{{{NS['m']}}}t")))
                    elem.clear()
        names = [n for n in zf.namelist() if re.fullmatch(r"xl/worksheets/sheet\d+\.xml", n)]
        for sheet in sorted(names):
            with zf.open(sheet) as stream:
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


def clean_name(raw: str) -> str:
    text = raw.strip()
    text = re.split(r"[A-Za-z]", text)[0].strip()
    return text


def to_number(raw: str) -> float | None:
    text = raw.translate(FULLWIDTH).strip().replace(",", "").replace(" ", "")
    if not text or text in {"-", "—", "…"}:
        return None
    if not re.fullmatch(r"-?\d+(\.\d+)?", text):
        return None
    return float(text)


def parse_table(data: bytes, fallback_year: int, initial_prov: str = "",
                default_grain_col: int | None = None):
    """Return (records, last_province_seen) for one table file.

    initial_prov / default_grain_col let continuation pages inherit the province
    context and column layout of the head table.
    """
    rows = list(sheet_rows(data))
    grain_col = default_grain_col
    start = 0
    year = fallback_year
    for i, row in enumerate(rows[:20]):
        for j, cell in enumerate(row):
            text = cell.strip()
            if not text:
                continue
            if "粮食" in text and "播种面积" not in text and ("万吨" in text or "Grain" in text or text.replace(" ", "").startswith("粮食")):
                grain_col = j
                start = i + 1
                break
        if grain_col is not None and default_grain_col is None:
            title = " ".join(rows[k][0] if rows[k] else "" for k in range(min(3, len(rows))))
            match = re.search(r"(\d{4})\s*年", title)
            if match:
                year = int(match.group(1))
            break
    if grain_col is None:
        return [], initial_prov

    current_prov = initial_prov
    out = []
    for row in rows[start:]:
        if not row:
            continue
        name = clean_name(row[0] if row else "")
        if not name:
            continue
        if "续表" in name or name in SKIP:
            continue
        if name in PROVINCES:
            current_prov = name
            continue
        if not name.endswith(CITY_SUFFIX) or name.endswith(("区", "县")):
            continue
        value = to_number(row[grain_col]) if grain_col < len(row) else None
        if value is None:
            continue
        if current_prov in MUNI and name != current_prov:
            continue
        out.append((year, current_prov, name, value))
    return out, current_prov


def main() -> int:
    chunks = Path(r"D:\DC\DC-AIino\data\raw\statistical_yearbook_chunks")
    work = Path(r"D:\DC\_scan\yb2\raw")
    work.mkdir(parents=True, exist_ok=True)

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

    records: dict[tuple[int, str, str], tuple[float, str]] = {}
    for zp in sorted(work.glob("yb*.zip")):
        match = re.search(r"yb(\d{4})", zp.name)
        fallback = (int(match.group(1)) - 1) if match else 0
        kept = 0
        with zipfile.ZipFile(zp) as zf:
            for info in zf.infolist():
                if info.is_dir():
                    continue
                name = decode(info.filename)
                if not name.lstrip().startswith("03"):
                    continue
                data = zf.read(info)
                if data[:2] != b"PK":
                    continue  # 旧式 .xls，另行处理
                try:
                    rows, _ = parse_table(data, fallback)
                except Exception:
                    continue
                for year, prov, city, value in rows:
                    key = (year, prov, city)
                    if key not in records:
                        records[key] = (value, Path(name).name)
                        kept += 1
        years = sorted({k[0] for k in records})
        print(f"  {zp.name}: +{kept} 条 (累计去重 {len(records)}, 年份 {years})")

    out = Path(r"D:\DC\_scan\city_yield_raw.csv")
    with out.open("w", newline="", encoding="utf-8-sig") as fh:
        writer = csv.writer(fh)
        writer.writerow(["年份", "省份", "地级市", "粮食产量(万吨)", "来源表"])
        for (year, prov, city), (value, src) in sorted(records.items()):
            writer.writerow([year, prov, city, value, src])
    print(f"total {len(records)} -> {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
