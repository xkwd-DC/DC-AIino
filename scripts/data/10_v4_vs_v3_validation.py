#!/usr/bin/env python3
"""验证 v4 final vs v3 的数值偏差"""

import logging
import sys
from pathlib import Path

import pandas as pd
import numpy as np

PROJECT_ROOT = Path(__file__).resolve().parents[2]
V4 = PROJECT_ROOT / "data" / "interim" / "paper_panel_v4.parquet"
V3 = PROJECT_ROOT / "data" / "interim" / "paper_panel_v3.parquet"


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")

    v4 = pd.read_parquet(V4)
    v3 = pd.read_parquet(V3)

    # Merge on province+year
    merged = v4.merge(v3, on=["province_code", "year"], suffixes=("_v4", "_v3"))

    print("=" * 70)
    print("📊 v4 vs v3 数值偏差验证")
    print("=" * 70)

    common_cols = []
    for c in v3.columns:
        if c in v4.columns and c not in ("province_code", "province", "year"):
            common_cols.append(c)

    v3_c, v4_c = [c + "_v3" for c in common_cols], [c + "_v4" for c in common_cols]

    # Only numeric cols
    num_v3 = [c for c in v3_c if merged[c].dtype.kind in "if"]
    num_v4 = [c for c in v4_c if merged[c].dtype.kind in "if"]

    print(f"\n{'列名':30s} {'v3_mean':>12s} {'v4_mean':>12s} {'abs Δ':>12s} {'Δ%':>8s} {'一致?':>6s}")
    print("-" * 82)

    for v3col, v4col in zip(num_v3, num_v4):
        col_name = v3col.replace("_v3", "")
        if col_name not in merged.columns:
            continue

        v3_mean = merged[v3col].mean()
        v4_mean = merged[v4col].mean()
        diff = abs(v4_mean - v3_mean)
        pct = diff / abs(v3_mean) * 100 if v3_mean != 0 else 0
        status = "✅" if pct < 0.1 or diff < 0.001 else "⚠️"

        print(f"{col_name:30s} {v3_mean:>12.4f} {v4_mean:>12.4f} {diff:>12.6f} {pct:>7.2f}%  {status}")

    # Also check v4-only columns
    v4_only = [c for c in v4.columns if c not in v3.columns]
    if v4_only:
        print(f"\nv4 新增列: {', '.join(v4_only)}")

    # Check cropland_ratio year-over-year change magnitude
    print("\n" + "=" * 70)
    print("📊 cropland_ratio 逐年变化量")
    print("=" * 70)
    cr = pd.read_parquet(PROJECT_ROOT / "data" / "interim" / "province_cropland_ratio_yearly.parquet")
    # Width of change per province
    for year in sorted(cr["year"].unique()):
        yr = cr[cr["year"] == year]
        print(f"  {year}: min={yr['cropland_ratio'].min():.4f}  max={yr['cropland_ratio'].max():.4f}  mean={yr['cropland_ratio'].mean():.4f}")

    # Max Δ per province across years
    print("\n各省 cropland_ratio 最大变化（max - min）:")
    prov_delta = cr.groupby("province")["cropland_ratio"].agg(["min", "max", "mean"])
    prov_delta["Δ"] = prov_delta["max"] - prov_delta["min"]
    prov_delta["Δ%"] = prov_delta["Δ"] / prov_delta["mean"] * 100
    prov_delta = prov_delta.sort_values("Δ", ascending=False)
    for prov, row in prov_delta.iterrows():
        print(f"  {prov:12s}: {row['min']:.4f} → {row['max']:.4f}  Δ={row['Δ']:.4f} ({row['Δ%']:.1f}%)")

    return 0


if __name__ == "__main__":
    sys.exit(main())
