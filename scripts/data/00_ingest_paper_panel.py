"""转换王天硕原版论文 panel xlsx → data/interim/paper_panel_raw.parquet。

输入：data/raw/paper_panel/wang_tianshuo_original/总表.xlsx
        Sheet1: 31 省 × 13 年 (2011-2023) = 403 行
        列：省份 | 年份 | 粮食单产风险Y | 平均气温 | 干旱指数 | 洪涝占比 |
            灌溉率 | 农机 | 旱灾受灾面积 | 化肥施用量 | 水灾受灾面积 | 降水量 | 日照时数

输出：data/interim/paper_panel_raw.parquet
       schema 对齐 docs/08 §11.3 / backend/services/inference.py（11 维特征 + Y）

列映射（论文版 → 项目 schema）：
    省份                  → province           (短名 → 全称，例 "北京" → "北京市")
    年份                  → year               int
    粮食单产风险Y          → y                  Y target（已去趋势）
    平均气温              → temp               °C
    干旱指数              → spei               SPEI
    洪涝占比              → flood              %
    灌溉率                → irr                %
    农机                  → mech               万千瓦
    旱灾受灾面积           → drou_a             千公顷
    化肥施用量             → fert               万吨
    水灾受灾面积           → flood_a            千公顷
    降水量                → prec               mm
    日照时数              → sun                小时/年
    (待 MODIS 聚合后合并)  → ndvi               z-score

CLI:
    python scripts/data/00_ingest_paper_panel.py
"""
from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_SRC = PROJECT_ROOT / "data" / "raw" / "paper_panel" / "wang_tianshuo_original" / "总表.xlsx"
DEFAULT_OUT = PROJECT_ROOT / "data" / "interim" / "paper_panel_raw.parquet"

# 列名映射（论文版 → 项目 schema）
COLUMN_MAP = {
    "省份": "province_short",  # 临时保留，下一步映射全称
    "年份": "year",
    "粮食单产风险Y": "y",
    "平均气温": "temp",
    "干旱指数": "spei",
    "洪涝占比": "flood",
    "灌溉率": "irr",
    "农机": "mech",
    "旱灾受灾面积": "drou_a",
    "化肥施用量": "fert",
    "水灾受灾面积": "flood_a",
    "降水量": "prec",
    "日照时数": "sun",
}

# 31 省：短名 → 6 位 province_code + 全称
PROVINCE_INFO: list[tuple[str, str, str]] = [
    ("北京",   "110000", "北京市"),
    ("天津",   "120000", "天津市"),
    ("河北",   "130000", "河北省"),
    ("山西",   "140000", "山西省"),
    ("内蒙古", "150000", "内蒙古自治区"),
    ("辽宁",   "210000", "辽宁省"),
    ("吉林",   "220000", "吉林省"),
    ("黑龙江", "230000", "黑龙江省"),
    ("上海",   "310000", "上海市"),
    ("江苏",   "320000", "江苏省"),
    ("浙江",   "330000", "浙江省"),
    ("安徽",   "340000", "安徽省"),
    ("福建",   "350000", "福建省"),
    ("江西",   "360000", "江西省"),
    ("山东",   "370000", "山东省"),
    ("河南",   "410000", "河南省"),
    ("湖北",   "420000", "湖北省"),
    ("湖南",   "430000", "湖南省"),
    ("广东",   "440000", "广东省"),
    ("广西",   "450000", "广西壮族自治区"),
    ("海南",   "460000", "海南省"),
    ("重庆",   "500000", "重庆市"),
    ("四川",   "510000", "四川省"),
    ("贵州",   "520000", "贵州省"),
    ("云南",   "530000", "云南省"),
    ("西藏",   "540000", "西藏自治区"),
    ("陕西",   "610000", "陕西省"),
    ("甘肃",   "620000", "甘肃省"),
    ("青海",   "630000", "青海省"),
    ("宁夏",   "640000", "宁夏回族自治区"),
    ("新疆",   "650000", "新疆维吾尔自治区"),
]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="论文已有面板 xlsx → parquet (任务 1.2)")
    parser.add_argument("--src", type=Path, default=DEFAULT_SRC)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--verbose", "-v", action="store_true")
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
        datefmt="%H:%M:%S",
    )

    if not args.src.exists():
        logging.error("找不到源文件 %s", args.src)
        return 1

    df = pd.read_excel(args.src, sheet_name="Sheet1")
    logging.info("读 %s: %d 行 × %d 列", args.src.name, len(df), len(df.columns))

    missing = [c for c in COLUMN_MAP if c not in df.columns]
    if missing:
        logging.error("缺列：%s（实际列：%s）", missing, list(df.columns))
        return 1

    df = df.rename(columns=COLUMN_MAP)
    df["year"] = df["year"].astype(int)

    # 短名 → 全称 + province_code
    short_to_code = {short: code for short, code, _ in PROVINCE_INFO}
    short_to_full = {short: full for short, _, full in PROVINCE_INFO}

    unknown_provinces = sorted(set(df["province_short"]) - set(short_to_code))
    if unknown_provinces:
        logging.error("未知省份名（不在 31 省映射表）：%s", unknown_provinces)
        return 1

    df["province_code"] = df["province_short"].map(short_to_code)
    df["province"] = df["province_short"].map(short_to_full)
    df = df.drop(columns=["province_short"])

    # 重排列：与 doc 08 / inference.py 对齐
    schema_order = [
        "province_code", "province", "year",
        "y",
        "irr", "flood", "sun", "temp", "spei", "prec",
        "mech", "fert", "drou_a", "flood_a",
    ]
    final = df[schema_order].sort_values(["province_code", "year"]).reset_index(drop=True)

    args.out.parent.mkdir(parents=True, exist_ok=True)
    final.to_parquet(args.out, index=False)
    logging.info("✅ 写入 %s（%d 行 × %d 列）", args.out, len(final), len(final.columns))

    # 输出关键 sanity check
    print()
    print("=== 完整性 ===")
    for col in final.columns:
        non_null = final[col].notna().sum()
        print(f"  {col:15s} {non_null:4d}/{len(final)}")

    print()
    print("=== 河南 2022 ===")
    h = final[(final["province"] == "河南省") & (final["year"] == 2022)]
    print(h.to_string(index=False))

    print()
    print(f"⚠️  NDVI 列待 MODIS pipeline 完成后合并（scripts/data/00z_merge_panel.py）")
    print(f"⚠️  熊鑫已可在此面板上用 10 维 X 跑 XGBoost-SHAP / LSTM 基线")
    return 0


if __name__ == "__main__":
    sys.exit(main())
