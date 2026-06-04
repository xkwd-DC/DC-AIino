#!/usr/bin/env python3
"""v4 缺失值统计 + 8:2 时序划分 → train_v4.csv / test_v4.csv

输出：
  data/interim/train_v4.csv
  data/interim/test_v4.csv
"""

import logging
import sys
from pathlib import Path

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[2]
V4_PANEL = PROJECT_ROOT / "data" / "interim" / "paper_panel_v4.parquet"
TRAIN_OUT = PROJECT_ROOT / "data" / "interim" / "train_v4.csv"
TEST_OUT = PROJECT_ROOT / "data" / "interim" / "test_v4.csv"

# 8:2 时序划分：前 80% 年份（2011-2020）训练，后 20%（2021-2023）测试
TRAIN_YEARS = list(range(2011, 2021))  # 10 years
TEST_YEARS = list(range(2021, 2024))    # 3 years


def main() -> int:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
        datefmt="%H:%M:%S",
    )

    # Load v4
    v4 = pd.read_parquet(V4_PANEL)
    logging.info("paper_panel_v4: %d rows × %d cols", len(v4), len(v4.columns))

    # ─── Missing value analysis ───
    print("\n" + "=" * 60)
    print("📊 MISSING VALUE ANALYSIS")
    print("=" * 60)

    total_nan = v4.isna().sum().sum()
    print(f"\nTotal NaN: {total_nan} (out of {v4.size} cells = {total_nan/v4.size*100:.4f}%)")

    nan_cols = v4.isna().sum()
    nan_cols = nan_cols[nan_cols > 0]
    if len(nan_cols) > 0:
        print(f"\nColumns with NaN:")
        for col, cnt in nan_cols.items():
            pct = cnt / len(v4) * 100
            print(f"  {col:30s}: {cnt:5d} / {len(v4)} ({pct:.2f}%)")
    else:
        print(f"✅  All columns have 0 NaN")

    # Per-column non-null stats
    print(f"\nPer-column stats:")
    for c in v4.columns:
        if v4[c].dtype.kind in "if":
            nulls = v4[c].isna().sum()
            if nulls > 0:
                print(f"  {c:30s}: {nulls} NaN, min={v4[c].min():.4f}, max={v4[c].max():.4f}")

    # ─── 8:2 Temporal split ───
    print("\n" + "=" * 60)
    print("📊 8:2 TEMPORAL SPLIT")
    print("=" * 60)

    train = v4[v4["year"].isin(TRAIN_YEARS)].copy()
    test = v4[v4["year"].isin(TEST_YEARS)].copy()

    print(f"\nTraining set ({TRAIN_YEARS[0]}-{TRAIN_YEARS[-1]}): {len(train)} rows")
    print(f"   Provinces: {train['province'].nunique()}")
    print(f"   Years: {sorted(train['year'].unique())}")
    print(f"Test set ({TEST_YEARS[0]}-{TEST_YEARS[-1]}): {len(test)} rows")
    print(f"   Provinces: {test['province'].nunique()}")
    print(f"   Years: {sorted(test['year'].unique())}")
    print(f"   Split ratio: {len(train)/(len(train)+len(test))*100:.1f} / {len(test)/(len(train)+len(test))*100:.1f}")

    # Verify no leakage
    train_provs = set(train["province_code"].unique())
    test_provs = set(test["province_code"].unique())
    if train_provs != test_provs:
        missing_in_test = train_provs - test_provs
        missing_in_train = test_provs - train_provs
        if missing_in_test:
            print(f"⚠️  Provinces in train but not in test: {missing_in_test}")
        if missing_in_train:
            print(f"⚠️  Provinces in test but not in train: {missing_in_train}")

    # Save
    TRAIN_OUT.parent.mkdir(parents=True, exist_ok=True)
    train.to_csv(TRAIN_OUT, index=False)
    test.to_csv(TEST_OUT, index=False)
    logging.info("✅ Train: %s (%d rows)", TRAIN_OUT, len(train))
    logging.info("✅ Test:  %s (%d rows)", TEST_OUT, len(test))

    # Also save Parquet
    train_pq = TRAIN_OUT.with_suffix(".parquet")
    test_pq = TEST_OUT.with_suffix(".parquet")
    train.to_parquet(train_pq, index=False)
    test.to_parquet(test_pq, index=False)
    logging.info("✅ Train parquet: %s", train_pq)
    logging.info("✅ Test parquet:  %s", test_pq)

    return 0


if __name__ == "__main__":
    sys.exit(main())
