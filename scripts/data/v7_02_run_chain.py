#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""按顺序跑 v6/v7 链路，逐步记录日志，任一步失败即停。

步骤（每一步都是仓库里已有的脚本）：
  1. v6_01c  县治最近格点聚合 TerraClimate → terraclimate_county_yearly_v6.parquet
  2. v6_03   年鉴 × 县级气候 × 省级共享特征 → paper_panel_v6_climate.parquet
  3. v6_08   县级 SPEI 覆盖省级 SPEI → paper_panel_v6_climate_full.parquet
  4. v6_04   XGBoost 留一县（LCO）复跑 → 核对 R² ≈ 0.6604
  5. v6_09   生长季/极端指数 + 滑窗 → paper_panel_v7_prediction.parquet
  6. v6_10   预测方向实验（log_yield / y_anom × 25/15 特征）→ 核对 0.679 / 0.651 / +0.451

用法：
    python scripts/data/v7_02_run_chain.py --log-dir D:\\DC\\_scan\\v7_chain
"""

from __future__ import annotations

import argparse
import subprocess
import sys
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]

STEPS = [
    ("v6_01c 聚合县级气候", ["scripts/data/v6_01c_terraclimate_agg_light.py"]),
    ("v6_03 合并特征矩阵", ["scripts/data/v6_03_merge_v6_matrix.py"]),
    ("v6_08 并入县级 SPEI", ["scripts/data/v6_08_merge_county_spei.py"]),
    ("v6_04 XGB 留一县复跑", ["scripts/data/v6_04_train_xgb_lco.py", "--panel",
                              "paper_panel_v6_climate_full.parquet"]),
    ("v6_09 生长季/极端指数", ["scripts/data/v6_09_build_seasonal_features.py"]),
    ("v6_10 预测方向实验", ["scripts/data/v6_10_train_xgb_prediction.py"]),
]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--log-dir", type=Path, default=Path(r"D:\DC\_scan\v7_chain"))
    ap.add_argument("--only", type=str, default="", help="只跑名字里含该子串的步骤")
    args = ap.parse_args()
    args.log_dir.mkdir(parents=True, exist_ok=True)

    for idx, (label, cmd) in enumerate(STEPS, start=1):
        if args.only and args.only not in label:
            continue
        log = args.log_dir / f"step{idx}_{label.split()[0]}.log"
        print(f"=== [{idx}/{len(STEPS)}] {label} -> {log.name}", flush=True)
        started = time.time()
        with log.open("w", encoding="utf-8") as fh:
            proc = subprocess.run(
                [sys.executable, "-X", "utf8", *cmd],
                cwd=PROJECT_ROOT, stdout=fh, stderr=subprocess.STDOUT,
            )
        elapsed = time.time() - started
        if proc.returncode != 0:
            print(f"    FAILED rc={proc.returncode} after {elapsed:.0f}s（见 {log}）", flush=True)
            print("".join(log.read_text(encoding="utf-8").splitlines(keepends=True)[-15:]), flush=True)
            return proc.returncode
        print(f"    OK {elapsed:.0f}s", flush=True)
        tail = [ln for ln in log.read_text(encoding="utf-8").splitlines() if ln.strip()][-6:]
        for line in tail:
            print(f"    | {line}", flush=True)
    print("CHAIN DONE", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
