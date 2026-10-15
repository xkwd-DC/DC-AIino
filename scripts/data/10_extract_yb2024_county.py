#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""提取《中国县域统计年鉴 2024（县市卷）》合表，并与县级面板做名称匹配。

背景
====
原计划用 2024 卷补 2023 年的县级「粮食总产量 / 播种面积」。实测结论：
2024 卷合表不含这两项，且 2018 卷起县市卷整册都不再收录粮食产量与播种面积
（2000-2017 卷有，2018-2024 卷无）。因此本脚本的定位改为：

1. 取出 2024 卷合表里确实存在的 2023 年指标（23 项：地区生产总值、
   第一产业增加值、户籍人口、设施农业占地面积、油料产量、棉花产量等）；
2. 建立「年鉴县名 <-> 区县代码」的对照桥，供 2025 卷与省级年鉴补录复用。

合表结构
========
宽表：指标在行、县在列。首列「指标」、次列「单位」，第 3 列起为县名（2,093 个）。
表内没有区县代码，也没有省份列，只能靠县名匹配。

产出
====
data/interim/county_2023_from_yb2024.csv
    2,093 行 x 23 指标（县-指标宽表，保留合表列序）
data/interim/county_2023_yb2024_match.csv
    面板 1,199 个县（区县代码为键）的匹配结果，含 match_status

用法
====
    python scripts/data/10_extract_yb2024_county.py
"""

from __future__ import annotations

import json
import re
import zipfile
from io import BytesIO
from pathlib import Path

import numpy as np
import openpyxl
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[2]
YB_ROOT = PROJECT_ROOT / "data" / "raw" / "statistical_yearbook"
INTERIM = PROJECT_ROOT / "data" / "interim"

# 2024 县市卷合表成员的字节数；包内中文名被错标为 UTF-8，故按大小定位
COUNTY_TABLE_SIZE = 372_711
PANEL_IN = INTERIM / "paper_panel_v7_prediction.parquet"
OUT_TIDY = INTERIM / "county_2023_from_yb2024.csv"
OUT_MATCH = INTERIM / "county_2023_yb2024_match.csv"
OUT_STATS = INTERIM / "county_2023_yb2024_match_stats.json"


def find_yearbook_zip() -> Path:
    """定位含 2024 县市卷合表的 zip。"""
    cands = [p for p in YB_ROOT.rglob("*.zip") if "2024" in p.name]
    for zp in cands:
        with zipfile.ZipFile(zp) as z:
            if any(i.file_size == COUNTY_TABLE_SIZE for i in z.infolist()):
                return zp
    raise FileNotFoundError("未找到 2024 县市卷合表")


def _to_num(val):
    """数值单元格转 float；空、破折号、文字一律给 None。"""
    if val is None:
        return None
    if isinstance(val, (int, float)):
        return float(val)
    s = str(val).strip().replace(",", "")
    if not s or s in {"-", "—", "…"}:
        return None
    try:
        return float(s)
    except ValueError:
        return None


def parse_county_table(zp: Path) -> pd.DataFrame:
    """把合表解析成 县 x 指标 的宽表。"""
    with zipfile.ZipFile(zp) as z:
        member = next(
            i.filename for i in z.infolist() if i.file_size == COUNTY_TABLE_SIZE
        )
        wb = openpyxl.load_workbook(
            BytesIO(z.read(member)), read_only=True, data_only=True
        )
    ws = wb[wb.sheetnames[0]]
    rows = list(ws.iter_rows(values_only=True))
    names = [str(c).strip() if c is not None else None for c in rows[2][2:]]

    indicators: list[tuple[str, list]] = []
    for row in rows[3:30]:
        filled = sum(1 for c in row if c is not None)
        if filled < 10 or row[0] is None:
            continue  # 分节标题行（仅首列有值）
        indicators.append((str(row[0]).strip(), list(row[2:])))

    records: dict[str, dict] = {}
    order: dict[str, int] = {}
    for j, name in enumerate(names):
        if not name:
            continue
        order[name] = j + 1
        records[name] = {
            label: _to_num(vals[j] if j < len(vals) else None)
            for label, vals in indicators
        }
    tidy = pd.DataFrame.from_dict(records, orient="index")
    tidy.index.name = "县名_年鉴"
    tidy = tidy.reset_index()
    tidy.insert(1, "合表序号", tidy["县名_年鉴"].map(order))
    return tidy


def _norm(name: str) -> str:
    return re.sub(r"[\s\u3000]", "", str(name))


def match_to_panel(tidy: pd.DataFrame) -> tuple[pd.DataFrame, dict]:
    """把合表县名匹配到面板的 1,199 个县。"""
    panel = pd.read_parquet(PANEL_IN)
    keys = panel[["区县代码", "省份", "城市", "区县"]].drop_duplicates()
    keys = keys.sort_values("区县代码").reset_index(drop=True)
    keys = keys.assign(_k=keys["区县"].map(_norm))
    tidy = tidy.assign(_k=tidy["县名_年鉴"].map(_norm))

    panel_dup = keys.loc[keys["_k"].duplicated(keep=False), "_k"].unique().tolist()

    ind_cols = [
        c for c in tidy.columns if c not in ("县名_年鉴", "合表序号", "_k")
    ]
    merged = keys.merge(
        tidy[["_k", "合表序号", *ind_cols]], on="_k", how="left"
    )
    # 合表内县名唯一，故匹配只有「命中/未命中」两态；面板内重名只作提示标记
    merged = merged.assign(
        match_status=np.where(merged["合表序号"].notna(), "matched", "no_match"),
        panel_name_duplicated=merged["_k"].isin(panel_dup),
    ).drop(columns=["_k"])

    un = merged[merged["match_status"] == "no_match"]
    suffix = un["区县"].astype(str).str[-1].value_counts().to_dict()
    merged_old = set(
        ("邯郸县", "邢台县", "任县", "南和县", "宣化县", "芜湖县", "繁昌县")
    )

    stats = {
        "panel_counties": int(len(keys)),
        "yb_counties": int(len(tidy)),
        "matched": int((merged["match_status"] == "matched").sum()),
        "no_match": int((merged["match_status"] == "no_match").sum()),
        "panel_names_duplicated": panel_dup,
        "unmatched_by_last_char": suffix,
        "unmatched_merged_county_hits": sorted(
            set(un["区县"]) & merged_old
        ),
        "panel_unmatched_sample": un["区县"].head(30).tolist(),
    }
    return merged, stats


def main() -> None:
    zp = find_yearbook_zip()
    print("yearbook zip:", zp.name)
    tidy = parse_county_table(zp)
    tidy.to_csv(OUT_TIDY, index=False, encoding="utf-8-sig")
    print(f"写出 {OUT_TIDY.name}: {tidy.shape[0]} 县 x {tidy.shape[1] - 1} 指标")
    print("指标列:", list(tidy.columns[2:]))

    merged, stats = match_to_panel(tidy)
    merged.to_csv(OUT_MATCH, index=False, encoding="utf-8-sig")
    ind_cols = [
        c
        for c in merged.columns
        if c not in ("区县代码", "省份", "城市", "区县", "合表序号", "match_status")
    ]
    ok = merged[merged["match_status"].str.startswith("matched")]
    stats["coverage_after_match"] = {
        c: int(ok[c].notna().sum()) for c in ind_cols
    }
    OUT_STATS.write_text(
        json.dumps(stats, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(f"写出 {OUT_MATCH.name}: {merged.shape}")
    for k, v in stats.items():
        if isinstance(v, list):
            print(f"  {k}: {v[:12]}{' ...' if len(v) > 12 else ''}")
        else:
            print(f"  {k}: {v}")
    print("匹配到县后各指标非空数：")
    print(ok[ind_cols].notna().sum().to_string())


if __name__ == "__main__":
    main()
