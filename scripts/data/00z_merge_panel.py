"""合并各来源 → data/interim/paper_panel_raw.parquet（论文面板重建版）。

输入（按可用性合并，缺失列填 NaN）：
  - data/interim/nasa_power_annual.csv          [temp, prec, sun]
  - data/interim/spei_province_annual.csv       [spei]
  - data/raw/paper_panel/stats_panel.csv        [yield, grain_sown, irr_area, mech, fert, disaster]
    （由 00a_fetch_stats_gov_cn_local.py 石灵子在国内 IP 跑，回传后放这里）

输出：data/interim/paper_panel_raw.parquet
      schema 见 docs/08_数据采集任务_石灵子.md §11.3

派生列：
  - irr (%)        = irr_area / grain_sown × 100      （灌溉率：粮食灌溉面积比例近似）
  - drou_a (%)     = 旱灾代理：从 SPEI 推（参与生长季月 SPEI<-1 占比 × 100）
  - flood_a (%)    = 涝灾代理：参与生长季月 SPEI>+1 占比 × 100
  - flood (%)      = 同 flood_a（论文里两列含义不完全一样，这里先简化）

⚠️  drou_a / flood_a / flood 是「代理列」，标注在 metadata 里
    （等 stats_panel.csv 有真实"水灾受灾面积"时再换）

CLI:
    python scripts/data/00z_merge_panel.py
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[2]
NASA_POWER_CSV = PROJECT_ROOT / "data" / "interim" / "nasa_power_annual.csv"
SPEI_CSV = PROJECT_ROOT / "data" / "interim" / "spei_province_annual.csv"
SPEI_DAILY_DIR = PROJECT_ROOT / "data" / "interim" / "spei_daily"  # 不存在则用月度
STATS_CSV = PROJECT_ROOT / "data" / "raw" / "paper_panel" / "stats_panel.csv"

DEFAULT_OUT_PARQUET = PROJECT_ROOT / "data" / "interim" / "paper_panel_raw.parquet"
DEFAULT_OUT_META = PROJECT_ROOT / "data" / "interim" / "paper_panel_raw_metadata.json"

# 31 个内陆省（不含港澳台）— 与 doc 08 §3.2 对齐
CANONICAL_PROVINCES: list[tuple[str, str]] = [
    ("110000", "北京市"), ("120000", "天津市"), ("130000", "河北省"), ("140000", "山西省"),
    ("150000", "内蒙古自治区"), ("210000", "辽宁省"), ("220000", "吉林省"), ("230000", "黑龙江省"),
    ("310000", "上海市"), ("320000", "江苏省"), ("330000", "浙江省"), ("340000", "安徽省"),
    ("350000", "福建省"), ("360000", "江西省"), ("370000", "山东省"), ("410000", "河南省"),
    ("420000", "湖北省"), ("430000", "湖南省"), ("440000", "广东省"), ("450000", "广西壮族自治区"),
    ("460000", "海南省"), ("500000", "重庆市"), ("510000", "四川省"), ("520000", "贵州省"),
    ("530000", "云南省"), ("540000", "西藏自治区"), ("610000", "陕西省"), ("620000", "甘肃省"),
    ("630000", "青海省"), ("640000", "宁夏回族自治区"), ("650000", "新疆维吾尔自治区"),
]


def build_skeleton(years: range) -> pd.DataFrame:
    """31 省 × N 年 骨架。"""
    rows = []
    for pc, name in CANONICAL_PROVINCES:
        for y in years:
            rows.append({"province_code": pc, "province": name, "year": y})
    return pd.DataFrame(rows)


def merge_optional(base: pd.DataFrame, src: Path, cols: list[str], rename: dict[str, str] | None = None) -> tuple[pd.DataFrame, list[str]]:
    """如果 src 存在就 merge 进来，否则只占位列填 NaN。返回 (df, 实际合并的列名)。"""
    rename = rename or {}
    if not src.exists():
        logging.warning("跳过 %s（文件不存在），列 %s 留空", src, cols)
        for c in cols:
            base[c] = pd.NA
        return base, []
    df = pd.read_csv(src, dtype={"province_code": str})
    df = df.rename(columns=rename)
    keep = ["province_code", "year"] + [c for c in cols if c in df.columns]
    base = base.merge(df[keep], on=["province_code", "year"], how="left")
    real_cols = [c for c in cols if c in df.columns]
    logging.info("✅ 合并 %s → 列 %s", src.name, real_cols)
    return base, real_cols


def derive_disaster_proxies(df: pd.DataFrame) -> pd.DataFrame:
    """从 spei_annual_mean 推 drou_a / flood_a / flood 代理列。"""
    if "spei" not in df.columns:
        df["drou_a"] = pd.NA
        df["flood_a"] = pd.NA
        df["flood"] = pd.NA
        return df
    # 简化：年均 SPEI 越负 → 旱情越重；越正 → 涝情越重
    # 映射到 [0, 100]：drou_a = max(0, -spei × 30)；flood_a = max(0, spei × 30)
    df["drou_a"] = df["spei"].apply(lambda v: max(0.0, -float(v) * 30) if pd.notna(v) else pd.NA)
    df["flood_a"] = df["spei"].apply(lambda v: max(0.0, float(v) * 30) if pd.notna(v) else pd.NA)
    df["flood"] = df["flood_a"]  # 暂时同 flood_a
    return df


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="合并各来源 → 论文面板 v0（重建版）")
    parser.add_argument("--years", type=str, default="2011-2023")
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT_PARQUET)
    parser.add_argument("--meta", type=Path, default=DEFAULT_OUT_META)
    parser.add_argument("--verbose", "-v", action="store_true")
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
        datefmt="%H:%M:%S",
    )

    lo, hi = args.years.split("-", 1)
    years = range(int(lo), int(hi) + 1)

    df = build_skeleton(years)
    logging.info("骨架 %d 行（31 × %d）", len(df), len(years))

    sources_used: dict[str, list[str]] = {}

    # NASA POWER: temp, prec, sun
    df, used = merge_optional(df, NASA_POWER_CSV, ["temp", "prec", "sun"])
    if used:
        sources_used["NASA_POWER"] = used

    # SPEI: 用年均
    df, used = merge_optional(
        df, SPEI_CSV, ["spei"],
        rename={"spei_annual_mean": "spei"},
    )
    if used:
        sources_used["SPEI"] = used

    # 统计局：yield, grain_sown, irr_area, mech, fert, disaster
    df, used = merge_optional(
        df, STATS_CSV,
        ["yield", "grain_sown", "irr_area", "mech", "fert", "disaster"],
    )
    if used:
        sources_used["STATS_GOV_CN"] = used

    # 派生：irr (灌溉率 %)
    if "irr_area" in df.columns and "grain_sown" in df.columns:
        df["irr"] = (df["irr_area"] / df["grain_sown"] * 100).round(2)
        sources_used.setdefault("DERIVED", []).append("irr = irr_area / grain_sown × 100")

    # 派生：灾害代理
    df = derive_disaster_proxies(df)
    sources_used.setdefault("DERIVED", []).extend(
        ["drou_a = max(0, -spei × 30) [proxy]", "flood_a = max(0, spei × 30) [proxy]", "flood = flood_a [proxy]"]
    )

    # 输出顺序符合 doc 08 §11.3
    schema_order = [
        "province_code", "province", "year",
        "yield",
        "irr", "flood", "sun", "temp", "spei", "prec", "mech", "fert", "drou_a", "flood_a",
    ]
    extras = [c for c in df.columns if c not in schema_order]
    df = df[[c for c in schema_order if c in df.columns] + extras]

    args.out.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(args.out, index=False)
    logging.info("✅ 写入 %s (%d 行 × %d 列)", args.out, len(df), len(df.columns))

    completeness = {col: int(df[col].notna().sum()) for col in df.columns if col not in ("province_code", "province", "year")}
    meta = {
        "rows": len(df),
        "year_range": [int(lo), int(hi)],
        "sources": sources_used,
        "completeness": completeness,
        "schema": "docs/08_数据采集任务_石灵子.md §11.3（暂缺 NDVI 等 MODIS pipeline 完成后再合）",
        "notes": [
            "drou_a / flood_a / flood 是 SPEI 派生 proxy，等 stats.gov.cn 数据回来再换",
            "sun 是 NASA POWER 辐射比近似（4380×ALLSKY/CLRSKY），偏高约 1.3x，Z-score 后等价",
            "yield/irr_area/mech/fert/disaster 需要石灵子本机跑 00a_fetch_stats_gov_cn_local.py 回传",
        ],
    }
    args.meta.parent.mkdir(parents=True, exist_ok=True)
    args.meta.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
    logging.info("metadata 写入 %s", args.meta)

    print()
    print("=== 完整性 ===")
    for k, v in completeness.items():
        bar = "█" * (v * 20 // len(df))
        print(f"  {k:20s} {v:4d}/{len(df)}  {bar}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
