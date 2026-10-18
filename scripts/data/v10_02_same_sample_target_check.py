#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""v10 Step 2：单产 vs 总产的同样本对照。

为什么必须做
============
v10_01 里单产 R² 更高，但单产样本只有 4,693 行 / 627 县，总产样本是
10,407 行 / 1,041 县。两组不是同一批县年，单产更高可能只是样本更容易。

本脚本把两个目标限制在**同一批县年**（同时有总产、单产、16 维气候），
再跑同样的 LCO + 时间外推。只有同样本下单产仍更高，才能把「换目标」
写成方法改进。

输出
====
reports/v10_02_same_sample_target_check_results.csv
reports/v10_02_same_sample_target_check_summary.md
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import xgboost as xgb
from sklearn.metrics import mean_squared_error, r2_score
from sklearn.model_selection import KFold

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

PROJECT_ROOT = Path(__file__).resolve().parents[2]
PANEL = PROJECT_ROOT / "data" / "interim" / "paper_panel_v7_prediction.parquet"
OUT_CSV = PROJECT_ROOT / "reports" / "v10_02_same_sample_target_check_results.csv"
OUT_MD = PROJECT_ROOT / "reports" / "v10_02_same_sample_target_check_summary.md"

SEEDS = [42, 43, 44, 45, 46]
TIME_SPLIT = 2019

XGB_PARAMS = {
    "n_estimators": 300, "max_depth": 5, "learning_rate": 0.05,
    "subsample": 0.8, "colsample_bytree": 0.8,
    "reg_alpha": 0.1, "reg_lambda": 1.0,
    "n_jobs": -1,
}

FEATURES = [
    "temp", "prec", "sun",
    "spei_annual_mean", "spei_growing_season_mean",
    "gs_tmax_mean", "gs_tmin_mean", "gs_ppt", "gs_srad", "gs_pet",
    "gdd10", "gs_aridity", "prec_cv", "gs_prec_share",
    "winter_temp", "seasonal_temp_range",
]


def _metrics(X, y, groups, years, seed):
    params = {**XGB_PARAMS, "random_state": seed}
    counties = np.unique(groups)
    kf = KFold(n_splits=min(10, len(counties)), shuffle=True, random_state=seed)
    preds, trues = [], []
    for tr_i, _ in kf.split(counties):
        tr = np.isin(groups, counties[tr_i])
        model = xgb.XGBRegressor(**params)
        model.fit(X[tr], y[tr])
        preds.append(model.predict(X[~tr]))
        trues.append(y[~tr])
    lco_r2 = r2_score(np.concatenate(trues), np.concatenate(preds))
    lco_rmse = mean_squared_error(np.concatenate(trues), np.concatenate(preds), squared=False)

    tr_t = years <= TIME_SPLIT
    te_t = ~tr_t
    model = xgb.XGBRegressor(**params)
    model.fit(X[tr_t], y[tr_t])
    p = model.predict(X[te_t])
    return {
        "seed": seed,
        "lco_r2": round(float(lco_r2), 4),
        "lco_rmse": round(float(lco_rmse), 4),
        "time_r2": round(float(r2_score(y[te_t], p)), 4),
        "time_rmse": round(float(mean_squared_error(y[te_t], p, squared=False)), 4),
        "n_rows": len(y),
        "n_counties": int(len(counties)),
    }


def main() -> int:
    df = pd.read_parquet(PANEL)
    df["log_single_yield"] = np.where(
        df["yield_ton_per_ha"] > 0,
        np.log(df["yield_ton_per_ha"]),
        np.nan,
    )

    # 同样本：两个目标 + 16 维气候都非空
    base = df.dropna(subset=FEATURES + ["log_yield", "log_single_yield"]).copy()
    print(f"同样本: {len(base)} 行 / {base['区县代码'].nunique()} 县 / {base['年份'].min()}-{base['年份'].max()}")

    rows = []
    for target in ["log_yield", "log_single_yield"]:
        X = base[FEATURES].values.astype(float)
        y = base[target].values.astype(float)
        groups = base["区县代码"].values
        years = base["年份"].values
        print(f"\n===== {target} =====")
        for seed in SEEDS:
            r = _metrics(X, y, groups, years, seed)
            r["target"] = target
            rows.append(r)
            print(f"  seed {seed}: LCO={r['lco_r2']:+.4f}  time={r['time_r2']:+.4f}")

    res = pd.DataFrame(rows)[
        ["target", "seed", "n_rows", "n_counties", "lco_r2", "lco_rmse", "time_r2", "time_rmse"]
    ]
    res.to_csv(OUT_CSV, index=False)

    agg = (res.groupby("target", sort=False)
              .agg(n_rows=("n_rows", "first"), n_counties=("n_counties", "first"),
                   lco_mean=("lco_r2", "mean"), lco_std=("lco_r2", "std"),
                   time_mean=("time_r2", "mean"), time_std=("time_r2", "std"))
              .reset_index())
    agg["lco"] = agg["lco_mean"].map("{:+.4f}".format) + " ± " + agg["lco_std"].map("{:.4f}".format)
    agg["time"] = agg["time_mean"].map("{:+.4f}".format) + " ± " + agg["time_std"].map("{:.4f}".format)

    lines = [
        "# v10-02 单产 vs 总产：同样本对照",
        "",
        f"> 同样本：{len(base)} 行 / {base['区县代码'].nunique()} 县 ｜ 种子 {', '.join(map(str, SEEDS))} ｜ 时间切分 ≤{TIME_SPLIT}",
        "",
        "| 目标 | 行数 | 县数 | LCO R² | 时间外推 R² |",
        "|---|---:|---:|---|---|",
    ]
    for _, r in agg.iterrows():
        lines.append(
            f"| {r['target']} | {r['n_rows']} | {r['n_counties']} | {r['lco']} | {r['time']} |"
        )

    a = agg.set_index("target")
    d_lco = a.loc["log_single_yield", "lco_mean"] - a.loc["log_yield", "lco_mean"]
    d_time = a.loc["log_single_yield", "time_mean"] - a.loc["log_yield", "time_mean"]
    lines += [
        "",
        "## 判断",
        "",
        f"- 同样本下单产 − 总产：LCO **{d_lco:+.4f}**，时间外推 **{d_time:+.4f}**。",
        "- 若两个差值仍为正：目标换单产是真实改进，不是样本选择。",
        "- 若差值接近 0 或转负：v10_01 的差距主要来自样本构成，不能写成「单产更好」。",
        "",
        "## 边界",
        "",
        "- 仍是 4,693 行 / 627 县的有单产子样本；结论只在这个样本内成立。",
        "- 两个目标的方差不同，R² 不是同一把尺子的绝对精度；这里比较的是同一批县年上的相对迁移能力。",
        "",
        "> 复现：`python scripts/data/v10_02_same_sample_target_check.py`",
        "",
    ]
    OUT_MD.write_text("\n".join(lines), encoding="utf-8")
    print(f"\n✅ {OUT_CSV}")
    print(f"✅ {OUT_MD}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
