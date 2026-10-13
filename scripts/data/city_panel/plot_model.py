"""Render the model-result figure set (PDF + PNG) for the city panel re-run."""

from __future__ import annotations

import warnings
from pathlib import Path

import matplotlib
import numpy as np
import pandas as pd
import xgboost as xgb
from matplotlib import pyplot as plt
from matplotlib.backends.backend_pdf import PdfPages
from sklearn.metrics import r2_score

matplotlib.use("Agg")
warnings.filterwarnings("ignore")

plt.rcParams["font.family"] = ["Microsoft YaHei", "SimHei"]
plt.rcParams["axes.unicode_minus"] = False
plt.rcParams["font.size"] = 11
plt.rcParams["axes.edgecolor"] = "#B8C2BC"
plt.rcParams["axes.labelcolor"] = "#1A1A1A"
plt.rcParams["text.color"] = "#1A1A1A"
plt.rcParams["xtick.color"] = "#3C4A44"
plt.rcParams["ytick.color"] = "#3C4A44"

PANEL = Path(r"D:\DC\deliverables\city-grain-data\主产区市级面板_2000_2024.csv")
OUT_DIR = Path(r"D:\DC\deliverables\city-grain-data\模型可视化")
PARAMS = dict(n_estimators=300, max_depth=5, learning_rate=0.05, subsample=0.8,
              colsample_bytree=0.8, reg_alpha=0.1, reg_lambda=1.0, random_state=42, n_jobs=-1)

GREEN, ORANGE, RED, NAVY, GRAY = "#2E7D5B", "#D08C34", "#C0392B", "#1F3864", "#7A8B83"
LEVEL_FEATS = ["log_sown", "cropland", "temp", "prec", "dew", "lat", "lon"]
CLIM_FEATS = ["temp", "prec", "dew", "lat", "lon"]


def load() -> pd.DataFrame:
    df = pd.read_csv(PANEL).rename(columns={
        "粮食产量(万吨)": "y", "农作物总播种面积(千公顷)": "sown",
        "常用耕地面积(万公顷)": "cropland", "年度平均气温(°C)": "temp",
        "年度总降水量(mm)": "prec", "年度平均露点温度(°C)": "dew",
        "产量数据来源": "source", "经度": "lon", "纬度": "lat", "省份": "prov", "地级市": "city",
    })
    df = df[(df["y"] > 0) & (df["sown"] > 0)].copy()
    df["log_sown"] = np.log1p(df["sown"])
    df["log_y"] = np.log(df["y"])
    df["log_y_pa"] = df["log_y"] - df["log_sown"]
    for c in ("cropland", "temp", "prec", "dew"):
        df[c] = pd.to_numeric(df[c], errors="coerce")
    df["is_official"] = df["source"] != "县级加总校准估算"
    return df


def fit(train, test, target, feats):
    model = xgb.XGBRegressor(**PARAMS)
    model.fit(train[feats], train[target])
    pred = model.predict(test[feats])
    return model, pred


def lpo(df, target, feats, keep_pred=False):
    scores, preds = [], []
    for prov in sorted(df["prov"].unique()):
        test, train = df[df["prov"] == prov], df[df["prov"] != prov]
        model, pred = fit(train, test, target, feats)
        scores.append((prov, len(test), r2_score(test[target], pred)))
        if keep_pred:
            preds.append(pd.DataFrame({
                "prov": test["prov"], "year": test["年份"], "actual": test[target],
                "pred": pred, "official": test["is_official"],
            }))
    return scores, (pd.concat(preds) if preds else None)


def save(fig, pdf, name):
    fig.tight_layout()
    pdf.savefig(fig)
    fig.savefig(OUT_DIR / f"{name}.png", dpi=200)
    plt.close(fig)


def style_axes(ax, xlabel=None, ylabel=None, title=None):
    if title:
        ax.set_title(title, fontsize=13, color="#12352A", pad=12, loc="left")
    if xlabel:
        ax.set_xlabel(xlabel, fontsize=10.5)
    if ylabel:
        ax.set_ylabel(ylabel, fontsize=10.5)
    ax.grid(axis="y", color="#E3E8E5", linewidth=0.8)
    ax.set_axisbelow(True)
    for side in ("top", "right"):
        ax.spines[side].set_visible(False)


def main() -> int:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    raw = load()
    # 与报告口径一致：水平模型要求特征完整，气候模型另用一套筛选
    df = raw.dropna(subset=LEVEL_FEATS + ["log_y"]).copy()
    clim = raw.dropna(subset=CLIM_FEATS + ["log_y", "log_y_pa"]).copy()
    official = df[df["is_official"]]
    clim_official = clim[clim["is_official"]]
    print(f"level rows={len(df)} official={len(official)} | climate rows={len(clim)} official={len(clim_official)}")

    # ---- 模型结果 ----
    print("run: leave-province-out")
    folds_all, _ = lpo(df, "log_y", LEVEL_FEATS)
    folds_off, preds_off = lpo(official, "log_y", LEVEL_FEATS, keep_pred=True)

    print("run: ablation")
    ablation = {}
    for label, target, feats, frame_all, frame_off in (
        ("含规模变量", "log_y", LEVEL_FEATS, df, official),
        ("仅气候与空间", "log_y", CLIM_FEATS, clim, clim_official),
        ("单产模型（仅气候）", "log_y_pa", CLIM_FEATS, clim, clim_official),
    ):
        for sub_label, sub in (("全部样本", frame_all), ("仅官方值", frame_off)):
            scores, _ = lpo(sub, target, feats)
            ablation[(label, sub_label)] = float(np.median([s[2] for s in scores]))

    print("run: incremental")
    incremental = {}
    for label, feats in (("播种面积", ["log_sown"]),
                         ("播种面积+气温", ["log_sown", "temp"]),
                         ("播种面积+气候+经纬度", ["log_sown", "temp", "prec", "dew", "lat", "lon"])):
        for sub_label, sub in (("全部样本", clim), ("仅官方值", clim_official)):
            scores, _ = lpo(sub, "log_y", feats)
            incremental[(label, sub_label)] = float(np.median([s[2] for s in scores]))

    model = xgb.XGBRegressor(**PARAMS)
    model.fit(df[LEVEL_FEATS], df["log_y"])
    importance = sorted(zip(LEVEL_FEATS, model.feature_importances_), key=lambda x: x[1])

    results = {"folds_all": folds_all, "folds_off": folds_off, "ablation": ablation,
               "incremental": incremental, "importance": importance}

    with PdfPages(OUT_DIR / "模型可视化.pdf") as pdf:
        # 图 1 留一省 R²
        fig, ax = plt.subplots(figsize=(9, 5.6))
        items = sorted(folds_off, key=lambda x: x[2])
        names = [p.replace("省", "").replace("自治区", "").replace("回族", "").replace("壮族", "") for p, _, _ in items]
        vals = [v for _, _, v in items]
        colors = [GREEN if v > 0 else RED for v in vals]
        ax.barh(names, vals, color=colors, height=0.62)
        for i, v in enumerate(vals):
            ax.text(v + (0.02 if v > 0 else -0.02), i, f"{v:.2f}",
                    va="center", ha="left" if v > 0 else "right", fontsize=9.5)
        ax.axvline(float(np.median(vals)), color=NAVY, linestyle="--", linewidth=1.2)
        ax.text(float(np.median(vals)) + 0.01, -0.9, f"中位 {np.median(vals):.3f}", color=NAVY, fontsize=10)
        ax.axvline(0, color="#8A9A93", linewidth=1)
        style_axes(ax, xlabel="留一省交叉验证 R²", title="分省空间外推表现（仅官方值样本，13 折）")
        save(fig, pdf, "fig1_lpo_by_province")

        # 图 2 对照实验
        fig, ax = plt.subplots(figsize=(9, 5))
        labels = ["含规模变量", "仅气候与空间", "单产模型（仅气候）"]
        x = np.arange(len(labels))
        w = 0.36
        a = [ablation[(l, "全部样本")] for l in labels]
        b = [ablation[(l, "仅官方值")] for l in labels]
        ax.bar(x - w / 2, a, w, label="全部样本", color=ORANGE)
        ax.bar(x + w / 2, b, w, label="仅官方值", color=NAVY)
        for xi, v in zip(x - w / 2, a):
            ax.text(xi, v + (0.02 if v >= 0 else -0.05), f"{v:.3f}", ha="center", fontsize=9.5)
        for xi, v in zip(x + w / 2, b):
            ax.text(xi, v + (0.02 if v >= 0 else -0.05), f"{v:.3f}", ha="center", fontsize=9.5)
        ax.axhline(0, color="#8A9A93", linewidth=1)
        ax.set_xticks(x, labels)
        ax.legend(frameon=False, fontsize=10)
        style_axes(ax, ylabel="中位 R²", title="去掉规模变量后，解释力几乎消失")
        save(fig, pdf, "fig2_ablation")

        # 图 3 增量检验
        fig, ax = plt.subplots(figsize=(9, 5))
        labels = ["播种面积", "播种面积+气温", "播种面积+气候+经纬度"]
        x = np.arange(len(labels))
        a = [incremental[(l, "全部样本")] for l in labels]
        b = [incremental[(l, "仅官方值")] for l in labels]
        ax.bar(x - w / 2, a, w, label="全部样本", color=ORANGE)
        ax.bar(x + w / 2, b, w, label="仅官方值", color=NAVY)
        for xi, v in zip(x - w / 2, a):
            ax.text(xi, v + 0.01, f"{v:.3f}", ha="center", fontsize=9.5)
        for xi, v in zip(x + w / 2, b):
            ax.text(xi, v + 0.01, f"{v:.3f}", ha="center", fontsize=9.5)
        ax.set_xticks(x, labels)
        ax.set_ylim(0, max(a + b) * 1.25)
        ax.legend(frameon=False, fontsize=10)
        style_axes(ax, ylabel="留一省中位 R²", title="加入气候变量没有带来增量")
        save(fig, pdf, "fig3_incremental")

        # 图 4 特征重要性
        fig, ax = plt.subplots(figsize=(9, 4.6))
        names = [f for f, _ in importance]
        vals = [v for _, v in importance]
        ax.barh(names, vals, color=GREEN, height=0.6)
        for i, v in enumerate(vals):
            ax.text(v + 0.005, i, f"{v:.3f}", va="center", fontsize=9.5)
        style_axes(ax, xlabel="特征重要性", title="模型依赖的是规模变量（全样本训练）")
        save(fig, pdf, "fig4_importance")

        # 图 5 预测 vs 实际
        fig, ax = plt.subplots(figsize=(7.6, 6.4))
        off = preds_off[preds_off["official"]]
        est = preds_off[~preds_off["official"]]
        ax.scatter(off["actual"], off["pred"], s=16, color=NAVY, alpha=0.75, label="官方值样本", edgecolors="none")
        if len(est):
            ax.scatter(est["actual"], est["pred"], s=16, color=ORANGE, alpha=0.75, label="估算值样本", edgecolors="none")
        lo = min(preds_off["actual"].min(), preds_off["pred"].min())
        hi = max(preds_off["actual"].max(), preds_off["pred"].max())
        ax.plot([lo, hi], [lo, hi], color=GRAY, linestyle="--", linewidth=1.2)
        r2 = r2_score(preds_off["actual"], preds_off["pred"])
        ax.text(0.04, 0.93, f"合并 R² = {r2:.3f}", transform=ax.transAxes, fontsize=11, color="#12352A")
        ax.legend(frameon=False, fontsize=10, loc="lower right")
        style_axes(ax, xlabel="实际 log(产量)", ylabel="留一省预测 log(产量)",
                   title="留一省预测与实际的吻合度")
        ax.grid(color="#E3E8E5", linewidth=0.8)
        save(fig, pdf, "fig5_pred_vs_actual")

        # 图 6 协议汇总
        fig, ax = plt.subplots(figsize=(9, 4.2))
        rows = []
        for sub_label, sub in (("全部样本", df), ("仅官方值", official)):
            shuffled = sub.sample(frac=1.0, random_state=0)
            cut = int(len(shuffled) * 0.8)
            _, pred = fit(shuffled.iloc[:cut], shuffled.iloc[cut:], "log_y", LEVEL_FEATS)
            rand = r2_score(shuffled.iloc[cut:]["log_y"], pred)
            yrs = []
            for year in sorted(sub["年份"].unique()):
                test, train = sub[sub["年份"] == year], sub[sub["年份"] != year]
                if len(test) < 10:
                    continue
                _, p2 = fit(train, test, "log_y", LEVEL_FEATS)
                yrs.append(r2_score(test["log_y"], p2))
            rows.append((sub_label, rand, float(np.median(yrs)), float(np.median([v for _, _, v in (folds_all if sub_label == "全部样本" else folds_off)]))))
        labels = [r[0] for r in rows]
        y = np.arange(len(labels))
        protos = [("随机 8:2", 1, GREEN), ("留一年", 2, ORANGE), ("留一省", 3, NAVY)]
        for name, idx, color in protos:
            vals = [r[idx] for r in rows]
            ax.scatter(vals, y, s=120, color=color, label=name, zorder=3)
            for v, yi in zip(vals, y):
                ax.text(v, yi - 0.16, f"{v:.3f}", ha="center", fontsize=9.5, color=color)
        ax.set_yticks(y, labels)
        ax.set_ylim(-0.6, len(labels) - 0.4)
        ax.set_xlim(0, 1.05)
        ax.legend(frameon=False, fontsize=10, ncol=3, loc="lower center")
        style_axes(ax, xlabel="R²", title="三种验证协议对比")
        ax.grid(axis="x", color="#E3E8E5", linewidth=0.8)
        ax.grid(axis="y", visible=False)
        save(fig, pdf, "fig6_protocols")

    print(f"figures -> {OUT_DIR}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
