#!/usr/bin/env python3
"""8b Step 1：用静态耕地比例对全省域 MODIS 均值做加权修正。

不实时读 CLCD，而是用预计算的 province_cropland_ratio.parquet。

原理：
  MODIS 全省域均值 = (耕地区域均值 × 耕地面积) + (非耕地区域均值 × 非耕地面积)
  我们想知道的是「耕地区域均值」。
  
  假设非耕地区域的 MODIS 值 = 全省域均值 × discount_factor，
  其中 discount_factor 由经验估计（耕地区 NDVI 高于非耕地区）。
  
  更简单的替代：直接用 cropland_ratio 做调节因子。
  耕地区 NDVI ≈ 全省域均值 × (1 + alpha × (cropland_ratio − mean_ratio))
  但这样参数 alpha 不好定。

  最稳健方案：直接用原来的全省域均值 + 新增 cropland_ratio 列。
  ML 模型自己能学到"同样 NDVI，耕地多的省风险不同"。
  这样完全不需要读栅格，也不引入额外假设。

输出：modis_province_monthly_v4.parquet
  = v3 列 + cropland_ratio
"""

import logging
import sys
from pathlib import Path

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[2]
V3_MODIS = PROJECT_ROOT / "data" / "interim" / "modis_province_monthly.parquet"
CROPLAND_RATIO = PROJECT_ROOT / "data" / "interim" / "province_cropland_ratio.parquet"
OUT_PATH = PROJECT_ROOT / "data" / "interim" / "modis_province_monthly_v4.parquet"


def main() -> int:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
        datefmt="%H:%M:%S",
    )

    logging.info("读取 v3 全省域 MODIS: %s", V3_MODIS)
    modis = pd.read_parquet(V3_MODIS)
    logging.info("  %d 行 × %d 列", len(modis), len(modis.columns))

    logging.info("读取耕地比例: %s", CROPLAND_RATIO)
    cr = pd.read_parquet(CROPLAND_RATIO)
    logging.info("  %d 个省", len(cr))

    # Merge cropland_ratio into MODIS
    v4 = modis.merge(
        cr[["province_code", "cropland_ratio"]],
        on="province_code",
        how="left",
    )
    logging.info("合并后: %d 行 × %d 列", len(v4), len(v4.columns))

    # Verify merge
    missing = v4[v4["cropland_ratio"].isna()]
    if len(missing) > 0:
        logging.warning("以下省份未匹配到耕地比例: %s", list(missing["province"]))
        return 1

    # Reorder columns: put cropland_ratio near valid_pixel_ratio
    cols = list(v4.columns)
    if "valid_pixel_ratio" in cols:
        vp_idx = cols.index("valid_pixel_ratio")
        cols.remove("cropland_ratio")
        cols.insert(vp_idx + 1, "cropland_ratio")
        v4 = v4[cols]

    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    v4.to_parquet(OUT_PATH, index=False)
    logging.info("✅ 写入 %s (%d 行 × %d 列)", OUT_PATH, len(v4), len(v4.columns))

    # Compare with v3
    print("\n=== v4 (cropland-weighted) vs v3 (simple mean) ===")
    merged_cmp = v4.merge(
        modis[
            ["province_code", "year", "month", "ndvi_mean", "lst_day_mean_k", "lst_night_mean_k"]
        ],
        on=["province_code", "year", "month"],
        suffixes=("_v4", "_v3"),
        how="inner",
    )

    for col in ["ndvi_mean", "lst_day_mean_k", "lst_night_mean_k"]:
        v4c = f"{col}_v4"
        v3c = f"{col}_v3"
        if v4c not in merged_cmp.columns or v3c not in merged_cmp.columns:
            continue
        delta = merged_cmp[v4c] - merged_cmp[v3c]
        print(f"  {col:20s}: Δ mean={delta.mean():+.6f}  "
              f"Δ std={delta.std():.6f}  "
              f"min={delta.min():+.6f}  max={delta.max():+.6f}")

    print(f"\n  cropland_ratio: mean={v4['cropland_ratio'].mean():.4f}  "
          f"min={v4['cropland_ratio'].min():.4f}  max={v4['cropland_ratio'].max():.4f}")
    print(f"  NaN count: {v4.isna().sum().sum()}")

    # Check: which provinces have highest/lowest cropland ratio
    prov_mean = v4.groupby("province")["cropland_ratio"].first().sort_values()
    print(f"\n  最高耕地占比: {prov_mean.tail(3).to_dict()}")
    print(f"  最低耕地占比: {prov_mean.head(3).to_dict()}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
