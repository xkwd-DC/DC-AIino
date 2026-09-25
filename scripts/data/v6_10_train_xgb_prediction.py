#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""v6 Step 10：XGBoost 产量异常(去县趋势) + 生长季/极端指数 预测对照。

目标变量（2 口径对照）：
  A. log_yield（绝对产量，现状）
  B. y_anom     = log_yield - 该县 OLS 线性趋势残差（产量异常/增减产）

特征（较 v6_04 扩展）：
  基础 14 维：temp/prec/sun/spei_annual/spei_gs/ndvi/ lst_day/fert/irr/flood/drou_a/
              flood_a/cropland_ratio/log_sown
  + 生长季/极端指数（v6_09）：gs_tmax_mean/gs_tmin_mean/gs_ppt/gs_srad/gs_pet/gdd10/
    gs_aridity/prec_cv/gs_prec_share/winter_temp/seasonal_temp_range

协议（与 v6_04 同框架）：
  LCO 10 折按县分组 + 时间外推（train ≤2019 → test 2020-22）
  多种子 42-46 稳健性

用法:
  python scripts/data/v6_10_train_xgb_prediction.py [--seeds 42,43,44,45,46] [--target log_yield|y_anom]
输出: reports/v6_xgb_pred_{target}_report.md + fold/seed csv
"""
import argparse
import sys
import warnings
from pathlib import Path

warnings.filterwarnings("ignore")
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.stderr.reconfigure(encoding="utf-8", errors="replace")

import numpy as np
import pandas as pd
from sklearn.metrics import r2_score, mean_squared_error
from sklearn.model_selection import KFold
import xgboost as xgb

PROJECT_ROOT = Path(__file__).resolve().parents[2]
PANEL = PROJECT_ROOT / "data" / "interim" / "paper_panel_v7_prediction.parquet"

# 基础特征（v6 官方口径） + 生长季/极端指数
BASE = ["temp", "prec", "sun",
        "spei_annual_mean", "spei_growing_season_mean", "ndvi_yearly",
        "lst_day_growing_mean_k", "fert", "irr", "flood", "drou_a", "flood_a",
        "cropland_ratio", "log_sown"]
SEASONAL = ["gs_tmax_mean", "gs_tmin_mean", "gs_ppt", "gs_srad", "gs_pet",
            "gdd10", "gs_aridity", "prec_cv", "gs_prec_share",
            "winter_temp", "seasonal_temp_range"]
FEATURES = BASE + SEASONAL

XGB_PARAMS = {
    "n_estimators": 300, "max_depth": 5, "learning_rate": 0.05,
    "subsample": 0.8, "colsample_bytree": 0.8,
    "reg_alpha": 0.1, "reg_lambda": 1.0,
    "random_state": 42, "n_jobs": -1,
}


def _to_md(df: pd.DataFrame) -> str:
    """手写 markdown 表格，不依赖 tabulate。"""
    cols = list(df.columns)
    header = "| " + " | ".join(str(c) for c in cols) + " |"
    sep = "|" + "|".join("---" for _ in cols) + "|"
    body = "\n".join("| " + " | ".join(str(v) for v in row) + " |"
                     for row in df.itertuples(index=False))
    return "\n".join([header, sep, body])


def detrend_county(df: pd.DataFrame, y_col: str = "log_yield",
                   id_col: str = "区县代码", yr_col: str = "年份",
                   min_pts: int = 3) -> pd.Series:
    """县内 OLS 线性趋势残差（产量异常）。年份不足 min_pts 的县回退为减县均值。"""
    out = pd.Series(np.nan, index=df.index, dtype=float)
    for cid, g in df.groupby(id_col):
        y = g[y_col].values.astype(float)
        t = g[yr_col].values.astype(float)
        if len(t) >= min_pts:
            coef = np.polyfit(t, y, 1)
            trend = np.polyval(coef, t)
        else:
            trend = np.full(len(t), y.mean())
        out.loc[g.index] = y - trend
    return out


def main() -> int:
    parser = argparse.ArgumentParser(description="XGBoost 产量异常 + 生长季/极端指数 预测")
    parser.add_argument("--panel", type=str, default=str(PANEL), help="v7 特征矩阵")
    parser.add_argument("--target", type=str, default="log_yield", choices=["log_yield", "y_anom"],
                        help="目标：绝对产量 or 县趋势残差异常（默认 y_anom 当 --target y_anom）")
    parser.add_argument("--seeds", type=str, default="42", help="种子列表")
    parser.add_argument("--no-seasonal", action="store_true", help="只用基础 14 维，不加生长季指数")
    parser.add_argument("--prov-ablate", action="store_true",
                        help="省级共享特征消融：只留县级气候 + 生长季/极端指数 + 规模控制，剔除省-年恒量")
    args = parser.parse_args()

    panel_path = Path(args.panel)
    df = pd.read_parquet(panel_path)
    df = df[df["log_yield"].notna()].copy()
    df["log_sown"] = np.log1p(df["农作物总播种面积_千公顷"].fillna(0))
    # 目标异常
    df["y_anom"] = detrend_county(df)
    target = args.target
    y = df[target].values.astype(float)

    feats = BASE if args.no_seasonal else FEATURES
    # 省级共享（省-年恒量），消融时剔除
    PROV_SHARED = ["spei_annual_mean", "spei_growing_season_mean", "ndvi_yearly",
                   "lst_day_growing_mean_k", "fert", "irr", "flood", "drou_a",
                   "flood_a", "cropland_ratio"]
    if args.prov_ablate:
        feats = [f for f in feats if f not in PROV_SHARED]
    df = df.dropna(subset=feats)
    print(f"采样: {len(df)} 行, {df['区县代码'].nunique()} 县, {df['年份'].nunique()} 年 | 特征 {len(feats)} | 目标 {target}")

    X = df[feats].values
    groups = df["区县代码"].values
    counties = np.unique(groups)
    # 对齐 y 到 dropna 之后
    y = df[target].values.astype(float)

    seeds = [int(s) for s in args.seeds.split(",")]
    suffix = f"_{target}" + ("" if args.no_seasonal else "_seasonal")
    if args.prov_ablate:
        suffix += "_provablate"
    report_path = PROJECT_ROOT / "reports" / f"v6_xgb_pred{suffix}_report.md"
    folds_path = PROJECT_ROOT / "reports" / f"v6_xgb_pred{suffix}_fold_results.csv"
    seed_path = PROJECT_ROOT / "reports" / f"v6_xgb_pred{suffix}_seed_results.csv"

    rows, seed_rows, imp = [], [], None
    for seed in seeds:
        print(f"\n── seed {seed} ──")
        kf = KFold(n_splits=10, shuffle=True, random_state=seed)
        params = {**XGB_PARAMS, "random_state": seed}
        preds, trues = [], []
        for fold, (tr_i, te_i) in enumerate(kf.split(counties)):
            tr_c = set(counties[tr_i])
            tr_mask = np.isin(groups, list(tr_c))
            te_mask = ~tr_mask
            model = xgb.XGBRegressor(**params)
            model.fit(X[tr_mask], y[tr_mask])
            p = model.predict(X[te_mask])
            r2 = r2_score(y[te_mask], p)
            rmse = mean_squared_error(y[te_mask], p, squared=False)
            rows.append({"seed": seed, "fold": fold + 1, "n_train": tr_mask.sum(), "n_test": te_mask.sum(),
                         "r2": round(r2, 4), "rmse": round(rmse, 4)})
            preds.append(p); trues.append(y[te_mask])
        overall_r2 = r2_score(np.concatenate(trues), np.concatenate(preds))
        overall_rmse = mean_squared_error(np.concatenate(trues), np.concatenate(preds), squared=False)
        print(f"  LCO overall: R²={overall_r2:+.4f}  RMSE={overall_rmse:.4f}")

        # 时间外推
        tr_t = (df["年份"] <= 2019).values
        te_t = ~tr_t
        model_t = xgb.XGBRegressor(**params)
        model_t.fit(X[tr_t], y[tr_t])
        p_t = model_t.predict(X[te_t])
        time_r2 = r2_score(y[te_t], p_t)
        time_rmse = mean_squared_error(y[te_t], p_t, squared=False)
        print(f"  Time-holdout (≤2019→2020-22): R²={time_r2:+.4f} RMSE={time_rmse:.4f}")

        seed_rows.append({"seed": seed, "lco_r2": round(overall_r2, 4), "lco_rmse": round(overall_rmse, 4),
                          "time_r2": round(time_r2, 4), "time_rmse": round(time_rmse, 4)})
        imp = pd.DataFrame({"feature": feats, "importance": model_t.feature_importances_}).sort_values("importance", ascending=False)

    pd.DataFrame(rows).to_csv(folds_path, index=False)
    pd.DataFrame(seed_rows).to_csv(seed_path, index=False)
    lines = [
        "# v6 XGBoost 产量异常 + 生长季/极端指数 预测报告",
        "",
        f"- 面板: {panel_path.name}",
        f"- 目标变量: **{target}**" + ("（绝对产量，现状）" if target == "log_yield" else "（县 OLS 线性趋势残差=产量异常/增减产）"),
        f"- 特征 ({len(feats)}): " + ", ".join(feats),
        f"- 协议: LCO 10 折按县分组 + 时间外推(≤2019→2020-22); 种子 {', '.join(map(str, seeds))}",
        "",
        "## 多种子结果",
        "",
        _to_md(pd.DataFrame(seed_rows)),
        "",
        "## 特征重要性（时间模型）",
        "",
        _to_md(imp),
        "",
    ]
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text("\n".join(lines), encoding="utf-8")
    print(f"✅ 报告 -> {report_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
