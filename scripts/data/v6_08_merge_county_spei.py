#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""v6 Step 8：县级 SPEI 合并进特征矩阵（县级优先，省级回填）。

用 v6_07 的县级 SPEI 覆盖 paper_panel_v6_climate.parquet 里的省级 SPEI；
县级缺失的县（无经纬度/无格点）回填省级值。

输出: data/interim/paper_panel_v6_climate_full.parquet（不覆盖原文件）
"""
import sys
from pathlib import Path

import pandas as pd

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.stderr.reconfigure(encoding="utf-8", errors="replace")

PROJECT_ROOT = Path(__file__).resolve().parents[2]
CLIMATE = PROJECT_ROOT / "data" / "interim" / "paper_panel_v6_climate.parquet"
COUNTY_SPEI = PROJECT_ROOT / "data" / "interim" / "spei_county_annual_v6.csv"
PROV_SPEI = PROJECT_ROOT / "data" / "interim" / "spei_province_annual.csv"
OUT = PROJECT_ROOT / "data" / "interim" / "paper_panel_v6_climate_full.parquet"

SPEI_COLS = ["spei_annual_mean", "spei_growing_season_mean"]


def main() -> int:
    m = pd.read_parquet(CLIMATE)
    c = pd.read_csv(COUNTY_SPEI)
    p = pd.read_csv(PROV_SPEI)
    n_before = m[SPEI_COLS[0]].notna().sum()

    # 县级 SPEI（覆盖）
    m = m.drop(columns=SPEI_COLS).merge(
        c[["区县代码", "year", *SPEI_COLS]],
        left_on=["区县代码", "年份"], right_on=["区县代码", "year"], how="left",
    ).drop(columns=["year"])
    n_county = m[SPEI_COLS[0]].notna().sum()

    # 省级回填（县级缺失的县，如无经纬度 3 县）
    m = m.merge(
        p[["province", "year", *SPEI_COLS]],
        left_on=["省份", "年份"], right_on=["province", "year"], how="left",
        suffixes=("", "_prov"),
    ).drop(columns=["province", "year"])
    for col in SPEI_COLS:
        m[col] = m[col].fillna(m[f"{col}_prov"])
    m = m.drop(columns=[f"{c}_prov" for c in SPEI_COLS])
    n_final = m[SPEI_COLS[0]].notna().sum()

    print(f"样本 {len(m)} 行 | SPEI 覆盖: 省级 {n_before} → 县级 {n_county} → 最终 {n_final}")
    print(f"县级 SPEI 覆盖率: {n_county / len(m):.1%}")
    m.to_parquet(OUT, index=False)
    print(f"✅ 写入 {OUT.name} ({m.shape})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
