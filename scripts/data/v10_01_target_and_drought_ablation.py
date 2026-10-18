#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""v10 Step 1：目标口径 + 干旱分辨率消融。

两个问题
========
1. 0.5° SPEI 是否比 4.6 km TerraClimate 干旱特征多提供信息？
   - CLIMG16：当前 16 维（含 SPEI ×2）
   - CLIMG14：去掉两个 SPEI，只保留 TerraClimate 4.6 km 派生特征
   若两者 LCO / 时间外推接近，说明粗格网 SPEI 可以撤掉，县级分辨率更干净。

2. 把目标从「县级总产量」换成「县级单产」后，气候信号是否更稳？
   - log_yield        = log(粮食总产量/吨)     （规模主导，N=10,407）
   - log_single_yield = log(单产 t/ha)         （剥离面积，N≈4,703）

协议
====
LCO：10 折按县分组（未见县）
时间外推：≤2019 → 2020-2022（未见年）
种子：42–46
模型：与 v6_12 完全一致的 XGBoost 参数

输出
====
reports/v10_01_target_and_drought_ablation_results.csv
reports/v10_01_target_and_drought_ablation_summary.md
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
OUT_CSV = PROJECT_ROOT / "reports" / "v10_01_target_and_drought_ablation_results.csv"
OUT_MD = PROJECT_ROOT / "reports" / "v10_01_target_and_drought_ablation_summary.md"

SEEDS = [42, 43, 44, 45, 46]
TIME_SPLIT = 2019

XGB_PARAMS = {
    "n_estimators": 300, "max_depth": 5, "learning_rate": 0.05,
    "subsample": 0.8, "colsample_bytree": 0.8,
    "reg_alpha": 0.1, "reg_lambda": 1.0,
    "n_jobs": -1,
}

CLIM3 = ["temp", "prec", "sun"]
SPEI = ["spei_annual_mean", "spei_growing_season_mean"]
SEASONAL = [
    "gs_tmax_mean", "gs_tmin_mean", "gs_ppt", "gs_srad", "gs_pet",
    "gdd10", "gs_aridity", "prec_cv", "gs_prec_share",
    "winter_temp", "seasonal_temp_range",
]

FEATURE_SETS = {
    "CLIMG16": CLIM3 + SPEI + SEASONAL,
    "CLIMG14_NOSPEI": CLIM3 + SEASONAL,
}

TARGETS = {
    "total_output": "log_yield",
    "single_yield": "log_single_yield",
}


def _lco(X: np.ndarray, y: np.ndarray, groups: np.ndarray, params: dict) -> tuple[float, float]:
    counties = np.unique(groups)
    n_splits = min(10, len(counties))
    kf = KFold(n_splits=n_splits, shuffle=True, random_state=params["random_state"])
    preds, trues = [], []
    for tr_i, te_i in kf.split(counties):
        tr_mask = np.isin(groups, counties[tr_i])
        te_mask = ~tr_mask
        model = xgb.XGBRegressor(**params)
        model.fit(X[tr_mask], y[tr_mask])
        preds.append(model.predict(X[te_mask]))
        trues.append(y[te_mask])
    return (
        float(r2_score(np.concatenate(trues), np.concatenate(preds))),
        float(mean_squared_error(np.concatenate(trues), np.concatenate(preds), squared=False)),
    )


def _time(X: np.ndarray, y: np.ndarray, years: np.ndarray, params: dict) -> tuple[float, float]:
    tr = years <= TIME_SPLIT
    te = ~tr
    model = xgb.XGBRegressor(**params)
    model.fit(X[tr], y[tr])
    p = model.predict(X[te])
    return (
        float(r2_score(y[te], p)),
        float(mean_squared_error(y[te], p, squared=False)),
    )


def main() -> int:
    df = pd.read_parquet(PANEL)
    df["log_single_yield"] = np.where(
        df["yield_ton_per_ha"] > 0,
        np.log(df["yield_ton_per_ha"]),
        np.nan,
    )

    rows = []
    for target_name, target_col in TARGETS.items():
        for cfg_name, feats in FEATURE_SETS.items():
            ok = [f for f in feats if f in df.columns]
            if len(ok) != len(feats):
                raise SystemExit(f"[FATAL] {cfg_name} 缺列: {set(feats) - set(ok)}")

            sub = df.dropna(subset=ok + [target_col]).copy()
            X = sub[ok].values.astype(float)
            y = sub[target_col].values.astype(float)
            groups = sub["区县代码"].values
            years = sub["年份"].values
            print(f"\n===== {target_name} | {cfg_name} | {len(ok)} 特征 | {len(sub)} 行 | {len(np.unique(groups))} 县 =====")

            for seed in SEEDS:
                params = {**XGB_PARAMS, "random_state": seed}
                lco_r2, lco_rmse = _lco(X, y, groups, params)
                time_r2, time_rmse = _time(X, y, years, params)
                rows.append({
                    "target": target_name,
                    "config": cfg_name,
                    "n_feat": len(ok),
                    "seed": seed,
                    "n_rows": len(sub),
                    "n_counties": int(len(np.unique(groups))),
                    "lco_r2": round(lco_r2, 4),
                    "lco_rmse": round(lco_rmse, 4),
                    "time_r2": round(time_r2, 4),
                    "time_rmse": round(time_rmse, 4),
                })
                print(f"  seed {seed}: LCO={lco_r2:+.4f}  time={time_r2:+.4f}")

    res = pd.DataFrame(rows)
    OUT_CSV.parent.mkdir(parents=True, exist_ok=True)
    res.to_csv(OUT_CSV, index=False)

    agg = (res.groupby(["target", "config"], sort=False)
              .agg(n_feat=("n_feat", "first"),
                   n_rows=("n_rows", "first"),
                   n_counties=("n_counties", "first"),
                   lco_mean=("lco_r2", "mean"), lco_std=("lco_r2", "std"),
                   time_mean=("time_r2", "mean"), time_std=("time_r2", "std"))
              .reset_index())
    agg["lco"] = agg["lco_mean"].map("{:+.4f}".format) + " ± " + agg["lco_std"].map("{:.4f}".format)
    agg["time"] = agg["time_mean"].map("{:+.4f}".format) + " ± " + agg["time_std"].map("{:.4f}".format)

    lines = [
        "# v10-01 目标口径 + 干旱分辨率消融",
        "",
        f"> 数据：`{PANEL.name}` ｜ 种子：{', '.join(map(str, SEEDS))} ｜ 时间切分：≤{TIME_SPLIT} → 之后",
        "",
        "## 结果（mean ± std，5 种子）",
        "",
        "| 目标 | 配置 | 特征数 | 行数 | 县数 | LCO R² | 时间外推 R² |",
        "|---|---|---:|---:|---:|---|---|",
    ]
    for _, r in agg.iterrows():
        lines.append(
            f"| {r['target']} | {r['config']} | {r['n_feat']} | {r['n_rows']} | "
            f"{r['n_counties']} | {r['lco']} | {r['time']} |"
        )

    lines += ["", "## 直接对比", ""]
    for target in TARGETS:
        sub = agg[agg["target"] == target].set_index("config")
        if {"CLIMG16", "CLIMG14_NOSPEI"}.issubset(sub.index):
            d_lco = sub.loc["CLIMG14_NOSPEI", "lco_mean"] - sub.loc["CLIMG16", "lco_mean"]
            d_time = sub.loc["CLIMG14_NOSPEI", "time_mean"] - sub.loc["CLIMG16", "time_mean"]
            lines.append(
                f"- **{target}**：去掉两个 0.5° SPEI 后，"
                f"LCO Δ={d_lco:+.4f}，时间外推 Δ={d_time:+.4f}。"
            )

    lines += [
        "",
        "## 判读规则",
        "",
        "- 若 `CLIMG14_NOSPEI` 与 `CLIMG16` 的 LCO/时间外推差都在 ±0.01 内：0.5° SPEI 冗余，"
        "县级主模型可以只用 TerraClimate 4.6 km 特征，分辨率口径更干净。",
        "- 若 `CLIMG16` 明显更高：SPEI 的多年干旱记忆有独立信息，不能简单撤掉，"
        "下一步应换成 4.6 km 的滚动水分亏缺（3/6/12 个月）再做对照。",
        "- 若 `single_yield` 的 LCO 高于 `total_output`：说明剥离播种面积后气候信号更干净，"
        "应把单产作为论文主口径；若样本量导致时间外推不稳，则单产只报 LCO，时间外推继续用总产口径。",
        "",
        "## 边界",
        "",
        "- `single_yield` 只有 4,703 行，县数与年份覆盖小于总产口径；不能把两个 R² 直接当同一精度比较。",
        "- `CLIMG14_NOSPEI` 仍是年度/生长季聚合，不是日尺度极端指数；它只回答「粗格网 SPEI 是否必要」。",
        "",
        f"> 复现：`python scripts/data/v10_01_target_and_drought_ablation.py`",
        "",
    ]
    OUT_MD.write_text("\n".join(lines), encoding="utf-8")
    print(f"\n✅ {OUT_CSV}")
    print(f"✅ {OUT_MD}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
