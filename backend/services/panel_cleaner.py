"""M08 数据整备：把用户上传的表清洗成可复现的面板。

职责边界
========
- 只读沙盒：不写 county.db / grain.db，不产出风险结论。
- 只做三件事：字段对齐、单位归一、质量检查；气候特征按模式回填。
- 输出三样：清洗后面板 CSV、质检报告 Markdown、可复现脚本。

为什么不做"通用清洗器"
======================
规则全部来自本项目做 14,388 条县级面板时踩过的坑：公顷/千公顷混用、
重名县、市辖区合计行、总产与单产互相矛盾、年份缺口、2023 年无真值。
这些是农业统计表的真实形态，通用清洗器不知道它们的存在。
"""

from __future__ import annotations

import hashlib
import json
import re
import sqlite3
from functools import lru_cache
from pathlib import Path
from typing import Any

import pandas as pd

BACKEND_DIR = Path(__file__).resolve().parents[1]
COUNTY_DB = BACKEND_DIR / "data" / "county.db"

# 县级面板里可回填的气候列（顺序即导出顺序）
CLIMATE_FIELDS: list[tuple[str, str, str]] = [
    ("gs_tmax_mean", "生长季最高气温均值", "°C"),
    ("gs_tmin_mean", "生长季最低气温均值", "°C"),
    ("gs_ppt", "生长季降水", "mm"),
    ("gs_srad", "生长季辐射", "W/m²"),
    ("gs_pet", "生长季潜在蒸散", "mm"),
    ("gdd10", "≥10℃ 积温", "℃·d"),
    ("gs_aridity", "生长季干燥度", "PET/P"),
    ("prec_cv", "降水变异系数", "—"),
    ("gs_prec_share", "生长季降水占比", "—"),
    ("winter_temp", "冬季均温", "°C"),
    ("seasonal_temp_range", "生长季-冬季温差", "°C"),
    ("spei_growing_season_mean", "生长季 SPEI", "—"),
    ("temp", "年均温", "°C"),
    ("prec", "年降水", "mm"),
    ("sun", "年辐射", "W/m²"),
]

# 统计字段规格：key 是输出列名，aliases 用来猜列
FIELD_SPECS: list[dict[str, Any]] = [
    {
        "key": "year",
        "label": "年份",
        "kind": "int",
        "required": True,
        "aliases": ["年份", "年度", "统计年度", "统计年份", "年", "year", "yr"],
    },
    {
        "key": "region_code",
        "label": "行政区划代码",
        "kind": "code",
        "required": False,
        "aliases": [
            "行政区划代码", "区划代码", "区县代码", "县代码", "地区代码",
            "adcode", "countycode", "regioncode", "code",
        ],
    },
    {
        "key": "region_name",
        "label": "地区名称",
        "kind": "text",
        "required": False,
        "aliases": [
            "区县名称", "区县", "县名", "县域", "地区名称", "行政区名称",
            "地区", "县", "countyname", "county", "district", "region",
            "areaname", "name",
        ],
    },
    {
        "key": "province",
        "label": "省份",
        "kind": "text",
        "required": False,
        "aliases": ["省份", "省名", "省", "province"],
    },
    {
        "key": "city",
        "label": "地市",
        "kind": "text",
        "required": False,
        "aliases": ["地级市", "地市", "市名", "城市", "city", "prefecture"],
    },
    {
        "key": "grain_output_t",
        "label": "粮食总产量",
        "kind": "float",
        "required": False,
        "aliases": [
            "粮食总产量", "粮食产量", "总产量", "产量", "grainoutput",
            "totaloutput", "output", "production",
        ],
    },
    {
        "key": "sown_kha",
        "label": "粮食播种面积",
        "kind": "float",
        "required": False,
        "aliases": [
            "粮食播种面积", "播种面积", "种植面积", "sownarea", "sown",
            "plantingarea", "area",
        ],
    },
    {
        "key": "yield_ton_per_ha",
        "label": "单产",
        "kind": "float",
        "required": False,
        "aliases": ["单位面积产量", "单产", "亩产", "yieldperha", "yield"],
    },
]

# 每个数值字段支持的单位及其折算到"标准单位"的系数
UNIT_FACTORS: dict[str, dict[str, float]] = {
    "grain_output_t": {"吨": 1.0, "万吨": 1e4, "千克": 1e-3, "公斤": 1e-3},
    "sown_kha": {"千公顷": 1.0, "公顷": 1e-3, "亩": 1 / 15000, "万亩": 2 / 3},
    "yield_ton_per_ha": {
        "吨/公顷": 1.0,
        "公斤/公顷": 1e-3,
        "公斤/亩": 0.015,
        "斤/亩": 0.0075,
    },
}

DEFAULT_UNITS = {
    "grain_output_t": "吨",
    "sown_kha": "千公顷",
    "yield_ton_per_ha": "吨/公顷",
}

# 面板气候覆盖窗口（county.db 实测 2012-2023）
CHINA_CLIMATE_YEARS = (2012, 2023)


class CleanError(Exception):
    """可直接展示给用户的清洗错误。"""


def read_table(path: Path, sheet: str | int | None = None) -> pd.DataFrame:
    """读 csv/xlsx。csv 依次尝试 utf-8-sig / utf-8 / gbk 三种编码。"""
    suffix = path.suffix.lower()
    if suffix in (".xlsx", ".xlsm"):
        return pd.read_excel(
            path, sheet_name=sheet if sheet is not None else 0, engine="openpyxl"
        )
    if suffix == ".xls":
        raise CleanError("旧版 .xls 请先另存为 .xlsx 再上传")
    if suffix in (".csv", ".txt", ".tsv"):
        last: Exception | None = None
        for enc in ("utf-8-sig", "utf-8", "gbk", "gb18030"):
            try:
                return pd.read_csv(path, encoding=enc, sep=None, engine="python")
            except UnicodeDecodeError as exc:
                last = exc
        raise CleanError(f"CSV 编码无法识别（已试 UTF-8/GBK）：{last}")
    raise CleanError(f"不支持的文件类型：{suffix}")


def _norm_header(value: Any) -> str:
    text = str(value).strip().replace("\ufeff", "")
    text = re.sub(r"[\s\-_/\\（）()\[\]【】:：,，.。、]+", "", text)
    return text.lower()


def guess_mapping(columns: list[str]) -> dict[str, dict[str, Any]]:
    """按别名给每个标准字段挑一列，全局贪心分配，同一列不会被用两次。"""
    pairs: list[tuple[float, str, str, str]] = []
    for spec in FIELD_SPECS:
        aliases = [_norm_header(a) for a in spec["aliases"]]
        for col in columns:
            norm = _norm_header(col)
            if not norm:
                continue
            best_alias, best_score = "", 0.0
            for alias in aliases:
                if not alias:
                    continue
                if norm == alias:
                    score = 1.0
                elif alias in norm:
                    score = 0.72
                elif norm in alias and len(norm) >= 2:
                    score = 0.5
                else:
                    score = 0.0
                # 同样命中时更长的别名更具体（"粮食总产量" 优先于 "产量"）
                score *= 1 + len(alias) / 60
                if score > best_score:
                    best_alias, best_score = alias, score
            if best_score > 0:
                pairs.append((best_score, spec["key"], col, best_alias))

    pairs.sort(key=lambda p: (-p[0], p[1]))
    used: set[str] = set()
    result: dict[str, dict[str, Any]] = {}
    for score, field, col, alias in pairs:
        if field in result or col in used:
            continue
        result[field] = {
            "column": col,
            "confidence": round(min(score, 1.0), 2),
            "matched_alias": alias,
        }
        used.add(col)

    for spec in FIELD_SPECS:
        result.setdefault(
            spec["key"], {"column": None, "confidence": 0.0, "matched_alias": ""}
        )
    return result


def mapping_complete(mapping: dict[str, Any]) -> tuple[bool, list[str]]:
    """检查必需字段：年份 + 至少一个地区标识。"""
    missing: list[str] = []
    if not mapping.get("year", {}).get("column"):
        missing.append("年份")
    if not (
        mapping.get("region_code", {}).get("column")
        or mapping.get("region_name", {}).get("column")
    ):
        missing.append("地区名称或行政区划代码")
    return (not missing), missing


_NUMERIC_JUNK = {"", "-", "—", "–", "…", "nan", "none", "null", "na", "n/a"}


def _to_number(series: pd.Series) -> pd.Series:
    text = (
        series.astype(str)
        .str.strip()
        .str.replace(",", "", regex=False)
        .str.replace("，", "", regex=False)
        .str.replace(" ", "", regex=False)
    )
    text = text.where(~text.str.lower().isin(_NUMERIC_JUNK))
    text = text.str.replace(r"[^\d.\-eE+]", "", regex=True)
    return pd.to_numeric(text, errors="coerce")


def parse_number(series: pd.Series) -> pd.Series:
    """公开入口：把可能带千分位/中文单位的列转成数值。"""
    return _to_number(series)


def infer_units(df: pd.DataFrame, mapping: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """用中位数猜单位。只给建议，最终以用户选择为准。"""
    out: dict[str, dict[str, Any]] = {}
    for field in ("grain_output_t", "sown_kha", "yield_ton_per_ha"):
        col = mapping.get(field, {}).get("column")
        if not col or col not in df.columns:
            continue
        values = _to_number(df[col]).dropna()
        if values.empty:
            continue
        median = float(values.median())
        suggestion, reason = DEFAULT_UNITS[field], "无法判断量级，按标准单位处理"
        if field == "grain_output_t":
            if 0 < median < 100:
                suggestion, reason = "万吨", f"中位数 {median:.2f}，更像万吨"
            elif median >= 1e8:
                suggestion, reason = "千克", f"中位数 {median:.3g}，更像千克"
            else:
                suggestion, reason = "吨", f"中位数 {median:,.0f}，按吨解释合理"
        elif field == "sown_kha":
            if 0 < median < 1:
                suggestion, reason = "万亩", f"中位数 {median:.2f}，更像万亩"
            elif median < 1000:
                suggestion, reason = "千公顷", f"中位数 {median:.1f}，更像千公顷"
            else:
                suggestion, reason = "公顷", f"中位数 {median:.1f}，更像公顷"
        else:
            if 0 < median < 20:
                suggestion, reason = "吨/公顷", f"中位数 {median:.2f}，更像吨/公顷"
            elif median < 2000:
                suggestion, reason = "公斤/亩", f"中位数 {median:.1f}，更像公斤/亩"
            else:
                suggestion, reason = "公斤/公顷", f"中位数 {median:.1f}，更像公斤/公顷"
        out[field] = {"suggested": suggestion, "reason": reason, "median": median}
    return out


def apply_mapping(
    df: pd.DataFrame, mapping: dict[str, Any], units: dict[str, str]
) -> pd.DataFrame:
    """把用户表压成标准列，并做单位换算。"""
    out = pd.DataFrame(index=df.index)
    for spec in FIELD_SPECS:
        key = spec["key"]
        col = (mapping.get(key) or {}).get("column")
        if not col or col not in df.columns:
            out[key] = pd.NA
            continue
        if spec["kind"] == "int":
            out[key] = _to_number(df[col]).astype("Int64")
        elif spec["kind"] == "float":
            values = _to_number(df[col])
            unit = units.get(key, DEFAULT_UNITS.get(key, ""))
            factor = UNIT_FACTORS.get(key, {}).get(unit)
            if factor is None:
                raise CleanError(f"{spec['label']} 的单位 {unit!r} 不受支持")
            out[key] = values * factor
        elif spec["kind"] == "code":
            out[key] = (
                df[col]
                .astype(str)
                .str.strip()
                .str.replace(r"\.0$", "", regex=True)
                .replace({"nan": pd.NA, "None": pd.NA, "": pd.NA})
            )
        else:
            out[key] = (
                df[col]
                .astype(str)
                .str.strip()
                .replace({"nan": pd.NA, "None": pd.NA, "": pd.NA})
            )
    return out


def _finding(
    level: str,
    rule: str,
    title: str,
    detail: str,
    count: int = 0,
    samples: list[str] | None = None,
    suggestion: str = "",
) -> dict[str, Any]:
    return {
        "level": level,
        "rule": rule,
        "title": title,
        "detail": detail,
        "count": int(count),
        "samples": samples or [],
        "suggestion": suggestion,
    }


def _sample(values: Any, n: int = 3) -> list[str]:
    if isinstance(values, pd.Series):
        return [str(v) for v in values.dropna().unique()[:n]]
    return [str(v) for v in list(values)[:n]]


def check_basic(df: pd.DataFrame) -> list[dict[str, Any]]:
    """与地区无关的检查：年份、重复、数值矛盾、量级。"""
    findings: list[dict[str, Any]] = []

    year = df["year"]
    invalid = year.isna() | (year < 1950) | (year > 2030)
    if invalid.any():
        findings.append(
            _finding(
                "blocker", "year_invalid", "年份缺失或越界",
                f"{int(invalid.sum())} 行的年份为空或不在 1950–2030 之间。",
                int(invalid.sum()), _sample(df["region_name"][invalid]),
                "补齐年份列；年份必须是四位整数。",
            )
        )

    has_region = df["region_code"].notna() | df["region_name"].notna()
    if has_region.any():
        tuples = list(
            zip(
                df["region_code"].fillna(""),
                df["province"].fillna(""),
                df["city"].fillna(""),
                df["region_name"].fillna(""),
                year.fillna(-1),
            )
        )
        dup = pd.Series(tuples, index=df.index).duplicated()
        if dup.any():
            findings.append(
                _finding(
                    "blocker", "duplicate_region_year", "同一地区同一年重复",
                    f"{int(dup.sum())} 行是同一地区同一年的重复记录，直接合并会让统计量翻倍。",
                    int(dup.sum()), _sample(df["region_name"][dup]),
                    "检查是否混入了合计行，或总产/单产各在一张表里。",
                )
            )

    need = ["grain_output_t", "sown_kha", "yield_ton_per_ha"]
    if all(df[c].notna().sum() >= 3 for c in need):
        implied = df["grain_output_t"] / (df["sown_kha"] * 1000)
        denom = implied.abs().where(implied.abs() > 1e-9)
        rel = (df["yield_ton_per_ha"] - implied).abs() / denom
        bad = (rel > 0.05).fillna(False)
        if bad.any():
            findings.append(
                _finding(
                    "warning", "output_yield_conflict", "总产、面积、单产三者对不上",
                    f"{int(bad.sum())} 行里「总产 ÷ 面积」与单产相差超过 5%，"
                    "通常意味着单位或统计口径不同源。",
                    int(bad.sum()), _sample(df["region_name"][bad]),
                    "三者至少有一列的统计口径（总产/单产、公顷/千公顷）或来源年份不一致。",
                )
            )

    if df["sown_kha"].notna().any():
        miss = float(df["sown_kha"].isna().mean())
        if miss > 0.3:
            findings.append(
                _finding(
                    "warning", "sown_missing", "播种面积缺失率偏高",
                    f"播种面积缺失 {miss:.0%}。本项目所有结论都建立在"
                    "「先剥离规模」之上，缺面积就无法复现。",
                    int(df["sown_kha"].isna().sum()), [],
                    "尽量补齐播种面积；否则只能做单产口径分析，不能做总产归因。",
                )
            )

    if df["grain_output_t"].notna().sum() >= 3:
        # 必须按地区分组：全表按年份排序会把不同县的相邻行串在一起，造成假阳性
        work = df.dropna(subset=["grain_output_t", "year"]).copy()
        work["_region_key"] = (
            work["region_code"].fillna(work["region_name"]).fillna("").astype(str)
        )
        work = work.sort_values(["_region_key", "year"])
        prev = work.groupby("_region_key")["grain_output_t"].shift(1)
        ratio = work["grain_output_t"] / prev.replace(0, pd.NA)
        bad = ((ratio > 5) | (ratio < 0.2)).fillna(False)
        if bad.any():
            findings.append(
                _finding(
                    "warning", "year_jump", "产量年际跳变异常",
                    f"{int(bad.sum())} 处同一地区相邻年份产量相差 5 倍以上，"
                    "常见于合计行混入或单位中途变化。",
                    int(bad.sum()), _sample(work.loc[bad, "region_name"]),
                    "逐条核对这几行，确认不是「全县合计」与「某乡镇」混在同一列。",
                )
            )

    if df["region_name"].notna().any():
        districts = df["region_name"].astype(str).str.contains("市辖区|辖区")
        if districts.any():
            findings.append(
                _finding(
                    "info", "city_district_rows", "含「市辖区」合计行",
                    f"{int(districts.sum())} 行的地区名是市辖区合计，不是独立农业单元，"
                    "与县级行混用会重复计算。",
                    int(districts.sum()), _sample(df["region_name"][districts]),
                    "保留但标记；做县域比较时应剔除。",
                )
            )

    return findings


def check_units(
    units: dict[str, str], inferred: dict[str, dict[str, Any]]
) -> list[dict[str, Any]]:
    findings: list[dict[str, Any]] = []
    labels = {
        "grain_output_t": "粮食总产量",
        "sown_kha": "播种面积",
        "yield_ton_per_ha": "单产",
    }
    for field, info in inferred.items():
        chosen = units.get(field, DEFAULT_UNITS[field])
        if chosen != info["suggested"]:
            findings.append(
                _finding(
                    "warning", f"unit_suspect_{field}", f"{labels[field]}单位可能选错",
                    f"你选的是「{chosen}」，但{info['reason']}"
                    f"（按「{info['suggested']}」解释更合理）。单位错一档，结果差 1000 倍。",
                    0, [],
                    f"如果原始表就是这个单位，可以忽略；否则请在映射页改成"
                    f"「{info['suggested']}」再跑一次。",
                )
            )
    return findings


_PROVINCE_ALIAS = {
    "内蒙古自治区": "内蒙古",
    "广西壮族自治区": "广西",
    "西藏自治区": "西藏",
    "宁夏回族自治区": "宁夏",
    "新疆维吾尔自治区": "新疆",
    "香港特别行政区": "香港",
    "澳门特别行政区": "澳门",
}

_NAME_SUFFIX = ("自治县", "自治旗", "市辖区", "县", "区", "市", "旗")


def _norm_province(value: Any) -> str:
    text = str(value).strip().replace(" ", "")
    text = _PROVINCE_ALIAS.get(text, text)
    return re.sub(r"(省|市)$", "", text)


def _norm_region(value: Any) -> str:
    text = str(value).strip().replace(" ", "")
    for suffix in _NAME_SUFFIX:
        if text.endswith(suffix) and len(text) > len(suffix):
            return text[: -len(suffix)]
    return text


@lru_cache(maxsize=1)
def _county_meta() -> pd.DataFrame:
    if not COUNTY_DB.exists():
        raise CleanError("县级面板 county.db 不存在，无法做中国模式匹配")
    with sqlite3.connect(COUNTY_DB) as conn:
        meta = pd.read_sql_query(
            "SELECT county_code, province, city, county, lon, lat, map_key, on_map "
            "FROM county_meta",
            conn,
        )
    meta["county_code"] = meta["county_code"].astype("int64")
    # 注意：itertuples() 会把下划线开头的列名改成位置名，这里不能用 _prov
    meta["prov_norm"] = meta["province"].map(_norm_province)
    meta["county_norm"] = meta["county"].map(_norm_region)
    return meta


def match_china(df: pd.DataFrame) -> tuple[pd.DataFrame, dict[str, Any]]:
    """把上传表每一行对到 county_meta。代码优先，其次省+县，最后县名唯一匹配。"""
    meta = _county_meta()
    by_code = {int(r.county_code): r for r in meta.itertuples()}
    by_prov_county: dict[tuple[str, str], list[Any]] = {}
    by_county: dict[str, list[Any]] = {}
    for row in meta.itertuples():
        by_prov_county.setdefault((row.prov_norm, row.county_norm), []).append(row)
        by_county.setdefault(row.county_norm, []).append(row)

    codes: list[Any] = []
    names: list[Any] = []
    provinces: list[Any] = []
    cities: list[Any] = []
    methods: list[str] = []
    notes: list[str] = []

    for row in df.itertuples():
        code_raw = getattr(row, "region_code", None)
        name_raw = getattr(row, "region_name", None)
        prov_raw = getattr(row, "province", None)

        hit = None
        how = ""
        note = ""
        if isinstance(code_raw, str) and code_raw.isdigit() and int(code_raw) in by_code:
            hit, how = by_code[int(code_raw)], "code"
        if hit is None and isinstance(name_raw, str):
            candidates = by_prov_county.get(
                (_norm_province(prov_raw), _norm_region(name_raw)), []
            )
            if len(candidates) == 1:
                hit, how = candidates[0], "province+name"
            elif len(candidates) > 1:
                note = f"{name_raw} 在 {prov_raw} 下有 {len(candidates)} 个同名单元"
            else:
                candidates = by_county.get(_norm_region(name_raw), [])
                if len(candidates) == 1:
                    hit, how = candidates[0], "name"
                elif len(candidates) > 1:
                    note = (
                        f"{name_raw} 跨 {len(candidates)} 个省重名（"
                        + "、".join(str(c.province) for c in candidates[:3])
                        + "）"
                    )

        codes.append(int(hit.county_code) if hit is not None else pd.NA)
        names.append(hit.county if hit is not None else pd.NA)
        provinces.append(hit.province if hit is not None else pd.NA)
        cities.append(hit.city if hit is not None else pd.NA)
        methods.append(how if hit is not None else "unmatched")
        notes.append(note)

    out = df.copy()
    out["matched_code"] = pd.array(codes, dtype="Int64")
    out["matched_county"] = names
    out["matched_province"] = provinces
    out["matched_city"] = cities
    out["match_method"] = methods
    out["match_note"] = notes

    total = len(out)
    hit_n = int(out["matched_code"].notna().sum())
    stats = {
        "total": total,
        "matched": hit_n,
        "match_rate": round(hit_n / total, 3) if total else 0.0,
        "by_method": {str(k): int(v) for k, v in out["match_method"].value_counts().items()},
    }
    return out, stats


def attach_climate_china(df: pd.DataFrame) -> tuple[pd.DataFrame, dict[str, Any]]:
    """按 (县代码, 年) 从 county.db 取气候特征。"""
    out = df.copy()
    climate_cols = [c for c, _, _ in CLIMATE_FIELDS]

    valid = out.dropna(subset=["matched_code", "year"])
    if valid.empty:
        for col in climate_cols:
            out[col] = pd.NA
        return out, {"covered": 0, "rows": len(out), "rate": 0.0, "years": []}

    codes = sorted({int(c) for c in valid["matched_code"]})
    years = sorted({int(y) for y in valid["year"]})
    placeholders_c = ",".join("?" * len(codes))
    placeholders_y = ",".join("?" * len(years))
    cols = ", ".join(["county_code", "year"] + climate_cols)
    query = (
        f"SELECT {cols} FROM county_panel "
        f"WHERE county_code IN ({placeholders_c}) AND year IN ({placeholders_y})"
    )
    with sqlite3.connect(COUNTY_DB) as conn:
        climate = pd.read_sql_query(query, conn, params=codes + years)

    merged = out.merge(
        climate,
        left_on=["matched_code", "year"],
        right_on=["county_code", "year"],
        how="left",
    ).drop(columns=["county_code"], errors="ignore")
    for col in climate_cols:
        if col not in merged.columns:
            merged[col] = pd.NA
    merged["climate_available"] = merged[climate_cols[0]].notna()
    covered = int(merged["climate_available"].sum())
    return merged, {
        "covered": covered,
        "rows": len(merged),
        "rate": round(covered / len(merged), 3) if len(merged) else 0.0,
        "years": years,
    }


def check_regions(df: pd.DataFrame, stats: dict[str, Any]) -> list[dict[str, Any]]:
    findings: list[dict[str, Any]] = []
    rate = stats["match_rate"]
    if rate < 0.5:
        findings.append(
            _finding(
                "blocker", "region_match_low", "地区匹配率过低",
                f"只有 {rate:.0%} 的行能对上内置县级边界"
                f"（{stats['matched']}/{stats['total']}）。匹配不上就没有气候数据。",
                stats["total"] - stats["matched"], [],
                "检查地区名后缀差异；跨国数据请改用「国外模式」并上传地理文件。",
            )
        )
    elif rate < 0.95:
        findings.append(
            _finding(
                "warning", "region_match_partial", "部分地区未匹配",
                f"{stats['total'] - stats['matched']} 行没对上（匹配率 {rate:.0%}），"
                "这些行的气候列会是空的。",
                stats["total"] - stats["matched"], [],
                "补充「省份」列可显著提高匹配率；跨省重名必须给省份或区划代码。",
            )
        )

    # 用 match_method 判定，而不是 matched_code：国外模式的单元没有区划代码，
    # 只靠 matched_code 判会把"全部匹配成功"误报成"未匹配"。
    unmatched = df[df["match_method"] == "unmatched"]
    if len(unmatched):
        names = _sample(unmatched["region_name"].dropna(), 6)
        if names:
            findings.append(
                _finding(
                    "info", "region_unmatched_sample", "未匹配地区示例",
                    "、".join(names), len(unmatched), names,
                    "优先核对这几行；其余在导出文件里标 match_method=unmatched。",
                )
            )

    ambiguous = df[df["match_note"].astype(str).str.len() > 0]
    if len(ambiguous):
        findings.append(
            _finding(
                "warning", "region_ambiguous", "重名地区",
                f"{len(ambiguous)} 行存在同名单元，必须靠省份或区划代码消歧。",
                len(ambiguous), _sample(ambiguous["match_note"], 3),
                "加一列「省份」或「行政区划代码」，不要只给县名。",
            )
        )
    return findings


def check_climate(
    df: pd.DataFrame,
    stats: dict[str, Any],
    window: tuple[int, int] = CHINA_CLIMATE_YEARS,
    region: str = "china",
) -> list[dict[str, Any]]:
    findings: list[dict[str, Any]] = []
    covered, rows = stats.get("covered", 0), stats.get("rows", 0)
    if rows and covered < rows:
        findings.append(
            _finding(
                "warning", "climate_missing", "气候回填不完整",
                f"有 {rows - covered} 行拿不到气候数据"
                f"（覆盖率 {covered / rows:.0%}）。",
                rows - covered, [],
                f"内置气候覆盖 {window[0]}–{window[1]} 年；"
                "超出范围的年份需要自带气候数据。",
            )
        )
    years = [int(y) for y in df["year"].dropna().unique()]
    outside = sorted(y for y in years if y < window[0] or y > window[1])
    if outside:
        findings.append(
            _finding(
                "info", "year_out_of_climate", "年份超出内置气候窗口",
                f"{outside} 不在 {window[0]}–{window[1]}，"
                "这些年份只有统计列、没有气候列。",
                len(outside), [str(y) for y in outside],
                "需要更早年份时请上传对应气候表；系统不做插值外推。",
            )
        )
    if region == "china" and 2023 in years:
        findings.append(
            _finding(
                "info", "no_truth_2023", "2023 年无产量真值",
                "县域统计年鉴 2024 卷尚未出版，2023 年的产量与气候只能作外推参考，"
                "不能当已验证结果。",
                0, [], "在论文或报告里明确标注该年为外推。",
            )
        )
    return findings


def build_report(
    findings: list[dict[str, Any]],
    summary: dict[str, Any],
    mapping: dict[str, Any],
    units: dict[str, str],
) -> str:
    level_name = {"blocker": "阻断", "warning": "警告", "info": "提示"}
    lines = [
        "# 数据整备报告",
        "",
        f"- 生成时间：{summary.get('generated_at', '')}",
        f"- 原始文件：{summary.get('source_file', '')}",
        f"- 原始行数：{summary.get('input_rows', 0)}",
        f"- 输出行数：{summary.get('output_rows', 0)}",
        f"- 地区匹配：{summary.get('matched', 0)}/{summary.get('input_rows', 0)}"
        f"（{summary.get('match_rate', 0):.0%}）",
        f"- 气候覆盖：{summary.get('climate_covered', 0)}/{summary.get('input_rows', 0)}"
        f"（{summary.get('climate_rate', 0):.0%}）",
        "",
        "## 字段映射",
        "",
        "| 标准字段 | 上传列 | 置信度 |",
        "|---|---|---|",
    ]
    for spec in FIELD_SPECS:
        item = mapping.get(spec["key"], {})
        lines.append(
            f"| {spec['label']} | {item.get('column') or '—'} | "
            f"{float(item.get('confidence', 0)):.2f} |"
        )
    lines += ["", "## 单位口径", "", "| 字段 | 采用单位 |", "|---|---|"]
    for field, unit in units.items():
        lines.append(f"| {field} | {unit} |")

    lines += ["", "## 检查结果", ""]
    if not findings:
        lines.append("未发现问题。")
    for level in ("blocker", "warning", "info"):
        group = [f for f in findings if f["level"] == level]
        if not group:
            continue
        lines += [f"### {level_name[level]}（{len(group)}）", ""]
        for item in group:
            lines.append(f"**{item['title']}**")
            lines.append("")
            lines.append(item["detail"])
            if item["samples"]:
                lines += ["", "示例：" + "、".join(item["samples"])]
            if item["suggestion"]:
                lines += ["", "建议：" + item["suggestion"]]
            lines.append("")

    lines += [
        "## 不能越过的边界",
        "",
        "1. 本报告只证明「表已对齐、可用」，不证明任何风险结论。",
        "2. 内置模型只在中国 10 个主产省的县级面板上训练，别国数据不做风险打分。",
        "3. 2023 年无产量真值，该年任何结果都是外推。",
        "4. 气候特征取自县治最近格点，不代表全县面平均。",
        "",
    ]
    return "\n".join(lines)


def build_repro_script(mapping: dict[str, Any], units: dict[str, str], sha: str) -> str:
    payload = json.dumps(mapping, ensure_ascii=False)
    unit_payload = json.dumps(units, ensure_ascii=False)
    return (
        "\"\"\"自动生成的复现脚本 —— 与 M08 本次清洗完全同参数。\n\n"
        "用法：python run_pipeline.py <原始文件路径>\n"
        "\"\"\"\n"
        "import json\n"
        "import sys\n"
        "from pathlib import Path\n\n"
        "sys.path.insert(0, str(Path(__file__).resolve().parents[2]))\n"
        "from services import panel_cleaner\n\n"
        f"MAPPING = json.loads({payload!r})\n"
        f"UNITS = json.loads({unit_payload!r})\n"
        f"SOURCE_SHA256 = {sha!r}\n\n"
        "SOURCE = sys.argv[1]\n"
        "df = panel_cleaner.read_table(Path(SOURCE))\n"
        "clean = panel_cleaner.apply_mapping(df, MAPPING, UNITS)\n"
        "print(clean.head())\n"
        "print('rows =', len(clean))\n"
    )


def sha256_of(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def export_columns(df: pd.DataFrame) -> list[str]:
    base = [
        "region_name", "matched_code", "matched_province", "matched_city",
        "year", "grain_output_t", "sown_kha", "yield_ton_per_ha",
    ]
    climate = [c for c, _, _ in CLIMATE_FIELDS]
    tail = ["match_method", "match_note", "climate_available"]
    cols = [c for c in base + climate + tail if c in df.columns]
    standard = {s["key"] for s in FIELD_SPECS}
    extra = [c for c in df.columns if c not in cols and not c.startswith("_") and c not in standard]
    return cols + extra
