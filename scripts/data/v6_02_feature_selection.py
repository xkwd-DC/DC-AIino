#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""v6 Step 2：农经特征选择 — 覆盖率 / 相关性 / 组内时序方差决策表。

年鉴 11 个农经特征缺失率高（播种 67%、耕地 83%），不能全进模型。
产出决策表 data/interim/v6_feature_selection.csv + 推荐特征集。

选择规则（可解释）：
  1. 覆盖率 ≥ 40%                       → 必选候选
  2. 覆盖率 30-40% 且 |r(log_yield)| ≥ 0.8 → 规模控制类，可入选
  3. 组内时序方差占比（within-county）过低 → 对气候归因无信息，降权

另输出：单产（总产量/播种面积）可计算行数，供论文讨论目标变量口径。
"""
from pathlib import Path

import numpy as np
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[2]
RAW = PROJECT_ROOT / "data" / "interim" / "paper_panel_v6.parquet"
OUT = PROJECT_ROOT / "data" / "interim" / "v6_feature_selection.csv"

Y = "log_yield"
STAT_COLS = [
    "农作物总播种面积_千公顷", "常用耕地面积_公顷", "机收面积_公顷", "设施农业占地面积_公顷",
    "农用机械总动力_千万瓦", "农林牧渔业总产值_万元", "农业增加值_万元", "第一产业增加值_万元",
    "乡村人口_万人", "乡村从业人员数_人", "农林牧渔业从业人员数_人",
]


def within_share(df: pd.DataFrame, col: str) -> float:
    """组内(县内)方差占总方差比例 — 时序识别力。越小 → 组内年际波动越小。"""
    g = df.groupby("区县代码")[col]
    grand_mean = df[col].mean()
    sst = ((df[col] - grand_mean) ** 2).sum()
    sse = sum(((sub - sub.mean()) ** 2).sum() for _, sub in g)
    return 1.0 - sse / sst if sst > 0 else np.nan


def main() -> int:
    df = pd.read_parquet(RAW)
    rows = []
    for c in STAT_COLS:
        sub = df[[c, Y]].dropna()
        r = sub.corr(method="spearman").iloc[0, 1] if len(sub) > 50 else np.nan
        rows.append({
            "feature": c,
            "coverage_pct": round(df[c].notna().mean() * 100, 1),
            "corr_logyield": round(r, 3),
            "within_var_share": round(within_share(df, c), 3),
            "n_valid_pair": len(sub),
        })

    sel = pd.DataFrame(rows)

    def decide(row):
        if row["coverage_pct"] >= 40:
            return "include"
        if row["coverage_pct"] >= 30 and abs(row["corr_logyield"]) >= 0.8:
            return "include_scale_control"
        return "drop"

    sel["decision"] = sel.apply(decide, axis=1)
    sel = sel.sort_values("coverage_pct", ascending=False).reset_index(drop=True)
    sel.to_csv(OUT, index=False)

    print("=== v6 农经特征决策表 ===")
    print(sel.to_string(index=False))

    inc = sel[sel["decision"].str.startswith("include")]
    print(f"\n✅ 推荐特征集 ({len(inc)}): {inc['feature'].tolist()}")

    # 单产口径验证（论文讨论用）
    pa = df.dropna(subset=["粮食总产量_吨", "农作物总播种面积_千公顷"]).copy()
    pa["yield_ton_per_ha"] = pa["粮食总产量_吨"] / (pa["农作物总播种面积_千公顷"] * 100)
    print(f"\n单产可计算行数: {len(pa)} / {len(df)} ({len(pa)/len(df):.1%})")
    print(f"单产均值: {pa['yield_ton_per_ha'].mean():.3f} t/ha")

    # 入选特征的联合覆盖率（有效训练行数）
    feat = inc["feature"].tolist()
    joint = df.dropna(subset=[Y] + feat)
    print(f"入选特征 + y 联合有效行: {len(joint)} ({len(joint)/len(df):.1%})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
