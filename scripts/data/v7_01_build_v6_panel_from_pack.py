#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""从本机分卷包重建 v6 县级基础面板（v7 链路的第一步）。

背景
====
``scripts/build_v6_panel.py`` 假设两个源 Excel 已解压到
``data/raw/statistical_yearbook/【25170】中国县域统计年鉴2000-2024/``，但该目录
不在仓库里（``.gitignore`` 忽略），因此 v6/v7 面板此前无法在仓内复现。
两个源文件其实就在 ``data/raw/statistical_yearbook_chunks/`` 的 24 个分卷里，
本脚本按 **文件大小** 定位成员（包内中文名编码不可靠），取出后按
``build_v6_panel.py`` 的口径重建面板。

口径（与 build_v6_panel.py 一致）
=================================
- 源 A：``区县面板数据2000-2024.xlsx``（73 912 884 B）→ 粮食总产量 + 农业统计列
- 源 B：``…/02.面板数据/【出版年份2001-2023】中国县域面板数据.xlsx``（73 186 343 B）→ 经纬度
- 窗口：10 个粮食主产省 × 2012–2023

用法
====
    python scripts/data/v7_01_build_v6_panel_from_pack.py
    python scripts/data/v7_01_build_v6_panel_from_pack.py --work-dir D:\\DC\\_scan\\yb_extract
"""

from __future__ import annotations

import argparse
import importlib.util
import math
import sys
from pathlib import Path

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[2]
CHUNKS_DIR = PROJECT_ROOT / "data" / "raw" / "statistical_yearbook_chunks"
OUT_DIR = PROJECT_ROOT / "data" / "interim"

SIZE_A = 73_912_884   # 区县面板数据2000-2024.xlsx
SIZE_B = 73_186_343   # 【出版年份2001-2023】中国县域面板数据.xlsx

TEN = ["河北省", "吉林省", "黑龙江省", "江苏省", "安徽省",
       "山东省", "河南省", "湖北省", "湖南省", "四川省"]
YEARS = list(range(2012, 2024))

Y = "粮食总产量_吨"
STAT_COLS = [
    "农作物总播种面积_千公顷", "常用耕地面积_公顷", "机收面积_公顷", "设施农业占地面积_公顷",
    "农用机械总动力_千万瓦", "农林牧渔业总产值_万元", "农业增加值_万元", "第一产业增加值_万元",
    "乡村人口_万人", "乡村从业人员数_人", "农林牧渔业从业人员数_人",
]
ID_COLS = ["区县代码", "省份", "城市", "区县", "年份"]


def load_yb09():
    path = PROJECT_ROOT / "scripts" / "data" / "09_extract_yearbook_county_panel.py"
    spec = importlib.util.spec_from_file_location("yb09", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def extract_sources(work_dir: Path) -> tuple[Path, Path]:
    work_dir.mkdir(parents=True, exist_ok=True)
    out_a = work_dir / "yuexian_panel_2000_2024.xlsx"
    out_b = work_dir / "xianyu_panel_2001_2023.xlsx"
    if out_a.exists() and out_b.exists():
        print(f"复用已取出的源文件：{work_dir}")
        return out_a, out_b

    yb09 = load_yb09()
    with yb09.open_archive(CHUNKS_DIR) as zf:
        for size, out in ((SIZE_A, out_a), (SIZE_B, out_b)):
            if out.exists():
                continue
            member = yb09.find_member(zf, size)
            print(f"解出 {member.filename} -> {out.name}")
            with zf.open(member) as src, out.open("wb") as dst:
                while chunk := src.read(1 << 20):
                    dst.write(chunk)
    return out_a, out_b


def build(xlsx: Path, sheet: str) -> pd.DataFrame:
    df = pd.read_excel(xlsx, sheet_name=sheet)
    df = df[df["省份"].isin(TEN) & df["年份"].isin(YEARS)]
    df = df[ID_COLS + [Y] + STAT_COLS].copy()
    logy = pd.to_numeric(df[Y], errors="coerce")
    df["log_yield"] = logy.where(logy > 0).map(lambda v: pd.NA if pd.isna(v) else math.log(v))
    return df


def attach_lonlat(df: pd.DataFrame, xlsx_b: Path) -> pd.DataFrame:
    b = pd.read_excel(xlsx_b, sheet_name="原始数据", usecols=["行政区划代码", "经度", "纬度"])
    b = b.drop_duplicates("行政区划代码")
    return df.merge(
        b.rename(columns={"行政区划代码": "区县代码", "经度": "lon", "纬度": "lat"}),
        on="区县代码", how="left",
    )


def report(df: pd.DataFrame, tag: str, out: Path) -> None:
    print(f"[{tag}] {df.shape}  (10省 {df['区县代码'].nunique()} 县 × {df['年份'].nunique()} 年)")
    print(f"  分年县数: {df.groupby('年份')['区县代码'].nunique().to_dict()}")
    print(f"  粮食总产量非空率: {df[Y].notna().mean():.1%}  log_yield 非空率: {df['log_yield'].notna().mean():.1%}")
    print(f"  经纬度非空率: {df['lon'].notna().mean():.1%}")
    for col in STAT_COLS:
        print(f"  {col}: 非空 {df[col].notna().mean():.1%}")
    df.to_parquet(out, index=False)
    print(f"  saved -> {out.relative_to(PROJECT_ROOT)}\n")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--work-dir", type=Path, default=Path(r"D:\DC\_scan\yb_extract"))
    args = ap.parse_args()

    xlsx_a, xlsx_b = extract_sources(args.work_dir)
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    print("=== building raw ===")
    raw = attach_lonlat(build(xlsx_a, "原始数据"), xlsx_b)
    report(raw, "raw", OUT_DIR / "paper_panel_v6.parquet")

    print("=== building filled (线性插值) ===")
    filled = attach_lonlat(build(xlsx_a, "线性插值"), xlsx_b)
    report(filled, "filled", OUT_DIR / "paper_panel_v6_filled.parquet")


if __name__ == "__main__":
    main()
