"""Build the prefecture-level grain output dataset for the main producing provinces.

Sources
  1. 《中国区域经济统计年鉴》2000-2014（表：地级统计资料 · 主要农产品产量）→ 全国地级单位
  2. EPS 地级市粮食产量（6 省，2011-2024）→ 与年鉴口径交叉校验
"""

from __future__ import annotations

import csv
import re
import sys
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from build_city_yield2 import decode, parse_table  # noqa: E402

MAIN_PROVINCES = [
    "河北省", "内蒙古自治区", "辽宁省", "吉林省", "黑龙江省", "江苏省",
    "安徽省", "江西省", "山东省", "河南省", "湖北省", "湖南省", "四川省",
]
MAIN_SHORT = {p: p.replace("省", "").replace("自治区", "").replace("壮族", "").replace("回族", "").replace("维吾尔", "")
              for p in MAIN_PROVINCES}

# 早期年鉴中部分地名使用繁体/异体字，需要归一到现行写法
VARIANT_MAP = str.maketrans({
    "峽": "峡", "陽": "阳", "陰": "阴", "寧": "宁", "遼": "辽", "濱": "滨",
    "濟": "济", "齊": "齐", "魯": "鲁", "蘇": "苏", "揚": "扬", "鎮": "镇",
    "興": "兴", "贛": "赣", "閩": "闽", "廣": "广", "東": "东", "瀋": "沈",
    "濰": "潍", "煙": "烟", "臨": "临", "萊": "莱", "嶽": "岳", "樂": "乐",
    "貴": "贵", "灤": "滦", "縣": "县", "關": "关", "龍": "龙", "鳳": "凤",
    "慶": "庆", "義": "义", "澤": "泽", "撫": "抚", "順": "顺", "蕪": "芜",
    "澮": "浍", "渦": "涡", "瀘": "泸", "涼": "凉", "綿": "绵", "內": "内",
    "黃": "黄", "岡": "冈", "甯": "宁", "陝": "陕", "豐": "丰", "銅": "铜",
    "錦": "锦", "營": "营", "鐵": "铁", "遜": "逊", "濱": "滨", "鶴": "鹤",
    "雞": "鸡", "鴨": "鸭", "雙": "双", "遼": "辽", "驛": "驿", "開": "开",
    "圖": "图", "會": "会", "萬": "万", "興": "兴", "澤": "泽", "滄": "沧",
})


def normalize_city(name: str) -> str:
    return name.translate(VARIANT_MAP)


def load_yearbooks(work: Path) -> dict[tuple[int, str, str], tuple[float, str]]:
    records: dict[tuple[int, str, str], tuple[float, str]] = {}
    converged = work / ".." / "converted"
    # 旧版 .xls 转出的分页文件：按年份分组，逐页携带省份上下文
    grouped: dict[str, list[Path]] = {}
    for path in sorted(converged.glob("*.xlsx")):
        grouped.setdefault(path.stem.split("_")[0], []).append(path)

    sources = sorted(work.glob("yb*.zip")) + [p for group in grouped.values() for p in group]
    for path in sources:
        if path.suffix == ".zip":
            match = re.search(r"yb(\d{4})", path.name)
            fallback = (int(match.group(1)) - 1) if match else 0
            with zipfile.ZipFile(path) as zf:
                for info in zf.infolist():
                    if info.is_dir():
                        continue
                    name = decode(info.filename)
                    short = name.split("/", 1)[-1]
                    if not name.lstrip().startswith("03"):
                        continue
                    # 只取“主要农产品产量/播种面积和农产品产量”这一张表，且排除单位面积表
                    if "农产品产量" not in short or "单位面积" in short:
                        continue
                    data = zf.read(info)
                    if data[:2] != b"PK":
                        continue
                    try:
                        rows, _ = parse_table(data, fallback)
                    except Exception:
                        continue
                    for year, prov, city, value in rows:
                        records.setdefault(
                            (year, prov, normalize_city(city)),
                            (value, "中国区域经济统计年鉴"),
                        )
        else:
            match = re.match(r"(\d{4})", path.stem)
            fallback = int(match.group(1)) if match else 0
            group = grouped.get(path.stem.split("_")[0], [])
            index = group.index(path)
            prov_ctx = ""
            grain_col = None
            for part in group[: index + 1]:
                is_head = part == group[0]
                try:
                    rows, prov_ctx = parse_table(
                        part.read_bytes(), fallback,
                        initial_prov=prov_ctx,
                        default_grain_col=None if is_head else grain_col,
                    )
                except Exception:
                    rows = []
                if is_head:
                    grain_col = 1 if rows else None  # 2008 年鉴该表粮食列为第 2 列
                if part == path:
                    for year, prov, city, value in rows:
                        if not prov:
                            continue
                        records.setdefault((year, prov, normalize_city(city)), (value, "中国区域经济统计年鉴"))
    return records


def load_eps(path: Path) -> dict[tuple[int, str, str], tuple[float, str]]:
    out: dict[tuple[int, str, str], tuple[float, str]] = {}
    with path.open(encoding="utf-8-sig") as fh:
        for row in csv.DictReader(fh):
            key = (int(row["year"]), row["province"], row["city"])
            out[key] = (float(row["production_wan_ton"]), "EPS 地级市统计年鉴")
    return out


def main() -> int:
    work = Path(r"D:\DC\_scan\yb2\raw")
    eps_path = Path(r"D:\DC\DC-AIino\data\raw\eps_yield\eps_city_yield_all.csv")
    out_dir = Path(r"D:\DC\deliverables\city-grain-data")
    out_dir.mkdir(parents=True, exist_ok=True)

    yb = load_yearbooks(work)
    eps = load_eps(eps_path)
    print(f"yearbook records: {len(yb)}  eps records: {len(eps)}")

    # 重叠年份一致性核对（同年同市两套来源对比）
    overlap = [(k, yb[k][0], eps[k][0]) for k in yb if k in eps]
    diffs = [(k, a, b, abs(a - b) / max(a, 1e-9)) for k, a, b in overlap]
    big = [d for d in diffs if d[3] > 0.05]
    print(f"overlap cells: {len(overlap)}  >5% 差异: {len(big)}")
    for k, a, b, r in sorted(big, key=lambda x: -x[3])[:5]:
        print(f"   {k[0]} {k[1]} {k[2]}: 年鉴 {a} vs EPS {b} ({r:.1%})")

    merged: dict[tuple[int, str, str], tuple[float, str]] = dict(yb)
    for key, value in eps.items():
        merged.setdefault(key, value)
    print(f"merged records: {len(merged)}")

    main_rows = [k for k in merged if k[1] in MAIN_PROVINCES]
    years = sorted({k[0] for k in main_rows})
    print(f"主产省记录: {len(main_rows)}  年份: {years}")

    long_path = out_dir / "主产区市级粮食产量_长表.csv"
    with long_path.open("w", newline="", encoding="utf-8-sig") as fh:
        writer = csv.writer(fh)
        writer.writerow(["年份", "省份", "地级市", "粮食产量(万吨)", "数据来源"])
        for key in sorted(main_rows):
            value, src = merged[key]
            writer.writerow([key[0], key[1], key[2], value, src])

    # 最新年份宽表
    latest: dict[tuple[str, str], tuple[int, float, str]] = {}
    for (year, prov, city), (value, src) in merged.items():
        if prov not in MAIN_PROVINCES:
            continue
        key = (prov, city)
        if key not in latest or year > latest[key][0]:
            latest[key] = (year, value, src)
    wide_path = out_dir / "主产区市级粮食产量_最新年份.csv"
    with wide_path.open("w", newline="", encoding="utf-8-sig") as fh:
        writer = csv.writer(fh)
        writer.writerow(["省份", "地级市", "粮食产量(万吨)", "年份", "数据来源"])
        for (prov, city), (year, value, src) in sorted(latest.items(), key=lambda x: (MAIN_PROVINCES.index(x[0][0]), x[0][1])):
            writer.writerow([prov, city, value, year, src])

    # 全国口径（含非主产省）也保留一份，便于后续扩展
    full_path = out_dir / "全国市级粮食产量_长表.csv"
    with full_path.open("w", newline="", encoding="utf-8-sig") as fh:
        writer = csv.writer(fh)
        writer.writerow(["年份", "省份", "地级市", "粮食产量(万吨)", "数据来源"])
        for key in sorted(merged):
            value, src = merged[key]
            writer.writerow([key[0], key[1], key[2], value, src])

    # 覆盖情况统计
    cover: dict[str, list[int]] = {p: [] for p in MAIN_PROVINCES}
    for key in main_rows:
        cover[key[1]].append(key[0])
    print("\n主产省覆盖：")
    for prov in MAIN_PROVINCES:
        ys = sorted(set(cover[prov]))
        if not ys:
            print(f"  {prov}: 无")
            continue
        cities = len({k[2] for k in main_rows if k[1] == prov})
        print(f"  {prov}: {cities} 市, {len(ys)} 个年份 ({ys[0]}-{ys[-1]})")
    print(f"\noutputs -> {out_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
