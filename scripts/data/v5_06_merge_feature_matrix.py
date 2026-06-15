#!/usr/bin/env python3
"""v5 Step 6：合并所有数据源 → feature_matrix_v5.parquet。

输入：
  - MODIS 地级市月度面板（modis_city_monthly_v5.parquet）
  - CLCD 地级市逐年 cropland_ratio（city_cropland_ratio_yearly_v5.parquet）
  - NASA POWER 地级市年度气象（nasa_power_city_yearly_v5.parquet）
  - v4 省级面板（paper_panel_v4.parquet）→ 提取省级固定特征

输出：
  - feature_matrix_v5.parquet（~1924 × 40+ 维）
  - 附 v4_vs_v5_crosswalk.csv
"""

import sys
from pathlib import Path

import numpy as np
import pandas as pd

PROJ = Path(__file__).resolve().parents[2]

# --- 输入路径 ---
MODIS_PATH = PROJ / "data" / "interim" / "modis_city_monthly_v5.parquet"
CLCD_PATH = PROJ / "data" / "interim" / "city_cropland_ratio_yearly_v5.parquet"
NASA_PATH = PROJ / "data" / "interim" / "nasa_power_city_yearly_v5.parquet"
V4_PATH = PROJ / "data" / "interim" / "paper_panel_v4.parquet"

OUT = PROJ / "data" / "interim" / "feature_matrix_v5.parquet"
OUT_CROSSWALK = PROJ / "data" / "interim" / "v5_crosswalk.csv"

# 10 粮食主产省（地级市 GeoJSON 中的短名）
TEN_PROVINCES = ["黑龙江", "河南", "山东", "吉林", "安徽",
                 "湖南", "河北", "四川", "江苏", "湖北"]

# v5 短名 → v4 省名（v4 面板中省名带"省"后缀）
V4_PROVINCE_MAP = {
    "黑龙江": "黑龙江省", "河南": "河南省", "山东": "山东省",
    "吉林": "吉林省", "安徽": "安徽省", "湖南": "湖南省",
    "河北": "河北省", "四川": "四川省", "江苏": "江苏省", "湖北": "湖北省",
}


def load_modis() -> pd.DataFrame:
    df = pd.read_parquet(MODIS_PATH)
    # MODIS 是月度面板：按 (city_id, year) 聚合为年度特征
    # NDVI: 年均值、夏季(6-8月)峰值
    # LST: 生长季均值（4-10月）
    annual = df.groupby(["province", "city", "city_id", "year"]).agg(
        ndvi_yearly=("ndvi_mean", "mean"),
        ndvi_summer_peak=("ndvi_mean", lambda x: x.loc[df.loc[x.index, "month"].isin([6, 7, 8])].mean()),
        lst_day_growing_mean_k=("lst_day_mean_k", lambda x: x.loc[df.loc[x.index, "month"].isin([4, 5, 6, 7, 8, 9, 10])].mean()),
        lst_night_growing_mean_k=("lst_night_mean_k", lambda x: x.loc[df.loc[x.index, "month"].isin([4, 5, 6, 7, 8, 9, 10])].mean()),
    ).reset_index()
    print(f"  MODIS: {len(annual)} rows, {annual.shape[1]} cols")
    return annual


def load_clcd() -> pd.DataFrame:
    df = pd.read_parquet(CLCD_PATH)
    df["city_id"] = df["province"] + "_" + df["city"]
    print(f"  CLCD: {len(df)} rows, {df.shape[1]} cols")
    return df[["province", "city", "city_id", "year", "cropland_ratio"]]


def load_nasa() -> pd.DataFrame:
    df = pd.read_parquet(NASA_PATH)
    print(f"  NASA: {len(df)} rows, {df.shape[1]} cols")
    return df


def load_v4_province_features() -> pd.DataFrame:
    """从 v4 提取省级固定特征（每个省每年一份），名称映射到 v5 短名。"""
    v4 = pd.read_parquet(V4_PATH)
    fixed_cols = [
        "province", "year",
        "irr", "flood", "mech", "fert",
        "drou_a", "flood_a", "spei",
        "prec", "temp", "sun",
        "prec_capital", "sun_capital",
        "sown_qian_ha", "production_wan_ton", "yield_kg_per_ha",
    ]
    v4_rev = {v: k for k, v in V4_PROVINCE_MAP.items()}
    v4_10 = v4[v4["province"].isin(V4_PROVINCE_MAP.values())].copy()
    v4_10["province"] = v4_10["province"].map(v4_rev)
    print(f"  v4 省级: {len(v4_10)} rows (10省×13年)")

    available = [c for c in fixed_cols if c in v4_10.columns]
    return v4_10[available].copy()

def main() -> int:
    print("=" * 60)
    print("v5 特征矩阵合并")
    print("=" * 60)

    # --- 1. 加载 v4 省级特征 ---
    print("\n[1] 加载 v4 省级固定特征...")
    v4_feat = load_v4_province_features()
    if v4_feat.empty:
        print("  ❌ v4 特征为空")
        return 1

    # --- 2. 加载 MODIS ---
    print("\n[2] 加载 MODIS 地级市...")
    if not MODIS_PATH.exists():
        print(f"  ❌ MODIS 文件不存在: {MODIS_PATH}")
        print(f"    请先运行 v5_01_modis_city_aggregate.py")
        return 1
    modis = load_modis()

    # --- 3. 加载 CLCD ---
    print("\n[3] 加载 CLCD 地级市...")
    if not CLCD_PATH.exists():
        print(f"  ❌ CLCD 文件不存在: {CLCD_PATH}")
        return 1
    clcd = load_clcd()

    # --- 4. 加载 NASA ---
    print("\n[4] 加载 NASA POWER 地级市...")
    if not NASA_PATH.exists():
        print(f"  ❌ NASA 文件不存在: {NASA_PATH}")
        return 1
    nasa = load_nasa()

    # --- 5. 合并 ---
    print("\n[5] 合并...")
    # 从 MODIS 开始（基表，包含所有 province/city/city_id/year 组合）
    merged = modis.copy()

    # CLCD
    merged = merged.merge(
        clcd[["city_id", "year", "cropland_ratio"]],
        on=["city_id", "year"], how="left"
    )

    # NASA
    merged = merged.merge(
        nasa, on=["province", "city", "year"], how="left", suffixes=("", "_nasa")
    )

    # v4 省级特征（按 province + year 匹配）
    merged = merged.merge(
        v4_feat, on=["province", "year"], how="left", suffixes=("", "_v4")
    )

    # 填充不可用的 NASA 列（已重名的加后缀）
    for c in ["temp", "prec", "sun"]:
        if c in merged.columns and c + "_v4" in merged.columns:
            # v4 的 temp/prec/sun 是省级的，我们用地级市的 NASA POWER
            # 如果已有 temp_mean_c / prec_mm_day，保留地级市版本
            pass

    merged = merged.sort_values(["province", "city", "year"]).reset_index(drop=True)

    print(f"  合并后: {len(merged)} rows × {merged.shape[1]} cols")
    nan_report = merged.isna().sum()
    bad_cols = nan_report[nan_report > 0]
    if len(bad_cols) > 0:
        print(f"  ⚠️  缺失值列:")
        for c, v in bad_cols.items():
            print(f"    {c}: {v} NaN ({v/len(merged)*100:.1f}%)")

    # --- 6. 保存 ---
    print(f"\n[6] 保存...")
    OUT.parent.mkdir(parents=True, exist_ok=True)
    merged.to_parquet(OUT, index=False)
    print(f"  ✅ {OUT} ({len(merged)} rows × {merged.shape[1]} cols)")

    # --- 7. 校验 ---
    print(f"\n[7] 校验...")
    print(f"  10 省覆盖: {merged['province'].nunique()}")
    print(f"  地级市数: {merged['city'].nunique()}")
    print(f"  年份范围: {merged['year'].min()}-{merged['year'].max()}")
    print(f"  总 NaN: {merged.isna().sum().sum()}")

    # --- 8. 抽样 ---
    print(f"\n[8] 抽样（河南 郑州市）:")
    sample = merged[(merged["province"] == "河南") & (merged["city"] == "郑州市")]
    if not sample.empty:
        show_cols = [c for c in merged.columns if c not in ["province", "city", "city_id"]]
        print(sample[show_cols].to_string(index=False))

    return 0


if __name__ == "__main__":
    sys.exit(main())
