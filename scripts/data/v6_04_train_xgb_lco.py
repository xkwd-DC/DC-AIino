#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""v6 Step 4：XGBoost leave-county-out 空间泛化 sanity（首轮）。

特征（首轮精简集，14 维）：
  县级 ERA5:     temp / prec / sun
  省级共享(v4):  spei_annual_mean / spei_growing_season_mean / ndvi_yearly /
                 lst_day_growing_mean_k / fert / irr / flood / drou_a / flood_a / cropland_ratio
  县级规模控制:  log1p(农作物总播种面积_千公顷)

CV 设计：
  - leave-county-out: 10 折按县分组（同县全部年份同折，防泄漏）
  - 另报时间外推: 训练 ≤2019 → 测试 2020-2023

用法: python scripts/data/v6_04_train_xgb_lco.py
输出: reports/v6_xgb_lco_report.md + reports/v6_xgb_fold_results.csv
"""
import argparse
from pathlib import Path
import sys
import warnings
warnings.filterwarnings("ignore")

# Windows GBK console 下 ²/✅ 等字符会 UnicodeEncodeError；强制 UTF-8 输出
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.stderr.reconfigure(encoding="utf-8", errors="replace")

import numpy as np
import pandas as pd
from sklearn.metrics import r2_score, mean_squared_error
from sklearn.model_selection import KFold
import xgboost as xgb

PROJECT_ROOT = Path(__file__).resolve().parents[2]
PANEL = PROJECT_ROOT / "data" / "interim" / "paper_panel_v6_climate.parquet"
REPORT = PROJECT_ROOT / "reports" / "v6_xgb_lco_report.md"
FOLDS = PROJECT_ROOT / "reports" / "v6_xgb_fold_results.csv"

COUNTY_FEATURES = ["temp", "prec", "sun"]
PROV_SHARED = [
    "spei_annual_mean", "spei_growing_season_mean", "ndvi_yearly",
    "lst_day_growing_mean_k", "fert", "irr", "flood", "drou_a", "flood_a",
    "cropland_ratio",
]
SCALE_CONTROL = ["log_sown"]
FEATURES = COUNTY_FEATURES + PROV_SHARED + SCALE_CONTROL

XGB_PARAMS = {
    "n_estimators": 300, "max_depth": 5, "learning_rate": 0.05,
    "subsample": 0.8, "colsample_bytree": 0.8,
    "reg_alpha": 0.1, "reg_lambda": 1.0,
    "random_state": 42, "n_jobs": -1,
}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="v6 XGBoost LCO sanity")
    parser.add_argument("--panel", type=str, default=str(PANEL),
                        help="特征矩阵 parquet 路径（如 paper_panel_v6_climate_full.parquet）")
    args = parser.parse_args(argv)
    panel_path = Path(args.panel)
    # 非默认面板 → 报告加后缀区分
    suffix = "" if panel_path.name == PANEL.name else f"_{panel_path.stem.replace('paper_panel_', '')}"
    report_path = Path(str(REPORT).replace("v6_xgb_lco_report.md", f"v6_xgb{suffix}_report.md"))
    folds_path = Path(str(FOLDS).replace("v6_xgb_fold_results.csv", f"v6_xgb{suffix}_fold_results.csv"))

    df = pd.read_parquet(panel_path)
    df = df[df["log_yield"].notna()].copy()
    df["log_sown"] = np.log1p(df["农作物总播种面积_千公顷"].fillna(0))
    df = df.dropna(subset=FEATURES)
    print(f"训练样本: {len(df)} 行, {df['区县代码'].nunique()} 县, {df['年份'].nunique()} 年 | 面板: {panel_path.name}")

    X = df[FEATURES].values
    y = df["log_yield"].values
    groups = df["区县代码"].values
    counties = np.unique(groups)

    # ── leave-county-out 10 折 ──
    kf = KFold(n_splits=10, shuffle=True, random_state=42)
    rows, preds, trues = [], [], []
    for fold, (tr_i, te_i) in enumerate(kf.split(counties)):
        tr_c = set(counties[tr_i])
        tr_mask = np.isin(groups, list(tr_c))
        te_mask = ~tr_mask
        model = xgb.XGBRegressor(**XGB_PARAMS)
        model.fit(X[tr_mask], y[tr_mask])
        p = model.predict(X[te_mask])
        r2 = r2_score(y[te_mask], p)
        rmse = mean_squared_error(y[te_mask], p, squared=False)
        rows.append({"fold": fold + 1, "n_train": tr_mask.sum(), "n_test": te_mask.sum(),
                     "r2": round(r2, 4), "rmse": round(rmse, 4)})
        preds.append(p)
        trues.append(y[te_mask])
        print(f"  fold {fold + 1:>2}: R²={r2:+.4f} RMSE={rmse:.4f} (test n={te_mask.sum()})")

    overall_r2 = r2_score(np.concatenate(trues), np.concatenate(preds))
    overall_rmse = mean_squared_error(np.concatenate(trues), np.concatenate(preds), squared=False)
    print(f"\nLCO overall: R²={overall_r2:+.4f}  RMSE={overall_rmse:.4f}")

    # ── 时间外推: train ≤2019 → test 2020-2023 ──
    tr_t = df["年份"] <= 2019
    te_t = ~tr_t
    model_t = xgb.XGBRegressor(**XGB_PARAMS)
    model_t.fit(X[tr_t.values], y[tr_t.values])
    p_t = model_t.predict(X[te_t.values])
    time_r2 = r2_score(y[te_t.values], p_t)
    time_rmse = mean_squared_error(y[te_t.values], p_t, squared=False)
    print(f"Time-holdout (≤2019→2020-23): R²={time_r2:+.4f} RMSE={time_rmse:.4f}")

    # ── 特征重要性 ──
    imp = pd.DataFrame({"feature": FEATURES, "importance": model_t.feature_importances_})
    imp = imp.sort_values("importance", ascending=False)

    fold_df = pd.DataFrame(rows)
    folds_path.parent.mkdir(parents=True, exist_ok=True)
    fold_df.to_csv(folds_path, index=False)

    REPORT.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        "# v6 XGBoost Leave-County-Out 报告（首轮 sanity）",
        "",
        f"- 样本: {len(df)} 行 = {df['区县代码'].nunique()} 县 × {df['年份'].nunique()} 年（10 主产省）",
        f"- 目标: log_yield = log(粮食总产量_吨)",
        f"- 特征 ({len(FEATURES)}): " + ", ".join(FEATURES),
        f"- LCO overall R² = **{overall_r2:+.4f}** (RMSE {overall_rmse:.4f})",
        f"- 时间外推 R² (≤2019 → 2020-23) = **{time_r2:+.4f}** (RMSE {time_rmse:.4f})",
        "",
        "## 各折结果",
        "",
        fold_df.to_markdown(index=False),
        "",
        "## 特征重要性（时间模型）",
        "",
        imp.to_markdown(index=False),
        "",
        "## 对比",
        "",
        "| 版本 | CV | R² |",
        "|---|---|---|",
        "| v4 省级 (XGBoost-SHAP) | LPO | 0.9072 |",
        "| v5 地级市 | 城市级 LPO | 0.213 |",
        f"| v6 县级 (本报告) | LCO | {overall_r2:+.4f} |",
        "",
    ]
    report_path.write_text("\n".join(lines), encoding="utf-8")
    print(f"✅ 报告 -> {report_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
