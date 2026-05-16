"""修正 paper_panel_v1 中 prec / sun 列（Wang 用省会单站，应用省域代表点）。

输入：
  data/interim/paper_panel_v1.parquet           王天硕原版 + MODIS NDVI
  data/interim/nasa_power_annual.csv            NASA POWER 31 省代表点年度气象

修复内容（v1 → v2）：
  - prec：Wang 省会单站 (mean 423/std 67) → NASA POWER 省代表点 (mean ~750/std ~500)
  - sun：Wang 省会单站 (mean 2407) → NASA POWER 辐射比近似 (mean ~3000)
  - 保留 Wang 的原版列：`prec_capital`, `sun_capital`（命名表明是省会单站）

不修复：
  - Y：未做完整 Butterworth 去趋势（57% 跌幅），由熊鑫 1.6 task 处理
  - flood_a：Wang 原始数据正确，与论文表 3-2 的差异可能是 trimmed mean

输出：
  data/interim/paper_panel_v2.parquet           prec/sun 用省域代表点 + 原版备份列

CLI:
    python scripts/data/07_fix_panel_v2.py
"""
from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[2]
V1_PARQUET = PROJECT_ROOT / "data" / "interim" / "paper_panel_v1.parquet"
NASA_POWER_CSV = PROJECT_ROOT / "data" / "interim" / "nasa_power_annual.csv"
DEFAULT_OUT = PROJECT_ROOT / "data" / "interim" / "paper_panel_v2.parquet"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="v1 → v2：用 NASA POWER 省代表点修 prec/sun")
    parser.add_argument("--v1", type=Path, default=V1_PARQUET)
    parser.add_argument("--nasa", type=Path, default=NASA_POWER_CSV)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--verbose", "-v", action="store_true")
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
        datefmt="%H:%M:%S",
    )

    v1 = pd.read_parquet(args.v1)
    nasa = pd.read_csv(args.nasa, dtype={"province_code": str})
    logging.info("v1 %d 行, nasa %d 行", len(v1), len(nasa))

    # 保留原版列作为备份
    v2 = v1.rename(columns={"prec": "prec_capital", "sun": "sun_capital"})

    # 合并 NASA POWER 数据
    v2 = v2.merge(
        nasa[["province_code", "year", "prec", "sun"]],
        on=["province_code", "year"], how="left",
    )

    # 校验完整性
    missing = v2[v2["prec"].isna() | v2["sun"].isna()]
    if not missing.empty:
        logging.warning("有 %d 行 prec/sun 缺失（NASA POWER 没覆盖）", len(missing))

    # 重排列：11 维特征用新 prec/sun
    feature_order = [
        "province_code", "province", "year",
        "y",
        "irr", "flood", "sun", "temp", "spei", "prec",
        "mech", "fert", "drou_a", "flood_a", "ndvi",
        # 次要列
        "prec_capital", "sun_capital",
        "ndvi_summer_peak", "ndvi_yearly",
        "lst_day_growing_mean_k", "lst_night_growing_mean_k",
    ]
    extras = [c for c in v2.columns if c not in feature_order]
    v2 = v2[feature_order + extras].sort_values(["province_code", "year"]).reset_index(drop=True)

    args.out.parent.mkdir(parents=True, exist_ok=True)
    v2.to_parquet(args.out, index=False)
    logging.info("✅ 写入 %s（%d 行 × %d 列）", args.out, len(v2), len(v2.columns))

    print()
    print("=== 修复后的统计 ===")
    for col in ["prec", "sun", "y", "flood_a", "temp", "spei"]:
        m = v2[col].mean()
        s = v2[col].std()
        lo = v2[col].min()
        hi = v2[col].max()
        print(f"  {col:15s} mean={m:8.2f}  std={s:8.2f}  range=[{lo:.2f}, {hi:.2f}]")

    print()
    print("=== 论文表 3-2 对照 ===")
    print(f"  prec  论文 mean=754.5 / std=465.0    实测 mean={v2['prec'].mean():.1f} / std={v2['prec'].std():.1f}")
    print(f"  sun   论文 mean=2085.9              实测 mean={v2['sun'].mean():.1f}")
    print()
    print(f"  ⚠️  Y 仍漂移 (57% 跌)——熊鑫需重做 Butterworth (task 1.6)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
