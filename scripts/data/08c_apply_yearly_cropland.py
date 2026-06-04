#!/usr/bin/env python3
"""8c Step 2：用逐年 cropland_ratio 替换 paper_panel_v4 中的静态值。

由于 MODIS 月度数据已经算好了（4836 行 × 14 列的全省域均值），
8c 的变化是：
1. cropland_ratio 从静态值（31 省）→ 动态值（31 省 × 13 年）
2. MODIS NDVI/LST 的值不变（v4 策略：保留均值 + 逐年 cropland_ratio 列）

输出：paper_panel_v4.parquet（更新版，cropland_ratio 变成逐年动态）
"""

import logging
import sys
from pathlib import Path

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[2]
V4_PANEL = PROJECT_ROOT / "data" / "interim" / "paper_panel_v4.parquet"
MODIS_V4 = PROJECT_ROOT / "data" / "interim" / "modis_province_monthly_v4.parquet"
CROP_RATIO_YEARLY = PROJECT_ROOT / "data" / "interim" / "province_cropland_ratio_yearly.parquet"

# Fallback: if yearly data not yet available, use static
CROP_RATIO_STATIC = PROJECT_ROOT / "data" / "interim" / "province_cropland_ratio.parquet"


def main() -> int:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
        datefmt="%H:%M:%S",
    )

    # Load
    v4 = pd.read_parquet(V4_PANEL)
    modis = pd.read_parquet(MODIS_V4)
    logging.info("v4 panel: %d rows × %d cols", len(v4), len(v4.columns))
    logging.info("MODIS v4:  %d rows × %d cols", len(modis), len(modis.columns))

    # Check if yearly cropland ratio is available
    if CROP_RATIO_YEARLY.exists():
        cr = pd.read_parquet(CROP_RATIO_YEARLY)
        logging.info("使用逐年 cropland_ratio: %d rows (31省 × %d年)",
                     len(cr), cr["year"].nunique())
        use_yearly = True
    else:
        cr = pd.read_parquet(CROP_RATIO_STATIC)
        logging.info("逐年数据未就绪，使用静态 cropland_ratio (31省)")
        use_yearly = False

    # Update MODIS v4: replace static cropland_ratio with yearly
    if use_yearly:
        # Get a mapping of province → static cropland_ratio (for reference)
        static_map = pd.read_parquet(CROP_RATIO_STATIC)
        static_map = static_map.set_index("province_code")["cropland_ratio"].to_dict()

        # Merge yearly cropland_ratio into modis
        modis_before = modis.copy()
        modis = modis.drop(columns=["cropland_ratio"])
        modis = modis.merge(
            cr[["province_code", "year", "cropland_ratio"]],
            on=["province_code", "year"],
            how="left",
        )
        missing = modis[modis["cropland_ratio"].isna()]
        if len(missing) > 0:
            logging.warning("逐年 cropland_ratio 有 %d 行缺失，回退到静态值", len(missing))
            for idx in missing.index:
                prov_code = missing.loc[idx, "province_code"]
                modis.loc[idx, "cropland_ratio"] = static_map.get(prov_code, 0.0)

        # Save updated modis
        modis.to_parquet(MODIS_V4, index=False)
        logging.info("✅ MODIS v4 更新为逐年 cropland_ratio: %s", MODIS_V4)

        # Now update paper_panel_v4
        # Get yearly cropland ratio per province×year (one per year)
        cr_yearly = cr[["province_code", "year", "cropland_ratio"]].drop_duplicates()
        v4_before = v4.copy()

        # Replace cropland_ratio column
        if "cropland_ratio" in v4.columns:
            v4 = v4.drop(columns=["cropland_ratio"])
        v4 = v4.merge(
            cr_yearly,
            on=["province_code", "year"],
            how="left",
        )

        # Check for NaN
        nan_v4 = v4[v4["cropland_ratio"].isna()]
        if len(nan_v4) > 0:
            logging.error("panel v4 有 %d 行未匹配到 cropland_ratio！", len(nan_v4))
            # Fall back: fill with static
            for idx in nan_v4.index:
                prov_code = nan_v4.loc[idx, "province_code"]
                v4.loc[idx, "cropland_ratio"] = static_map.get(prov_code, 0.0)

        v4.to_parquet(V4_PANEL, index=False)
        logging.info("✅ paper_panel_v4 更新为逐年 cropland_ratio: %s", V4_PANEL)

        # Show 8c impact: which provinces have biggest cropland change over time
        print("\n=== 8c 影响评估：各省 cropland_ratio 最大年份变化 ===")
        for prov_code in sorted(cr["province_code"].unique()):
            p = cr[cr["province_code"] == prov_code].sort_values("year")
            if len(p) < 2:
                continue
            max_change = p["cropland_ratio"].max() - p["cropland_ratio"].min()
            pct_change = max_change / p["cropland_ratio"].mean() * 100
            if pct_change > 2:
                prov_name = p.iloc[0]["province"]
                print(f"  {prov_name:12s}: {p['cropland_ratio'].min():.4f} → {p['cropland_ratio'].max():.4f} (Δ={max_change:.4f}, {pct_change:+.1f}%)")

    else:
        logging.info("逐年 CLCD 数据尚未就绪，面板保持静态 cropland_ratio。")
        logging.info("等 8c 下载完成后，运行: .venv-data/bin/python scripts/data/08c_calc_cropland_ratio_yearly.py")
        logging.info("然后重跑本脚本:  .venv-data/bin/python scripts/data/08c_apply_yearly_cropland.py")

    # Summary
    print(f"\n{'='*60}")
    print(f"paper_panel_v4 当前状态:")
    print(f"{'='*60}")
    print(f"  Shape: {v4.shape}")
    has_yearly = "cropland_ratio" in v4.columns and v4["year"].nunique() == 13
    cr_source = "逐年" if use_yearly else "静态"
    print(f"  cropland_ratio: {cr_source} ({v4['cropland_ratio'].min():.4f}–{v4['cropland_ratio'].max():.4f})")
    print(f"  NaN: {v4.isna().sum().sum()}")
    print(f"  Columns: {len(v4.columns)}")
    print(f"  Added: prec_nasa, sun_nasa, cropland_ratio")

    return 0


if __name__ == "__main__":
    sys.exit(main())
