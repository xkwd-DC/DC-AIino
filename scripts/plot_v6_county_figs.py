#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""scripts/plot_v6_county_figs.py — 重画县级口径（v6 面板）论文图并插入 §3 用。

产物（docs/figures/）：
  fig_v6_shap_bar.png           县级口径 XGBoost-SHAP 全局重要性 (mean |SHAP|)
  fig_v6_shap_beeswarm.png      县级口径 SHAP 蜂群图
  fig_v6_attention_weights.png  县级口径 Attention-LSTM 特征注意力权重（多种子×多折均值）
  fig_v6_scale_lpo_lco.png      三级尺度空间外推对照（省级 LPO / 地级市 LPO / 县级 LCO）
  fig_v6_time_neg_to_pos.png    时间外推"负→正"（省-年共享特征消融）对照

在根 .venv（含 xgboost / shap / matplotlib / sklearn / pandas / numpy）下运行：
    .venv/Scripts/python.exe scripts/plot_v6_county_figs.py
"""
from __future__ import annotations

import warnings
warnings.filterwarnings("ignore")
import sys
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.stderr.reconfigure(encoding="utf-8", errors="replace")
from pathlib import Path

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
from matplotlib import font_manager
import xgboost as xgb
import shap

ROOT = Path(__file__).resolve().parents[1]
FIG = ROOT / "docs/figures"
FIG.mkdir(parents=True, exist_ok=True)
DATA = ROOT / "data/interim/paper_panel_v6_climate_full.parquet"
ATT_CSV = ROOT / "reports/v6_att_lstm_v6_climate_full_weights.csv"

# 中文字体（Windows）：SimHei 兜底，DejaVu 作 ASCII 回退
plt.rcParams["font.family"] = ["Microsoft YaHei", "SimHei", "DejaVu Sans"]
plt.rcParams["axes.unicode_minus"] = False

COUNTY = ["temp", "prec", "sun"]
PROV = ["spei_annual_mean", "spei_growing_season_mean", "ndvi_yearly",
        "lst_day_growing_mean_k", "fert", "irr", "flood", "drou_a", "flood_a",
        "cropland_ratio"]
SCALE = ["log_sown"]
FEAT14 = COUNTY + PROV + SCALE

CN = {
    "log_sown": "播种面积(对数 log_sown)", "temp": "气温 temp", "prec": "降水 prec",
    "sun": "日照 sun", "cropland_ratio": "耕地比例 cropland_ratio",
    "lst_day_growing_mean_k": "生长季白天LST lst_day", "flood_a": "洪涝面积 flood_a",
    "drou_a": "干旱面积 drou_a", "ndvi_yearly": "NDVI ndvi_yearly",
    "irr": "灌溉率 irr", "fert": "化肥 fert", "flood": "洪涝占比 flood",
    "spei_annual_mean": "SPEI(年) spei_annual", "spei_growing_season_mean": "SPEI(生长季) spei_grow",
}

XGB_PARAMS = {"n_estimators": 300, "max_depth": 5, "learning_rate": 0.05,
              "subsample": 0.8, "colsample_bytree": 0.8,
              "reg_alpha": 0.1, "reg_lambda": 1.0, "random_state": 42, "n_jobs": -1}


def build_panel() -> pd.DataFrame:
    df = pd.read_parquet(DATA)
    df = df[df["log_yield"].notna()].copy()
    df["log_sown"] = np.log1p(df["农作物总播种面积_千公顷"].fillna(0))
    return df.dropna(subset=FEAT14)


def county_shap(df: pd.DataFrame):
    X = df[FEAT14].values
    y = df["log_yield"].values
    model = xgb.XGBRegressor(**XGB_PARAMS)
    model.fit(X, y)
    expl = shap.TreeExplainer(model)
    sv = expl.shap_values(X)
    imp = np.abs(sv).mean(axis=0)
    return model, sv, imp, X


def plot_shap_bar(imp: np.ndarray):
    order = np.argsort(imp)[::-1]
    labels = [CN[FEAT14[i]] for i in order]
    vals = imp[order]
    fig, ax = plt.subplots(figsize=(8.5, 6))
    bars = ax.barh(labels[::-1], vals[::-1], color="#456B5D")
    ax.set_xlabel("mean |SHAP|（对 log 产量预测的边际贡献）")
    ax.set_title("县级口径 XGBoost-SHAP 全局重要性（14 维全特征模型）")
    ax.invert_yaxis()
    for b, v in zip(bars, vals[::-1]):
        ax.text(v, b.get_y() + b.get_height() / 2, f" {v:.3f}",
                va="center", ha="left", fontsize=8)
    ax.set_xlim(0, imp.max() * 1.18)
    plt.tight_layout()
    plt.savefig(FIG / "fig_v6_shap_bar.png", dpi=200)
    plt.close()


def plot_shap_beeswarm(df: pd.DataFrame, sv: np.ndarray):
    X = df[FEAT14].values
    labels = [CN[f] for f in FEAT14]
    shap.summary_plot(sv, X, feature_names=labels, show=False, max_display=14)
    plt.title("县级口径 SHAP 蜂群图（单样本边际贡献分布）")
    plt.tight_layout()
    plt.savefig(FIG / "fig_v6_shap_beeswarm.png", dpi=200)
    plt.close()


def plot_attention():
    att = pd.read_csv(ATT_CSV)
    feat_cols = [c for c in att.columns if c not in ("seed", "fold")]
    w = att[feat_cols].mean(axis=0).values
    # 对齐到 FEAT14 顺序
    order = np.argsort(w)[::-1]
    labels = [CN[feat_cols[i]] for i in order]
    vals = w[order]
    fig, ax = plt.subplots(figsize=(8.5, 6))
    bars = ax.barh(labels[::-1], vals[::-1], color="#7B5E3B")
    ax.set_xlabel("Attention 权重（多种子×多折均值，softmax 软掩码）")
    ax.set_title("县级口径 Attention-LSTM 特征注意力权重")
    ax.invert_yaxis()
    for b, v in zip(bars, vals[::-1]):
        ax.text(v, b.get_y() + b.get_height() / 2, f" {v:.3f}",
                va="center", ha="left", fontsize=8)
    ax.set_xlim(0, w.max() * 1.18)
    plt.tight_layout()
    plt.savefig(FIG / "fig_v6_attention_weights.png", dpi=200)
    plt.close()
    return feat_cols, w


def plot_scale():
    names = ["省级 v4\nleave-province-out\n(中位)", "地级市 v5\n城市级 LPO", "县级 v6\nLCO (seed 42)"]
    vals = [-16.83, 0.213, 0.6625]
    fig, ax = plt.subplots(figsize=(7.5, 5))
    colors = ["#B23A48", "#C98A3B", "#456B5D"]
    bars = ax.bar(names, vals, color=colors, width=0.55)
    ax.set_ylim(-3.2, 1.0)
    # 省级被截断到 -3.2：白底注释真实值 + 柱底截断锯齿
    ax.text(0, -2.0, "−16.83\n(截断显示)", ha="center", va="center", fontsize=10,
            color="#B23A48", bbox=dict(boxstyle="round,pad=0.25", fc="white", ec="#B23A48", alpha=0.9))
    ax.plot([-0.28, 0.28], [-3.2, -3.2], color="#B23A48", lw=1.2)
    for x0 in np.linspace(-0.28, 0.28, 6):
        ax.plot([x0, x0 + 0.04], [-3.2, -3.28], color="#B23A48", lw=1.2)
    for b, v in zip(bars, vals):
        if v != vals[0]:  # 省级已在柱内注释，不再重复外层标签
            ax.text(b.get_x() + b.get_width() / 2, v + 0.12,
                    f"{v:+.3f}", ha="center", va="bottom", fontsize=10)
    ax.axhline(0, color="k", lw=0.8)
    ax.set_ylabel("空间外推 R²")
    ax.set_title("三级尺度空间外推对照（单位越小样本越下沉）")
    plt.tight_layout()
    plt.savefig(FIG / "fig_v6_scale_lpo_lco.png", dpi=200)
    plt.close()


def plot_time():
    names = ["XGBoost 全特征\n(14 维)", "省特征消融-县级SPEI\n(6 维)",
             "省特征消融-剔省级SPEI\n(4 维)", "生长季/极端指数 v7\n(15 维消融)"]
    vals = [-0.8198, 0.319, 0.368, 0.451]
    fig, ax = plt.subplots(figsize=(8, 5))
    colors = ["#B23A48", "#C98A3B", "#C98A3B", "#456B5D"]
    bars = ax.bar(names, vals, color=colors, width=0.55)
    ax.axhline(0, color="k", lw=0.9)
    for b, v in zip(bars, vals):
        ax.text(b.get_x() + b.get_width() / 2, v + (0.02 if v >= 0 else -0.06),
                f"{v:+.3f}", ha="center", va="bottom" if v >= 0 else "top", fontsize=10)
    ax.set_ylim(-1.0, 0.55)
    ax.set_ylabel("时间外推 R²（≤2019 → 2020–22）")
    ax.set_title("省-年共享特征消融：时间外推由负转正")
    plt.tight_layout()
    plt.savefig(FIG / "fig_v6_time_neg_to_pos.png", dpi=200)
    plt.close()


def spearman(a: np.ndarray, b: np.ndarray) -> float:
    ar, br = pd.Series(a).rank(), pd.Series(b).rank()
    return float(np.corrcoef(ar, br)[0, 1])


def main():
    df = build_panel()
    print(f"[1] 县制面板: {len(df)} 行, {df['区县代码'].nunique()} 县")
    model, sv, imp, _ = county_shap(df)
    order = np.argsort(imp)[::-1]
    print("[2] 县级口径 XGBoost-SHAP (full 14) mean|SHAP| 排名:")
    for i in order:
        print(f"    {FEAT14[i]:<26} {imp[i]:.4f}")
    plot_shap_bar(imp)
    plot_shap_beeswarm(df, sv)
    print(f"    出图: fig_v6_shap_bar.png / fig_v6_shap_beeswarm.png")

    feat_cols, w = plot_attention()
    aorder = np.argsort(w)[::-1]
    print("[3] 县级口径 Attention-LSTM 权重 (多种子×多折均值) 排名:")
    for i in aorder:
        print(f"    {feat_cols[i]:<26} {w[i]:.4f}")

    # SHAP(14维) vs Attention(14维) Spearman
    shap_rank = np.array([imp[FEAT14.index(f)] for f in feat_cols])
    rho = spearman(shap_rank, w)
    top_shap = [FEAT14[i] for i in order[:3]]
    top_att = [feat_cols[i] for i in aorder[:3]]
    print(f"[4] 县制 SHAP↔Attention Top-3: SHAP={top_shap}  Att={top_att}  Spearman ρ={rho:.3f}")

    plot_scale()
    plot_time()
    print(f"[5] 出图: fig_v6_scale_lpo_lco.png / fig_v6_time_neg_to_pos.png")
    print("✅ 全部完成")


if __name__ == "__main__":
    main()
