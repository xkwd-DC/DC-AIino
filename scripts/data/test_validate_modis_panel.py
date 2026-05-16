"""validate_modis_panel 的合成数据单元测试。

策略：构造一份"完美面板"，再针对每条规则注入一种坏情况，验证报告里出现对应 error。

跑法：
    cd /home/darcy/DC/DC && pytest scripts/data/test_validate_modis_panel.py -v
"""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

# 把项目根挂进 sys.path，使 `scripts.data.validate_modis_panel` 可导入
PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts.data.validate_modis_panel import (  # noqa: E402
    CANONICAL_PROVINCES,
    EXPECTED_ROWS,
    SHORT_TO_FULL,
    validate,
)

YEAR_RANGE = range(2011, 2024)
MONTH_RANGE = range(1, 13)


def _perfect_panel() -> pd.DataFrame:
    """31 省 × 13 年 × 12 月 = 4836 行的合规面板。"""
    rows = []
    for code, full, _short in CANONICAL_PROVINCES:
        for year in YEAR_RANGE:
            for month in MONTH_RANGE:
                rows.append(
                    {
                        "province_code": code,
                        "province": full,
                        "year": int(year),
                        "month": int(month),
                        "ndvi_mean": 0.45,
                        "ndvi_std": 0.10,
                        "lst_day_mean_k": 295.0,
                        "lst_night_mean_k": 280.0,
                        "valid_pixel_ratio": 0.92,
                    }
                )
    return pd.DataFrame(rows)


# ─── 基线：完美面板必须 PASS ────────────────────────────────────────────
def test_perfect_panel_passes():
    df = _perfect_panel()

    report = validate(df)

    assert report.passed, f"perfect panel should pass, errors: {report.errors}"
    assert report.row_count == EXPECTED_ROWS
    assert report.province_count == 31
    assert report.month_coverage == 156


# ─── schema ─────────────────────────────────────────────────────────────
def test_missing_required_column_is_error():
    df = _perfect_panel().drop(columns=["ndvi_mean"])

    report = validate(df)

    assert not report.passed
    assert any(i.rule == "schema.columns" for i in report.errors)


def test_wrong_dtype_is_error():
    df = _perfect_panel()
    df["year"] = df["year"].astype(str)

    report = validate(df)

    assert not report.passed
    assert any(i.rule == "schema.dtype" for i in report.errors)


# ─── 省名规约 ───────────────────────────────────────────────────────────
def test_short_province_name_is_error():
    df = _perfect_panel()
    df.loc[df["province"] == "河南省", "province"] = "河南"

    report = validate(df)

    assert not report.passed
    naming_errors = [i for i in report.errors if i.rule == "province.naming"]
    assert naming_errors
    assert "河南" in naming_errors[0].detail
    assert "河南" in report.short_names_found


def test_unknown_province_is_error():
    df = _perfect_panel()
    df.loc[df["province"] == "河南省", "province"] = "中州省"

    report = validate(df)

    assert not report.passed
    rules = {i.rule for i in report.errors}
    assert "province.naming" in rules or "province.coverage" in rules


def test_unknown_province_code_is_error():
    df = _perfect_panel()
    df.loc[df["province"] == "河南省", "province_code"] = "999999"

    report = validate(df)

    assert not report.passed
    assert any(i.rule == "province.code" for i in report.errors)


# ─── 时间覆盖 ───────────────────────────────────────────────────────────
def test_missing_month_is_error():
    df = _perfect_panel()
    df = df.drop(df[(df["year"] == 2022) & (df["month"] == 7)].index)

    report = validate(df)

    assert not report.passed
    assert any(i.rule == "time.coverage" for i in report.errors)


def test_year_out_of_range_is_error():
    df = _perfect_panel()
    df.loc[df.index[0], "year"] = 1999

    report = validate(df)

    assert not report.passed
    assert any(i.rule == "time.year" for i in report.errors)


def test_duplicate_key_is_error():
    df = _perfect_panel()
    df = pd.concat([df, df.iloc[[0]]], ignore_index=True)

    report = validate(df)

    assert not report.passed
    assert any(i.rule == "time.duplicate" for i in report.errors)


# ─── 取值范围 ───────────────────────────────────────────────────────────
def test_ndvi_out_of_bounds_is_error():
    df = _perfect_panel()
    df.loc[df.index[:3], "ndvi_mean"] = 1.5

    report = validate(df)

    assert not report.passed
    err = next(i for i in report.errors if i.rule == "value.ndvi")
    assert "3 行" in err.detail


def test_lst_day_out_of_bounds_is_error():
    df = _perfect_panel()
    df.loc[df.index[0], "lst_day_mean_k"] = 200.0  # 太低（K）

    report = validate(df)

    assert not report.passed
    assert any(i.rule == "value.lst_day" for i in report.errors)


def test_valid_pixel_ratio_low_is_warning_not_error():
    df = _perfect_panel()
    df.loc[df.index[:5], "valid_pixel_ratio"] = 0.3

    report = validate(df)

    assert report.passed, "低 valid_pixel_ratio 应只是 warning，不阻塞下游"
    assert any(i.rule == "value.pixel_ratio" for i in report.warnings)


# ─── 辅助常量 ───────────────────────────────────────────────────────────
def test_short_to_full_covers_31_provinces():
    assert len(SHORT_TO_FULL) == 31
    assert SHORT_TO_FULL["河南"] == "河南省"
    assert SHORT_TO_FULL["内蒙古"] == "内蒙古自治区"
    assert SHORT_TO_FULL["广西"] == "广西壮族自治区"
    assert SHORT_TO_FULL["新疆"] == "新疆维吾尔自治区"


