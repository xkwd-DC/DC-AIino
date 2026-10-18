#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""v10 Step 4：日值极端指数是否给县级单产模型加分。

输入
====
- data/interim/paper_panel_v7_prediction.parquet（14,388 行）
- data/interim/openmeteo_county_daily_extremes.parquet（1,196 县 × 12 年）

对照
====
- CLIMG16：现有 16 维气候特征
- CLIMG16 + OM_ALL：加 Open-Meteo 全部 12 个日值极端指数
- CLIMG16 + OM_CORE：只加 7 个核心指数（TX35、Tmax 极值、Tmin 极值、CDD、暴雨日、R95p、GDD10）

目标
====
- 主口径：log_single_yield（单产）
- 对照：log_yield（总产）

协议
====
LCO 10 折按县分组 + 时间外推 ≤2019 → 2020–2022；种子 42–46。
所有配置都限制在**同样本**（单产 + 全部特征非空），避免样本选择。
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

ROOT = Path(__file__).resolve().parents[2]
PANEL = ROOT / "data" / "interim" / "paper_panel_v7_prediction.parquet"
OM = ROOT / "data" / "interim" / "nasapower_county_daily_extremes.parquet"
OUT_CSV = ROOT / "reports" / "v10_04_daily_extremes_ablation_results.csv"
OUT_MD = ROOT / "reports" / "v10_04_daily_extremes_ablation_summary.md"

SEEDS = [42, 43, 44, 45, 46]
TIME_SPLIT = 2019

XGB_PARAMS = {
    "n_estimators": 300, "max_depth": 5, "learning_rate": 0.05,
    "subsample": 0.8, "colsample_bytree": 0.8,
    "reg_alpha": 0.1, "reg_lambda": 1.0,
    "n_jobs": -1,
}

CLIM = [
    "temp", "prec", "sun",
    "spei_annual_mean", "spei_growing_season_mean",
    "gs_tmax_mean", "gs_tmin_mean", "gs_ppt", "gs_srad", "gs_pet",
    "gdd10", "gs_aridity", "prec_cv", "gs_prec_share",
    "winter_temp", "seasonal_temp_range",
]

OM_ALL = [
    "np_tmax_mean_gs", "np_tmax_max_gs", "np_heat_days35",
    "np_tmin_min_gs", "np_frost_days", "np_prec_sum_gs",
    "np_wet_days", "np_rainstorm_days", "np_cdd_max",
    "np_gdd10", "np_prec_p95", "np_r95p_days",
]

OM_CORE = [
    "np_heat_days35", "np_tmax_max_gs", "np_tmin_min_gs",
    "np_cdd_max", "np_rainstorm_days", "np_r95p_days", "np_gdd10",
]

CONFIGS = {
    "CLIMG16": CLIM,
    "CLIMG16+NP_ALL": CLIM + OM_ALL,
    "CLIMG16+NP_CORE": CLIM + OM_CORE,
}


def metrics(X, y, groups, years, seed):
    params = {**XGB_PARAMS, "random_state": seed}
    counties = np.unique(groups)
    kf = KFold(n_splits=min(10, len(counties)), shuffle=True, random_state=seed)
    preds, trues = [], []
    for tr_i, _ in kf.split(counties):
        tr = np.isin(groups, counties[tr_i])
        m = xgb.XGBRegressor(**params)
        m.fit(X[tr], y[tr])
        preds.append(m.predict(X[~tr]))
        trues.append(y[~tr])
    lco = r2_score(np.concatenate(trues), np.concatenate(preds))
    lco_rmse = mean_squared_error(np.concatenate(trues), np.concatenate(preds), squared=False)

    tr_t = years <= TIME_SPLIT
    te_t = ~tr_t
    m = xgb.XGBRegressor(**params)
    m.fit(X[tr_t], y[tr_t])
    p = m.predict(X[te_t])
    return {
        "seed": seed,
        "lco_r2": round(float(lco), 4),
        "lco_rmse": round(float(lco_rmse), 4),
        "time_r2": round(float(r2_score(y[te_t], p)), 4),
        "time_rmse": round(float(mean_squared_error(y[te_t], p, squared=False)), 4),
    }


def main() -> int:
    panel = pd.read_parquet(PANEL).rename(columns={"区县代码": "county_code", "年份": "year"})
    om = pd.read_parquet(OM)
    df = panel.merge(om, on=["county_code", "year"], how="left", validate="one_to_one")
    df["log_single_yield"] = np.where(df["yield_ton_per_ha"] > 0, np.log(df["yield_ton_per_ha"]), np.nan)
    print(f"panel {len(panel)} + NP {len(om)} -> {len(df)} 行；NP 覆盖 {df['np_heat_days35'].notna().sum()} 行")

    rows = []
    sample_info = {}
    for target in ["log_single_yield", "log_yield"]:
        for cfg, feats in CONFIGS.items():
            sub = df.dropna(subset=feats + [target]).copy()
            key = (target, cfg)
            sample_info[key] = (len(sub), sub["county_code"].nunique())
            print(f"\n===== {target} | {cfg} | {len(feats)} 特征 | {len(sub)} 行 | {sub['county_code'].nunique()} 县 =====")
            if len(sub) < 200:
                print("  样本过少，跳过")
                continue
            X = sub[feats].values.astype(float)
            y = sub[target].values.astype(float)
            groups = sub["county_code"].values
            years = sub["year"].values
            for seed in SEEDS:
                r = metrics(X, y, groups, years, seed)
                r.update({"target": target, "config": cfg, "n_feat": len(feats), "n_rows": len(sub), "n_counties": int(sub["county_code"].nunique())})
                rows.append(r)
                print(f"  seed {seed}: LCO={r['lco_r2']:+.4f}  time={r['time_r2']:+.4f}")

    res = pd.DataFrame(rows)[[
        "target", "config", "n_feat", "seed", "n_rows", "n_counties",
        "lco_r2", "lco_rmse", "time_r2", "time_rmse",
    ]]
    res.to_csv(OUT_CSV, index=False)

    agg = (res.groupby(["target", "config"], sort=False)
              .agg(n_feat=("n_feat", "first"), n_rows=("n_rows", "first"), n_counties=("n_counties", "first"),
                   lco=("lco_r2", "mean"), lco_sd=("lco_r2", "std"),
                   time=("time_r2", "mean"), time_sd=("time_r2", "std"))
              .reset_index())
    agg["lco_s"] = agg["lco"].map("{:+.4f}".format) + " ± " + agg["lco_sd"].map("{:.4f}".format)
    agg["time_s"] = agg["time"].map("{:+.4f}".format) + " ± " + agg["time_sd"].map("{:.4f}".format)

    lines = [
        "# v10-04 日值极端指数消融",
        "",
        f"> 数据：`{PANEL.name}` + `{OM.name}` ｜ 种子 {', '.join(map(str, SEEDS))} ｜ 时间切分 ≤{TIME_SPLIT}",
        "",
        "| 目标 | 配置 | 特征数 | 行数 | 县数 | LCO R² | 时间外推 R² |",
        "|---|---|---:|---:|---:|---|---|",
    ]
    for _, r in agg.iterrows():
        lines.append(f"| {r['target']} | {r['config']} | {r['n_feat']} | {r['n_rows']} | {r['n_counties']} | {r['lco_s']} | {r['time_s']} |")

    lines += ["", "## 相对 CLIMG16 的增益", ""]
    for target in ["log_single_yield", "log_yield"]:
        sub = agg[agg["target"] == target].set_index("config")
        if "CLIMG16" not in sub.index:
            continue
        for cfg in ["CLIMG16+NP_ALL", "CLIMG16+NP_CORE"]:
            if cfg in sub.index:
                dl = sub.loc[cfg, "lco"] - sub.loc["CLIMG16", "lco"]
                dt = sub.loc[cfg, "time"] - sub.loc["CLIMG16", "time"]
                lines.append(f"- **{target} / {cfg}**：LCO Δ={dl:+.4f}，时间外推 Δ={dt:+.4f}")

    lines += [
        "",
        "## 判读",
        "",
        "- 若 OM 增益 ≥ +0.02 且方向稳定：日值极端值得进主模型，下一步做 4.6 km 网格版或固定阈值 R95p。",
        "- 若增益在 ±0.01 内：日值极端对当前目标没有额外信息，问题更可能在目标/样本，而不是数据频率。",
        "- 若增益为负：日值极端与现有 `gs_tmax/gs_aridity` 高度共线，先做相关性/消融，不要硬堆。",
        "",
        "## 边界",
        "",
        "- NASA POWER 是 0.5° 再分析/卫星融合，县治点最近格点，不是台站观测。",
        "- `np_prec_p95` 是年内湿日 95 分位；跨年比较时更稳的做法是用 2012–2023 固定阈值重算 R95p。",
        "- 所有配置都限制在同样本，但 NP 覆盖少的县会被丢掉；看 `n_rows` / `n_counties` 列。",
        "",
        "> 复现：`python scripts/data/v10_04_daily_extremes_ablation.py`",
        "",
    ]
    OUT_MD.write_text("\n".join(lines), encoding="utf-8")
    print(f"\n✅ {OUT_CSV}\n✅ {OUT_MD}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
