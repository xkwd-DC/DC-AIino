"""时空对齐——把 MODIS 月度 panel 按 (province, year) 折叠 → 加 NDVI 列到论文 panel。

任务 1.7（截止 2026-07-15）。

输入：
  data/interim/modis_province_monthly.parquet     31×156 月度 NDVI/LST
  data/interim/paper_panel_raw.parquet            31×13 年度 Y + 10 X（王天硕原版）

输出：
  data/interim/paper_panel_v1.parquet             31×13 × 11 X + Y（完整）
  data/interim/alignment_report.md（重写）         匹配率报告

NDVI 折叠策略：取生长季（4-10 月）均值——与作物物候对齐，比全年均值更敏感
LST 暂不进 11 维特征（doc 08 §3.2 注：默认不进，作为可选研究列）

CLI:
    python scripts/data/06_align_panel.py
"""
from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[2]
MODIS_PARQUET = PROJECT_ROOT / "data" / "interim" / "modis_province_monthly.parquet"
PAPER_PARQUET = PROJECT_ROOT / "data" / "interim" / "paper_panel_raw.parquet"
DEFAULT_OUT = PROJECT_ROOT / "data" / "interim" / "paper_panel_v1.parquet"
DEFAULT_REPORT = PROJECT_ROOT / "data" / "interim" / "alignment_report.md"

GROWING_SEASON_MONTHS = (4, 5, 6, 7, 8, 9, 10)


def fold_modis_annual(modis: pd.DataFrame) -> pd.DataFrame:
    """月度 → 年度（生长季 4-10 月均值 / 全年均值 / 7-8 月夏季峰值）。"""
    gs = modis[modis["month"].isin(GROWING_SEASON_MONTHS)]
    annual = (
        gs.groupby(["province_code", "province", "year"], as_index=False)
        .agg(
            ndvi=("ndvi_mean", "mean"),
            ndvi_summer_peak=("ndvi_mean", "max"),
            lst_day_growing_mean_k=("lst_day_mean_k", "mean"),
            lst_night_growing_mean_k=("lst_night_mean_k", "mean"),
        )
    )
    # 全年平均（次要列）
    yr_full = (
        modis.groupby(["province_code", "year"], as_index=False)
        .agg(ndvi_yearly=("ndvi_mean", "mean"))
    )
    annual = annual.merge(yr_full, on=["province_code", "year"], how="left")
    return annual


def write_report(path: Path, paper: pd.DataFrame, modis_annual: pd.DataFrame, merged: pd.DataFrame) -> None:
    matched = merged.dropna(subset=["ndvi"]).shape[0]
    total = paper.shape[0]
    rate = matched / total * 100

    paper_keys = set(zip(paper["province_code"], paper["year"]))
    modis_keys = set(zip(modis_annual["province_code"], modis_annual["year"]))
    miss_in_modis = sorted(paper_keys - modis_keys)
    miss_in_paper = sorted(modis_keys - paper_keys)

    content = f"""# 时空对齐报告（任务 1.7）

**状态**：{"✅ PASS" if rate >= 95 else "❌ FAIL"}（要求 ≥ 95%）
**论文 panel 行数**：{total}（31 × 13 = 403）
**MODIS 年度 panel 行数**：{len(modis_annual)}（31 × 13 = 403）
**合并后含 NDVI 的行数**：{matched}
**对齐准确率**：{rate:.1f}%

## 合并 key
- `province_code` (民政部 6 位)
- `year`

## NDVI 列定义
- `ndvi`：生长季（4-10 月）月度 NDVI 均值 — 与作物物候对齐，**作为 11 维特征的 NDVI 列**
- `ndvi_summer_peak`：生长季月度 NDVI 最大值（次要参考）
- `ndvi_yearly`：全年 12 月均值（含冬季低值，参考用）
- `lst_day_growing_mean_k` / `lst_night_growing_mean_k`：生长季 LST 均值（**不进 11 维**，可选研究列）

## 缺失分析

### 论文有但 MODIS 缺
{f'{len(miss_in_modis)} 条：{miss_in_modis[:10]}{"..." if len(miss_in_modis) > 10 else ""}' if miss_in_modis else '无'}

### MODIS 有但论文缺
{f'{len(miss_in_paper)} 条：{miss_in_paper[:10]}{"..." if len(miss_in_paper) > 10 else ""}' if miss_in_paper else '无'}

## 下游使用
- 熊鑫训练：直接 `pd.read_parquet("data/interim/paper_panel_v1.parquet")`，11 维 X + Y 都齐
- 标准化（1.8 task）：归熊鑫，用 sklearn StandardScaler，scaler.pkl 存 backend/models/
"""
    path.write_text(content, encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="MODIS + 论文面板时空对齐 → paper_panel_v1.parquet")
    parser.add_argument("--modis", type=Path, default=MODIS_PARQUET)
    parser.add_argument("--paper", type=Path, default=PAPER_PARQUET)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--report", type=Path, default=DEFAULT_REPORT)
    parser.add_argument("--verbose", "-v", action="store_true")
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
        datefmt="%H:%M:%S",
    )

    if not args.modis.exists() or not args.paper.exists():
        logging.error("缺源文件：modis=%s, paper=%s", args.modis.exists(), args.paper.exists())
        return 1

    modis = pd.read_parquet(args.modis)
    paper = pd.read_parquet(args.paper)
    logging.info("MODIS 月度 %d 行，论文面板 %d 行", len(modis), len(paper))

    modis_annual = fold_modis_annual(modis)
    logging.info("MODIS 折叠后年度 %d 行（生长季 4-10 月均值）", len(modis_annual))

    merged = paper.merge(
        modis_annual[["province_code", "year", "ndvi", "ndvi_summer_peak", "ndvi_yearly",
                      "lst_day_growing_mean_k", "lst_night_growing_mean_k"]],
        on=["province_code", "year"], how="left",
    )
    logging.info("合并后 %d 行 × %d 列", len(merged), len(merged.columns))

    # 与 inference.py 11 维顺序对齐
    feature_order = [
        "province_code", "province", "year",
        "y",
        "irr", "flood", "sun", "temp", "spei", "prec",
        "mech", "fert", "drou_a", "flood_a", "ndvi",
        # 次要列（不进 11 维）
        "ndvi_summer_peak", "ndvi_yearly",
        "lst_day_growing_mean_k", "lst_night_growing_mean_k",
    ]
    extras = [c for c in merged.columns if c not in feature_order]
    final = merged[feature_order + extras].sort_values(["province_code", "year"]).reset_index(drop=True)

    args.out.parent.mkdir(parents=True, exist_ok=True)
    final.to_parquet(args.out, index=False)
    logging.info("✅ 写入 %s（%d 行 × %d 列）", args.out, len(final), len(final.columns))

    write_report(args.report, paper, modis_annual, final)
    logging.info("报告写入 %s", args.report)

    print()
    print("=== 完整性 ===")
    for col in final.columns[:15]:  # 主要 11 维 + meta
        non_null = final[col].notna().sum()
        print(f"  {col:15s} {non_null:4d}/{len(final)}")

    print()
    print("=== 河南各年（NDVI 生长季均值）===")
    h = final[final["province"] == "河南省"].sort_values("year")
    print(h[["year", "y", "ndvi", "spei", "temp", "prec"]].to_string(index=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
