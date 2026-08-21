#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""v6 Step 3：合并 v6 特征矩阵 — 县级年鉴 + 县级 TerraClimate 气候 + v4 省级共享特征。

三层结构（与 v5 feature_matrix 同构，但键为 区县代码×年份）：
  1. 县级年鉴面板: y(log_yield) + 播种面积(规模控制/单产分母) + 第一产业增加值(投入控制)
  2. 县级 TerraClimate 气候: temp / prec / sun (v6_01b 抓取)
  3. 省级共享特征(v4, 按 省份×年份): spei / ndvi / lst / fert / irr / flood / drou_a / flood_a / cropland_ratio
     说明: 县级 SPEI/NDVI/LST 尚无数据源(SPEIbase nc 未下载、MODIS 未聚合)，首轮用省级共享，
           与 v5 处理一致；后续 v6 专项升级再替换为县级。

另产出稳健性目标 yield_ton_per_ha = 粮食总产量_吨 / (播种面积_千公顷×1000)，
与 v4 的 yield_kg_per_ha 单产口径可比（论文讨论用）。

输出: data/interim/paper_panel_v6_climate.parquet
"""
from pathlib import Path

import numpy as np
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[2]
YEARBOOK = PROJECT_ROOT / "data" / "interim" / "paper_panel_v6.parquet"
ERA5 = PROJECT_ROOT / "data" / "interim" / "terraclimate_county_yearly_v6.parquet"
V4 = PROJECT_ROOT / "data" / "interim" / "paper_panel_v4.parquet"
SPEI_CSV = PROJECT_ROOT / "data" / "interim" / "spei_province_annual.csv"
OUT = PROJECT_ROOT / "data" / "interim" / "paper_panel_v6_climate.parquet"

V4_SHARED = [
    "ndvi_yearly", "ndvi_summer_peak",
    "lst_day_growing_mean_k", "lst_night_growing_mean_k",
    "fert", "irr", "flood", "drou_a", "flood_a", "cropland_ratio",
]


def main() -> int:
    yb = pd.read_parquet(YEARBOOK)
    era5 = pd.read_parquet(ERA5)
    v4 = pd.read_parquet(V4)

    print(f"年鉴 {yb.shape}, ERA5 {era5.shape}, v4 {v4.shape}")

    # 1+2: 年鉴 × ERA5 (区县代码, 年份)
    m = yb.merge(
        era5[["区县代码", "year", "temp", "prec", "sun"]],
        left_on=["区县代码", "年份"], right_on=["区县代码", "year"], how="left",
    ).drop(columns=["year"])
    no_c = m["temp"].isna().mean()
    print(f"ERA5 气候覆盖: {(1 - no_c):.1%}  (缺失县 = {m.loc[m['temp'].isna(), '区县代码'].nunique()})")

    # 3: 省级共享特征 (省份, 年份) — SPEI 来自 00c 产出的双口径 csv，其余来自 v4
    spei = pd.read_csv(SPEI_CSV)
    m = m.merge(
        spei[["province", "year", "spei_annual_mean", "spei_growing_season_mean"]],
        left_on=["省份", "年份"], right_on=["province", "year"], how="left",
    ).drop(columns=["province", "year"])
    m = m.merge(
        v4[["province", "year"] + V4_SHARED],
        left_on=["省份", "年份"], right_on=["province", "year"], how="left",
    ).drop(columns=["province", "year"])
    for c in ["spei_annual_mean", "spei_growing_season_mean"] + V4_SHARED:
        print(f"  {c}: 覆盖 {(1 - m[c].isna().mean()):.1%}")

    # 稳健性目标: 单产 t/ha
    sown_ha = m["农作物总播种面积_千公顷"] * 1000.0
    m["yield_ton_per_ha"] = np.where(
        (m["粮食总产量_吨"] > 0) & (sown_ha > 0),
        m["粮食总产量_吨"] / sown_ha, np.nan,
    )
    print(f"单产目标覆盖: {m['yield_ton_per_ha'].notna().mean():.1%} "
          f"(n={m['yield_ton_per_ha'].notna().sum()}, 均值 {m['yield_ton_per_ha'].mean():.3f} t/ha)")

    m.to_parquet(OUT, index=False)
    print(f"✅ 写入 {OUT} ({m.shape})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
