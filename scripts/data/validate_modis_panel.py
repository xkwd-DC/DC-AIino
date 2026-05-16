"""校验石灵子产出的 MODIS 省域月度面板。

输入：`data/interim/modis_province_monthly.parquet`
契约：docs/08_数据采集任务_石灵子.md §3.2 / §3.3

通过 = 退出码 0；任何一类硬性失败 = 退出码 1（让 CI 拦下，避免脏数据进 processed/）。

CLI：
    python -m scripts.data.validate_modis_panel
    python -m scripts.data.validate_modis_panel --panel /path/to/x.parquet --report /path/to/report.md
"""
from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass, field
from pathlib import Path

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_PANEL_PATH = PROJECT_ROOT / "data" / "interim" / "modis_province_monthly.parquet"
DEFAULT_REPORT_PATH = PROJECT_ROOT / "data" / "interim" / "alignment_report.md"

REQUIRED_COLUMNS: dict[str, str] = {
    "province_code": "object",
    "province": "object",
    "year": "integer",
    "month": "integer",
    "ndvi_mean": "float",
    "ndvi_std": "float",
    "lst_day_mean_k": "float",
    "lst_night_mean_k": "float",
    "valid_pixel_ratio": "float",
}

YEAR_RANGE = (2011, 2023)
MONTH_RANGE = (1, 12)
EXPECTED_ROWS = 31 * 13 * 12  # 4836

NDVI_BOUNDS = (-0.2, 1.0)
# LST 白天/夜间下限放宽——西藏/新疆/黑龙江冬季 1km 像元 LST 可低至 -50°C（220K）
# 上限 320K (47°C) 已经覆盖南方夏季陆面温度极值
LST_DAY_BOUNDS_K = (220.0, 330.0)
LST_NIGHT_BOUNDS_K = (200.0, 320.0)
VALID_PIXEL_BOUNDS = (0.0, 1.0)

CANONICAL_PROVINCES: tuple[tuple[str, str, str], ...] = (
    ("110000", "北京市", "北京"),
    ("120000", "天津市", "天津"),
    ("130000", "河北省", "河北"),
    ("140000", "山西省", "山西"),
    ("150000", "内蒙古自治区", "内蒙古"),
    ("210000", "辽宁省", "辽宁"),
    ("220000", "吉林省", "吉林"),
    ("230000", "黑龙江省", "黑龙江"),
    ("310000", "上海市", "上海"),
    ("320000", "江苏省", "江苏"),
    ("330000", "浙江省", "浙江"),
    ("340000", "安徽省", "安徽"),
    ("350000", "福建省", "福建"),
    ("360000", "江西省", "江西"),
    ("370000", "山东省", "山东"),
    ("410000", "河南省", "河南"),
    ("420000", "湖北省", "湖北"),
    ("430000", "湖南省", "湖南"),
    ("440000", "广东省", "广东"),
    ("450000", "广西壮族自治区", "广西"),
    ("460000", "海南省", "海南"),
    ("500000", "重庆市", "重庆"),
    ("510000", "四川省", "四川"),
    ("520000", "贵州省", "贵州"),
    ("530000", "云南省", "云南"),
    ("540000", "西藏自治区", "西藏"),
    ("610000", "陕西省", "陕西"),
    ("620000", "甘肃省", "甘肃"),
    ("630000", "青海省", "青海"),
    ("640000", "宁夏回族自治区", "宁夏"),
    ("650000", "新疆维吾尔自治区", "新疆"),
)
FULL_NAMES = frozenset(p[1] for p in CANONICAL_PROVINCES)
SHORT_NAMES = frozenset(p[2] for p in CANONICAL_PROVINCES)
CANONICAL_CODES = frozenset(p[0] for p in CANONICAL_PROVINCES)
SHORT_TO_FULL: dict[str, str] = {p[2]: p[1] for p in CANONICAL_PROVINCES}


@dataclass(frozen=True)
class Issue:
    """一条校验问题。severity=error 进退出码 1，warning 只记报告。"""

    severity: str  # "error" | "warning"
    rule: str
    detail: str


@dataclass
class ValidationReport:
    issues: list[Issue] = field(default_factory=list)
    row_count: int = 0
    province_count: int = 0
    month_coverage: int = 0
    short_names_found: list[str] = field(default_factory=list)

    @property
    def errors(self) -> list[Issue]:
        return [i for i in self.issues if i.severity == "error"]

    @property
    def warnings(self) -> list[Issue]:
        return [i for i in self.issues if i.severity == "warning"]

    @property
    def passed(self) -> bool:
        return not self.errors

    def add(self, severity: str, rule: str, detail: str) -> None:
        self.issues.append(Issue(severity=severity, rule=rule, detail=detail))


def _check_columns(df: pd.DataFrame, report: ValidationReport) -> bool:
    """返回 True = schema OK，可继续后续检查；False = 后续会崩，提前结束。"""
    missing = [c for c in REQUIRED_COLUMNS if c not in df.columns]
    if missing:
        report.add("error", "schema.columns", f"缺列：{missing}")
        return False

    extra = [c for c in df.columns if c not in REQUIRED_COLUMNS]
    if extra:
        report.add("warning", "schema.columns", f"多余列（不影响下游，但请确认）：{extra}")

    dtype_errors = 0
    for col, kind in REQUIRED_COLUMNS.items():
        dtype = df[col].dtype
        if kind == "integer" and not pd.api.types.is_integer_dtype(dtype):
            report.add("error", "schema.dtype", f"`{col}` 应为整数，实际 {dtype}")
            dtype_errors += 1
        elif kind == "float" and not pd.api.types.is_float_dtype(dtype):
            report.add("error", "schema.dtype", f"`{col}` 应为浮点，实际 {dtype}")
            dtype_errors += 1
        elif kind == "object" and not (
            pd.api.types.is_object_dtype(dtype) or pd.api.types.is_string_dtype(dtype)
        ):
            report.add("error", "schema.dtype", f"`{col}` 应为字符串，实际 {dtype}")
            dtype_errors += 1

    # dtype 不对时，下游 .between / groupby 会抛 TypeError；不再继续，避免遮蔽根因。
    return dtype_errors == 0


def _check_provinces(df: pd.DataFrame, report: ValidationReport) -> None:
    found_names = set(df["province"].dropna().unique())
    found_codes = set(df["province_code"].dropna().unique())

    short_used = sorted(found_names & SHORT_NAMES - FULL_NAMES)
    if short_used:
        report.short_names_found = short_used
        report.add(
            "error",
            "province.naming",
            f"出现简称 {short_used}，docs/08 §3.3 要求中文全称（如 '河南省' 而非 '河南'）。"
            f"提示：可用 scripts.data.validate_modis_panel.SHORT_TO_FULL 映射。",
        )

    unknown_names = sorted(found_names - FULL_NAMES - SHORT_NAMES)
    if unknown_names:
        report.add("error", "province.naming", f"未知省名：{unknown_names}")

    missing_full = sorted(FULL_NAMES - found_names - {SHORT_TO_FULL[s] for s in short_used if s in SHORT_TO_FULL})
    if missing_full:
        report.add("error", "province.coverage", f"缺省（按全称统计）：{missing_full}")

    unknown_codes = sorted(found_codes - CANONICAL_CODES)
    if unknown_codes:
        report.add("error", "province.code", f"未知 province_code（应为民政部 6 位）：{unknown_codes}")

    report.province_count = len(found_names)


def _check_time_coverage(df: pd.DataFrame, report: ValidationReport) -> None:
    bad_years = df.loc[~df["year"].between(*YEAR_RANGE), "year"].unique().tolist()
    if bad_years:
        report.add("error", "time.year", f"year 越界（应 {YEAR_RANGE[0]}–{YEAR_RANGE[1]}）：{sorted(bad_years)}")

    bad_months = df.loc[~df["month"].between(*MONTH_RANGE), "month"].unique().tolist()
    if bad_months:
        report.add("error", "time.month", f"month 越界（应 1–12）：{sorted(bad_months)}")

    pairs = df.groupby(["year", "month"]).size()
    report.month_coverage = len(pairs)
    expected_pairs = (YEAR_RANGE[1] - YEAR_RANGE[0] + 1) * 12
    if report.month_coverage < expected_pairs:
        missing_pairs = sorted(
            {(y, m) for y in range(YEAR_RANGE[0], YEAR_RANGE[1] + 1) for m in range(1, 13)}
            - set(pairs.index.tolist())
        )
        report.add(
            "error",
            "time.coverage",
            f"缺少 {expected_pairs - report.month_coverage} 个 (year, month) 组合，例：{missing_pairs[:5]}",
        )

    dup = df.groupby(["province_code", "year", "month"]).size()
    dup_keys = dup[dup > 1]
    if not dup_keys.empty:
        report.add(
            "error",
            "time.duplicate",
            f"(province_code, year, month) 重复 {len(dup_keys)} 组，例：{dup_keys.index[:3].tolist()}",
        )


def _check_value_ranges(df: pd.DataFrame, report: ValidationReport) -> None:
    def out_of_range(col: str, lo: float, hi: float) -> int:
        valid = df[col].dropna()
        return int(((valid < lo) | (valid > hi)).sum())

    if (n := out_of_range("ndvi_mean", *NDVI_BOUNDS)):
        report.add("error", "value.ndvi", f"ndvi_mean 越界（应 {NDVI_BOUNDS}）：{n} 行")
    if (n := out_of_range("lst_day_mean_k", *LST_DAY_BOUNDS_K)):
        report.add("error", "value.lst_day", f"lst_day_mean_k 越界（应 {LST_DAY_BOUNDS_K} K）：{n} 行")
    if (n := out_of_range("lst_night_mean_k", *LST_NIGHT_BOUNDS_K)):
        report.add("warning", "value.lst_night", f"lst_night_mean_k 越界（应 {LST_NIGHT_BOUNDS_K} K）：{n} 行")
    if (n := out_of_range("valid_pixel_ratio", *VALID_PIXEL_BOUNDS)):
        report.add("error", "value.pixel_ratio", f"valid_pixel_ratio 越界（应 [0,1]）：{n} 行")

    if (n := int(df["ndvi_mean"].isna().sum())):
        report.add("warning", "value.ndvi", f"ndvi_mean 缺失 {n} 行")
    low_pix = df[df["valid_pixel_ratio"].fillna(1.0) < 0.5]
    if not low_pix.empty:
        report.add(
            "warning",
            "value.pixel_ratio",
            f"valid_pixel_ratio < 0.5 的行有 {len(low_pix)}（云污染过多，下游 NDVI 不可靠）",
        )


def validate(df: pd.DataFrame) -> ValidationReport:
    """对 MODIS 月度面板做硬性校验。返回 ValidationReport，不抛异常。"""
    report = ValidationReport(row_count=len(df))

    if not _check_columns(df, report):
        return report  # schema 都不对，后续 group_by 会崩，提前返回

    _check_provinces(df, report)
    _check_time_coverage(df, report)
    _check_value_ranges(df, report)

    if report.row_count != EXPECTED_ROWS and not any(
        i.rule.startswith("time.") or i.rule.startswith("province.") for i in report.errors
    ):
        report.add(
            "warning",
            "shape.rows",
            f"行数 {report.row_count} ≠ 期望 {EXPECTED_ROWS}（31 省 × 13 年 × 12 月）",
        )
    return report


def render_report(report: ValidationReport, panel_path: Path) -> str:
    status = "✅ PASS" if report.passed else "❌ FAIL"
    lines = [
        f"# MODIS 面板校验报告",
        "",
        f"**面板文件**：`{panel_path}`",
        f"**状态**：{status}",
        f"**行数**：{report.row_count} / 期望 {EXPECTED_ROWS}",
        f"**省份覆盖**：{report.province_count} / 31",
        f"**(year, month) 覆盖**：{report.month_coverage} / 156",
        "",
    ]
    if report.errors:
        lines.append("## ❌ 错误（CI 拦截）")
        for issue in report.errors:
            lines.append(f"- **{issue.rule}**：{issue.detail}")
        lines.append("")
    if report.warnings:
        lines.append("## ⚠️ 警告（仅记录）")
        for issue in report.warnings:
            lines.append(f"- **{issue.rule}**：{issue.detail}")
        lines.append("")
    if not report.issues:
        lines.append("无问题，可进入 `data/processed/` 与论文面板合并。")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="MODIS 省域月度面板 schema 校验")
    parser.add_argument("--panel", type=Path, default=DEFAULT_PANEL_PATH)
    parser.add_argument("--report", type=Path, default=DEFAULT_REPORT_PATH)
    parser.add_argument("--strict-warnings", action="store_true", help="把 warning 也算失败")
    args = parser.parse_args(argv)

    if not args.panel.exists():
        print(f"❌ 面板文件不存在：{args.panel}", file=sys.stderr)
        return 1

    df = pd.read_parquet(args.panel)
    report = validate(df)
    rendered = render_report(report, args.panel)

    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(rendered, encoding="utf-8")
    print(rendered)
    print(f"\n报告写入：{args.report}")

    if not report.passed:
        return 1
    if args.strict_warnings and report.warnings:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
