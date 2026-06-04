#!/usr/bin/env python3
"""8b Step 2：将 cropland_ratio 合并到 paper_panel_v4，做最终验证。

输出：data/interim/paper_panel_v4.parquet（更新版，含 cropland_ratio）
"""

import logging
import sys
from pathlib import Path

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[2]
V4_PANEL = PROJECT_ROOT / "data" / "interim" / "paper_panel_v4.parquet"
MODIS_V4 = PROJECT_ROOT / "data" / "interim" / "modis_province_monthly_v4.parquet"
V3_PANEL = PROJECT_ROOT / "data" / "interim" / "paper_panel_v3.parquet"


def main() -> int:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
        datefmt="%H:%M:%S",
    )

    # Load
    v4 = pd.read_parquet(V4_PANEL)
    modis = pd.read_parquet(MODIS_V4)
    v3 = pd.read_parquet(V3_PANEL)

    logging.info("v4 panel: %d rows × %d cols", len(v4), len(v4.columns))
    logging.info("v3 panel: %d rows × %d cols", len(v3), len(v3.columns))

    # Get static cropland_ratio (one per province)
    cr = modis[["province_code", "province", "cropland_ratio"]].drop_duplicates()
    logging.info("cropland_ratio: %d provinces", len(cr))

    # Merge into v4
    v4 = v4.merge(cr[["province_code", "cropland_ratio"]], on="province_code", how="left")
    missing = v4[v4["cropland_ratio"].isna()]
    if len(missing) > 0:
        logging.error("Unmerged provinces: %s", list(missing["province"].unique()))
        return 1

    # Reorder: put cropland_ratio near ndvi / lst columns
    ndvi_idx = list(v4.columns).index("ndvi") if "ndvi" in v4.columns else -1
    if ndvi_idx > 0:
        cols = list(v4.columns)
        cols.remove("cropland_ratio")
        cols.insert(ndvi_idx, "cropland_ratio")
        v4 = v4[cols]

    # Save
    V4_PANEL.parent.mkdir(parents=True, exist_ok=True)
    v4.to_parquet(V4_PANEL, index=False)
    logging.info("✅ Updated v4 panel: %s (%d rows × %d cols)", V4_PANEL, len(v4), len(v4.columns))

    # ─── Validation ───

    print("\n" + "=" * 60)
    print("🔍 VALIDATION: v4 vs v3")
    print("=" * 60)

    # 1. Column diff
    added = sorted(set(v4.columns) - set(v3.columns))
    removed = sorted(set(v3.columns) - set(v4.columns))
    print(f"\nAdded columns: {added}")
    print(f"Removed columns: {removed}")

    # 2. Shape
    print(f"\nShape: v3={v3.shape}, v4={v4.shape}")

    # 3. NaN check
    nan_total = v4.isna().sum().sum()
    if nan_total > 0:
        nan_cols = v4.isna().sum()
        nan_cols = nan_cols[nan_cols > 0]
        print(f"\n⚠️  NaN count: {nan_total}")
        for col, cnt in nan_cols.items():
            print(f"   {col}: {cnt} NaN")
    else:
        print(f"\n✅  NaN count: 0 (clean!)")

    # 4. Key column diff (mean/std)
    print(f"\n{'Column':25s} {'v3_mean':>12s} {'v4_mean':>12s} {'Δ%':>10s}")
    print("-" * 60)
    for c in sorted(set(v3.columns) & set(v4.columns)):
        if c in ("province_code", "province"):
            continue
        v3_col = v3[c]
        v4_col = v4[c]
        if v3_col.dtype.kind not in "if":
            continue
        v3_m = v3_col.mean()
        v4_m = v4_col.mean()
        if v3_m == 0:
            pct = "N/A"
        else:
            pct = f"{(v4_m - v3_m) / v3_m * 100:+7.2f}%"
        if abs(v4_m - v3_m) > 0.000001:
            print(f"{c:25s} {v3_m:>12.4f} {v4_m:>12.4f} {pct:>10s}")
        else:
            print(f"{c:25s} {v3_m:>12.4f} {v4_m:>12.4f}     =")

    # 5. cropland_ratio stats
    if "cropland_ratio" in v4.columns:
        print(f"\n{'cropland_ratio':25s}: mean={v4['cropland_ratio'].mean():.4f}  "
              f"min={v4['cropland_ratio'].min():.4f}  max={v4['cropland_ratio'].max():.4f}")

    # 6. v4 describe
    print("\n" + "=" * 60)
    print("📊 v4 describe()")
    print("=" * 60)
    num_cols = v4.select_dtypes(include="number").columns
    print(v4[num_cols].describe().to_string())

    return 0


if __name__ == "__main__":
    sys.exit(main())
