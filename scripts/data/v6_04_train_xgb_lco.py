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

用法:
  python scripts/data/v6_04_train_xgb_lco.py                            # 官方口径 (seed 42)
  python scripts/data/v6_04_train_xgb_lco.py --ablate-prov              # 省特征消融(仅县级特征)
  python scripts/data/v6_04_train_xgb_lco.py --seeds 42,43,44,45,46     # 多种子稳健性
  python scripts/data/v6_04_train_xgb_lco.py --panel paper_panel_v6_climate_full.parquet  # 县级 SPEI 面板
输出: reports/v6_xgb{_ablate_prov}{_面板名}_report.md + 同名 fold/seed_results.csv
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
    parser.add_argument("--ablate-prov", action="store_true",
                        help="省特征消融：剔除 10 个省级共享特征，仅保留县级特征重跑")
    parser.add_argument("--seeds", type=str, default="42",
                        help="种子列表（逗号分隔，同时控制折划分与模型随机性；默认 42）")
    args = parser.parse_args(argv)
    panel_path = Path(args.panel)
    # 非默认面板/消融 → 报告加后缀区分; 默认保持官方文件名 v6_xgb_lco_report.md
    suffix = "_ablate_prov" if args.ablate_prov else ""
    if panel_path.name != PANEL.name:
        suffix += f"_{panel_path.stem.replace('paper_panel_', '')}"
    report_path = REPORT if suffix == "" else Path(str(REPORT).replace("v6_xgb_lco_report.md", f"v6_xgb{suffix}_report.md"))
    folds_path = Path(str(FOLDS).replace("v6_xgb_fold_results.csv", f"v6_xgb{suffix}_fold_results.csv"))

    df = pd.read_parquet(panel_path)
    df = df[df["log_yield"].notna()].copy()
    df["log_sown"] = np.log1p(df["农作物总播种面积_千公顷"].fillna(0))
    # ── 省特征消融: 剔除省级共享特征, 仅保留县级特征 ──
    features = FEATURES
    spei_is_county = False
    if args.ablate_prov:
        spei_is_county = df["spei_annual_mean"].nunique() > 500  # 县级 ~5000 唯一值 vs 省级 ~100
        features = [f for f in FEATURES
                    if f not in PROV_SHARED or (f.startswith("spei_") and spei_is_county)]
        print(f"[消融] 特征集 ({len(features)}): {features}")
    df = df.dropna(subset=features)
    print(f"训练样本: {len(df)} 行, {df['区县代码'].nunique()} 县, {df['年份'].nunique()} 年 | 面板: {panel_path.name}")

    X = df[features].values
    y = df["log_yield"].values
    groups = df["区县代码"].values
    counties = np.unique(groups)

    seeds = [int(s) for s in args.seeds.split(",")]
    rows, seed_rows, imp = [], [], None
    for seed in seeds:
        print(f"\n── seed {seed} ──")
        # ── leave-county-out 10 折(折划分随 seed 变化)──
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
            preds.append(p)
            trues.append(y[te_mask])
            print(f"  seed {seed} fold {fold + 1:>2}: R²={r2:+.4f} RMSE={rmse:.4f} (test n={te_mask.sum()})")

        overall_r2 = r2_score(np.concatenate(trues), np.concatenate(preds))
        overall_rmse = mean_squared_error(np.concatenate(trues), np.concatenate(preds), squared=False)
        print(f"  LCO overall: R²={overall_r2:+.4f}  RMSE={overall_rmse:.4f}")

        # ── 时间外推: train ≤2019 → test 2020-2023 ──
        tr_t = df["年份"] <= 2019
        te_t = ~tr_t
        model_t = xgb.XGBRegressor(**params)
        model_t.fit(X[tr_t.values], y[tr_t.values])
        p_t = model_t.predict(X[te_t.values])
        time_r2 = r2_score(y[te_t.values], p_t)
        time_rmse = mean_squared_error(y[te_t.values], p_t, squared=False)
        print(f"  Time-holdout (≤2019→2020-22): R²={time_r2:+.4f} RMSE={time_rmse:.4f}")

        seed_rows.append({"seed": seed, "lco_r2": round(overall_r2, 4), "lco_rmse": round(overall_rmse, 4),
                          "time_r2": round(time_r2, 4), "time_rmse": round(time_rmse, 4)})
        # ── 特征重要性(最后一个 seed 的时间模型)──
        imp = pd.DataFrame({"feature": features, "importance": model_t.feature_importances_})
        imp = imp.sort_values("importance", ascending=False)

    fold_df = pd.DataFrame(rows)
    seed_df = pd.DataFrame(seed_rows)
    folds_path.parent.mkdir(parents=True, exist_ok=True)
    fold_df.to_csv(folds_path, index=False)
    seed_csv_path = Path(str(folds_path).replace("_fold_results.csv", "_seed_results.csv"))
    seed_df.to_csv(seed_csv_path, index=False)

    REPORT.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        "# v6 XGBoost Leave-County-Out 报告（首轮 sanity）",
        "",
        f"- 样本: {len(df)} 行（{df['区县代码'].nunique()} 县 × {df['年份'].min()}–{df['年份'].max()} 非平衡面板，10 主产省；部分县缺 1–10 年，2023 年产量缺失）",
        f"- 目标: log_yield = log(粮食总产量_吨)",
        f"- 特征 ({len(features)}): " + ", ".join(features),
        "",
    ]
    if args.ablate_prov:
        lines += [
            "> **省特征消融**：剔除 10 个省级共享特征（省-年常量，原重要性合计 ~73%）后重跑；"
            + ("县级 SPEI 保留（本面板 spei 列为县级值，唯一值 ~5000）。"
               if spei_is_county else "省级 SPEI 一并剔除（本面板 spei 列为省级值）。"),
            "",
        ]
    lines += [
        "## 多种子结果",
        "",
        seed_df.to_markdown(index=False),
        "",
        f"- 种子集: {', '.join(map(str, seeds))}。"
        + ("seed 42 行即官方口径（省级 SPEI 面板下与首轮 R²=0.6604 同 split 可比）。"
           if 42 in seeds and not args.ablate_prov
           else "均值±std 报告多种子稳健性。"),
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
        "| v4 省级 (XGBoost-SHAP) | random 8:2 | 0.9072 |",
        "| v4 省级 (XGBoost-SHAP) | leave-province-out（真实 LPO） | -16.83（中位） |",
        "| v5 地级市 | 城市级 LPO | 0.213 |",
        f"| v6 县级 (本报告, seed {seeds[0]}) | LCO | {seed_rows[0]['lco_r2']:+.4f} |",
        "",
    ]
    report_path.write_text("\n".join(lines), encoding="utf-8")
    print(f"✅ 报告 -> {report_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
