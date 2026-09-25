"""华北冬麦区数据闸门探测 — 逐省逐年判断县级"小麦播种面积/产量"是否可机读。

为什么要探:
    山西县级冬小麦面板只有 2018–2023 可机读（《山西统计年鉴》在线版
    ``zk/html/XX-YY.xls``），2014–2017 是 JPG 扫描件。要做华北六省县级面板，
    先得知道其余五省的年鉴口径是 Excel、图片还是根本没有县级分作物表。
    这是长期气候线的**唯一闸门**，不是建模问题。

探测方式（每个省 × 每个年份）:
    1. 取该年年鉴的目录帧（left.htm）——多为 GB2312/GBK 编码
    2. 抽出目录里所有 ``html/XX-YY.jpg|pdf`` 形式的表号
    3. 抽样探测同表号下的 ``.xls`` 是否真的返回 Excel
    4. 判定：命中任一 xls → 可机读；只有图片/PDF → 仅图片或PDF；都没有 → 不可达或无目录

注意:
    目录帧只链图片/PDF，不链 XLS（山西就是如此），所以必须"按表号反射探测"，
    不能靠解析目录里的链接后缀来判断可机读性。

用法:
    python -m scripts.climate_probe.probe_yearbooks --years 2018-2023 --out reports/north_china_yearbook_matrix
"""

from __future__ import annotations

import argparse
import json
import logging
import re
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path

logger = logging.getLogger(__name__)

USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120"

#: 目录里出现的表号有两种写法：山西是 "20-14"，河南是 "2014"（无连字符）
_TABLE_ID = re.compile(r"html/(\d{2}-?\d{2})\.(?:jpg|jpeg|pdf|png)", re.I)

#: Excel 的 content-type
_EXCEL_TYPES = ("application/vnd.ms-excel", "application/vnd.openxmlformats", "application/octet-stream")


@dataclass
class YearbookSource:
    """一个省的年鉴入口。

    Attributes:
        province: 省名。
        toc_templates: 目录帧 URL 模板候选（含 {year}），按顺序尝试。
        xls_templates: 与 toc_templates 一一对应的表文件模板（含 {year} 与 {table}）。
        entry_url: 人工核对用的入口页。
        verified: 该省的 URL 模板是否已被实地验证过。
        note: 备注。
    """

    province: str
    toc_templates: tuple[str, ...]
    xls_templates: tuple[str, ...]
    entry_url: str = ""
    verified: bool = False
    note: str = ""


#: 六省年鉴入口。山西模板已实地验证；其余为候选项，需本脚本跑通后才会标 verified。
SOURCES: list[YearbookSource] = [
    YearbookSource(
        province="山西",
        toc_templates=("http://tjj.shanxi.gov.cn/tjsj/tjnj/nj{year}/zk/left.htm",),
        xls_templates=("http://tjj.shanxi.gov.cn/tjsj/tjnj/nj{year}/zk/html/{table}.xls",),
        entry_url="http://tjj.shanxi.gov.cn/tjsj/tjnj/",
        verified=True,
        note=(
            "年鉴分三代发布平台：nj2000–nj2014 用 html/njcx.htm，"
            "nj2015–nj2018 用 indexch.htm（无 /zk/），nj2019 起用 /zk/indexch.htm。"
            "XLS 只在 nj2019+ 出现，对应数据年 2018–2023"
        ),
    ),
    YearbookSource(
        province="河南",
        toc_templates=(
            "https://oss.henan.gov.cn/sbgt-wztipt/attachment/hntjj/hntj/lib/tjnj/{year}nj/zk/left.htm",
            "https://oss.henan.gov.cn/sbgt-wztipt/attachment/hntjj/hntj/lib/tjnj/{year}/zk/left.htm",
        ),
        xls_templates=(
            "https://oss.henan.gov.cn/sbgt-wztipt/attachment/hntjj/hntj/lib/tjnj/{year}nj/zk/html/{table}.xls",
            "https://oss.henan.gov.cn/sbgt-wztipt/attachment/hntjj/hntj/lib/tjnj/{year}/zk/html/{table}.xls",
        ),
        entry_url="https://tjj.henan.gov.cn/tjfw/tjcbw/tjnj/",
        note="年鉴挂在 OSS 上；nj 后缀逐年不同（2023 有、2022 无），表号形如 0101.jpg 无连字符",
    ),
    YearbookSource(
        province="河北",
        toc_templates=("http://tjj.hebei.gov.cn/hetj/tjnj/nj{year}/zk/left.htm",),
        xls_templates=("http://tjj.hebei.gov.cn/hetj/tjnj/nj{year}/zk/html/{table}.xls",),
        entry_url="http://tjj.hebei.gov.cn/",
        note="入口路径 404，需先找到年鉴首页",
    ),
    YearbookSource(
        province="山东",
        toc_templates=("http://tjj.shandong.gov.cn/tjnj/nj{year}/zk/left.htm",),
        xls_templates=("http://tjj.shandong.gov.cn/tjnj/nj{year}/zk/html/{table}.xls",),
        entry_url="http://tjj.shandong.gov.cn/tjnj/",
        note="与山西同一套 /zk/ 平台，实测多数年份可机读",
    ),
    YearbookSource(
        province="北京",
        toc_templates=("https://nj.tjj.beijing.gov.cn/nj/main/{year}-tjnj/zk/left.htm",),
        xls_templates=("https://nj.tjj.beijing.gov.cn/nj/main/{year}-tjnj/zk/html/{table}.xls",),
        entry_url="https://nj.tjj.beijing.gov.cn/",
        note="北京为区县口径，冬小麦面积小",
    ),
    YearbookSource(
        province="天津",
        toc_templates=("https://stats.tj.gov.cn/tjsj_52032/tjnj/nj{year}/zk/left.htm",),
        xls_templates=("https://stats.tj.gov.cn/tjsj_52032/tjnj/nj{year}/zk/html/{table}.xls",),
        entry_url="https://stats.tj.gov.cn/tjsj_52032/tjnj/",
        note="入口可达，目录帧路径待确认",
    ),
]


def extract_table_ids(html: str) -> list[str]:
    """从目录帧 HTML 里抽出表号（保序去重后排序）。"""
    ids = {match.group(1) for match in _TABLE_ID.finditer(html or "")}
    return sorted(ids)


def toc_candidates(source: YearbookSource, year: int) -> list[tuple[str, str]]:
    """展开某个省某个年份的候选（目录帧 URL, 表模板）对，按声明顺序。

    用字符串替换而不是 str.format——表模板里还留着 {table} 占位符，
    format 会因为缺参数直接抛 KeyError。
    """
    return [
        (toc.replace("{year}", str(year)), xls.replace("{year}", str(year)))
        for toc, xls in zip(source.toc_templates, source.xls_templates)
    ]


def classify_year(xls_hits: int, image_tables: int, toc_status: str) -> str:
    """给一年定档。

    必须区分"网络不通"和"路径模板不对"——山西年鉴于 nj2019 换了发布平台，
    老年份用同一模板取会 404，那不代表数据不存在，只代表模板要换。
    """
    if toc_status == "network":
        return "站点不可达"
    if toc_status == "missing":
        return "目录不存在"
    if toc_status == "forbidden":
        return "站点拒绝访问"
    if xls_hits > 0:
        return "可机读"
    if image_tables > 0:
        return "仅图片或PDF"
    return "目录为空"


def fetch_text(url: str, timeout: int = 25) -> tuple[str | None, str]:
    """抓页面并按 UTF-8/GB2312/GBK 依次解码（统计局站点多为 GB2312）。

    Returns:
        (文本, 状态)。状态取值: ok / missing(404) / forbidden(403) / network。
    """
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    try:
        raw = urllib.request.urlopen(request, timeout=timeout).read()
    except urllib.error.HTTPError as exc:
        logger.debug("抓取失败(HTTP %s) %s", exc.code, url)
        if exc.code == 404:
            return None, "missing"
        if exc.code in (401, 403):
            return None, "forbidden"
        return None, "network"
    except (urllib.error.URLError, OSError) as exc:
        logger.debug("抓取失败 %s: %s", url, exc)
        return None, "network"

    for encoding in ("utf-8", "gb2312", "gbk"):
        try:
            return raw.decode(encoding), "ok"
        except UnicodeDecodeError:
            continue
    return raw.decode("utf-8", errors="replace"), "ok"


def probe_xls(url: str, timeout: int = 20) -> bool:
    """探测一个 .xls 是否真的存在且是 Excel。"""
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    try:
        response = urllib.request.urlopen(request, timeout=timeout)
    except (urllib.error.URLError, urllib.error.HTTPError, OSError):
        return False

    content_type = (response.headers.get("Content-Type") or "").lower()
    return any(kind in content_type for kind in _EXCEL_TYPES)


def probe_year(source: YearbookSource, year: int, sample: int = 3, pause: float = 0.4) -> dict:
    """探测一个省的一个年鉴年份，逐个候选模板回退。"""
    html = None
    toc_url = ""
    toc_status = "network"
    xls_template = ""

    for candidate_toc, candidate_xls in toc_candidates(source, year):
        html, toc_status = fetch_text(candidate_toc)
        toc_url, xls_template = candidate_toc, candidate_xls
        if html is not None:
            break
        if toc_status in ("network", "forbidden"):
            break

    if html is None:
        return {
            "province": source.province,
            "year": year,
            "status": classify_year(0, 0, toc_status),
            "tables": 0,
            "xls_hits": 0,
            "toc_url": toc_url,
        }

    table_ids = extract_table_ids(html)
    # 县级分作物表通常在后面的章节，从尾部往前抽
    candidates = table_ids[-sample:] if table_ids else []

    xls_hits = 0
    for table in candidates:
        if probe_xls(xls_template.replace("{table}", table)):
            xls_hits += 1
        time.sleep(pause)

    return {
        "province": source.province,
        "year": year,
        "status": classify_year(xls_hits, len(table_ids), "ok"),
        "tables": len(table_ids),
        "xls_hits": xls_hits,
        "toc_url": toc_url,
    }


def parse_years(spec: str) -> list[int]:
    """解析 "2018-2023" 或 "2018,2020" 形式。"""
    if "-" in spec:
        start, end = spec.split("-", 1)
        return list(range(int(start), int(end) + 1))
    return [int(part) for part in spec.split(",") if part.strip()]


def render_matrix(rows: list[dict]) -> str:
    """省份 × 年份 的状态矩阵。"""
    provinces = sorted({r["province"] for r in rows})
    years = sorted({r["year"] for r in rows})
    lookup = {(r["province"], r["year"]): r["status"] for r in rows}

    header = "| 省 | " + " | ".join(str(y) for y in years) + " | 可机读年数 |"
    divider = "|" + "---|" * (len(years) + 2)
    lines = [header, divider]

    for province in provinces:
        cells = [lookup.get((province, year), "-") for year in years]
        readable = sum(1 for c in cells if c == "可机读")
        lines.append(f"| {province} | " + " | ".join(cells) + f" | {readable} |")

    return "\n".join(lines)


def decide(rows: list[dict], min_years: int = 10) -> str:
    """按计划里写死的决策规则给结论。"""
    by_province: dict[str, int] = {}
    for row in rows:
        if row["status"] == "可机读":
            by_province[row["province"]] = by_province.get(row["province"], 0) + 1

    qualified = [p for p, n in by_province.items() if n >= min_years]
    if len(qualified) >= 3:
        return f"闸门通过：{len(qualified)} 省有 ≥{min_years} 年可机读 → 走县级面板"
    if len(qualified) >= 1:
        return (
            f"闸门部分通过：仅 {len(qualified)} 省达标（{', '.join(qualified)}）→ "
            "退市级，或改用 v6 已有的县级粮食总产量（换作物）"
        )
    return "闸门未通过：暂无可机读的省 → 退回省级长面板（全国冬麦主产省 × 20+ 年）"


def main() -> None:
    parser = argparse.ArgumentParser(prog="probe_yearbooks", description="华北冬麦区年鉴数据闸门探测")
    parser.add_argument("--years", default="2018-2023", help='年鉴年份，如 "2018-2023"')
    parser.add_argument("--out", default="reports/north_china_yearbook_matrix", help="输出前缀")
    parser.add_argument("--sample", type=int, default=3, help="每年抽样探测几个表号")
    parser.add_argument("--only", default="", help="只探某个省（逗号分隔）")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(message)s")

    years = parse_years(args.years)
    wanted = {p.strip() for p in args.only.split(",") if p.strip()}
    sources = [s for s in SOURCES if not wanted or s.province in wanted]

    rows: list[dict] = []
    for source in sources:
        for year in years:
            row = probe_year(source, year, sample=args.sample)
            row["verified_template"] = source.verified
            rows.append(row)
            logger.info(
                "%-4s %d  %-10s 表数=%-4d xls命中=%d",
                row["province"], row["year"], row["status"], row["tables"], row["xls_hits"],
            )

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.with_suffix(".json").write_text(
        json.dumps({"rows": rows, "decision": decide(rows)}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    matrix = render_matrix(rows) + "\n\n" + decide(rows) + "\n"
    out.with_suffix(".md").write_text(matrix, encoding="utf-8")
    print("\n" + matrix)


if __name__ == "__main__":
    main()
