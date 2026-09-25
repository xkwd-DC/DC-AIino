#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""v6 Step 12：县级气候变量的可迁移产量解释能力 — 干净隔离实验。

研究问题：县级气候变量（不含播种面积/规模、不含省-年共享常量）是否具有
可迁移的产量解释能力？迁移 = 空间(LCO) + 时间(≤2019→2020-22) 双口径。

设计（逐步隔离混淆）：
  CLIM3   : 纯县级气候 3 维      temp / prec / sun
  CLIM5   : CLIM3 + 县级 SPEI ×2 (spei_annual_mean / spei_growing_season_mean)
  CLIMG   : CLIM5 + 生长季/极端指数 (gs_* / gdd10 / gs_aridity 等)
  CLIMG+S : CLIMG + log_sown (规模/播种面积)   ← 曝露"规模"是否在背解释力
  CLIMG+P : CLIMG + 省-年共享常量 (原 10 省特征) ← 曝露"省常量"贡献 (原"官方"口径)

目标: log_yield = log(粮食总产量_吨)  (与原报告可比)
  * 同时打印 log_yield 方差中被播种面积 vs 单产解释的份额，说明 log_yield 口径的局限。

协议: LCO 10 折按县分组 + 时间外推(≤2019→2020-22)；种子 42-46。
输出: reports/v6_12_climate_transfer_{nfeat}.csv + reports/v6_12_climate_transfer_summary.md
"""
import argparse
import json
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
import shap

PROJECT_ROOT = Path(__file__).resolve().parents[2]
PANEL = PROJECT_ROOT / "data" / "interim" / "paper_panel_v7_prediction.parquet"

# ── 县级气候(纯) ─────────────────────────────────────────────────────────
CLIM3 = ["temp", "prec", "sun"]
CLIM5 = CLIM3 + ["spei_annual_mean", "spei_growing_season_mean"]
SEASONAL = ["gs_tmax_mean", "gs_tmin_mean", "gs_ppt", "gs_srad", "gs_pet",
            "gdd10", "gs_aridity", "prec_cv", "gs_prec_share",
            "winter_temp", "seasonal_temp_range"]
CLIMG = CLIM5 + SEASONAL

# 省-年共享常量（原"官方"特征，非县级）
PROV_SHARED = ["ndvi_yearly", "ndvi_summer_peak",
               "lst_day_growing_mean_k", "lst_night_growing_mean_k",
               "fert", "irr", "flood", "drou_a", "flood_a", "cropland_ratio"]

CONFIGS = {
    "CLIM3": CLIM3,
    "CLIM5": CLIM5,
    "CLIMG": CLIMG,
    "CLIMG+S": CLIMG + ["log_sown"],
    "CLIMG+P": CLIMG + PROV_SHARED,
}

XGB_PARAMS = {
    "n_estimators": 300, "max_depth": 5, "learning_rate": 0.05,
    "subsample": 0.8, "colsample_bytree": 0.8,
    "reg_alpha": 0.1, "reg_lambda": 1.0,
    "n_jobs": -1,
}


def _to_md(df: pd.DataFrame) -> str:
    cols = list(df.columns)
    header = "| " + " | ".join(str(c) for c in cols) + " |"
    sep = "|" + "|".join("---" for _ in cols) + "|"
    body = "\n".join("| " + " | ".join(str(v) for v in row) + " |"
                     for row in df.itertuples(index=False))
    return "\n".join([header, sep, body])


def _variance_share(df: pd.DataFrame) -> dict:
    """log_yield 方差被 播种面积(log) 和 单产(log yield_ton_per_ha) 解释多少。"""
    d = df.dropna(subset=["yield_ton_per_ha"]).copy()
    d["log_area"] = np.log1p(d["农作物总播种面积_千公顷"].fillna(0))
    d["log_yhp"] = np.log(d["yield_ton_per_ha"])
    out = {}
    out["n"] = len(d)
    out["var_logy"] = float(d["log_yield"].var())
    out["corr_area"] = float(np.corrcoef(d["log_yield"], d["log_area"])[0, 1])
    out["corr_yhp"] = float(np.corrcoef(d["log_yield"], d["log_yhp"])[0, 1])
    # log_yield ≈ log_area + log_yhp ；面积解释份额 = cov(y,area)/var(y)
    c = np.polyfit(d["log_area"], d["log_yield"], 1)
    cov = float(np.cov(d["log_area"], d["log_yield"])[0, 1])
    out["share_area"] = float(c[0] * cov / d["log_yield"].var())
    return {k: round(v, 4) for k, v in out.items()}


def _shap_sign_consistency(X_tr, y_tr, X_te, y_te, feats, params, sample=2000) -> dict:
    """训练(≤2019)模型 → 对训练集/测试集(2020-22)分别计算特征 SHAP 均值，
    报告每个气候特征在 train/test 是否同号(time 不变)、以及主导特征方向。"""
    model = xgb.XGBRegressor(**params)
    model.fit(X_tr, y_tr)
    expl = shap.TreeExplainer(model)
    idx_tr = np.random.RandomState(0).choice(len(X_tr), size=min(sample, len(X_tr)), replace=False)
    idx_te = np.random.RandomState(0).choice(len(X_te), size=min(sample, len(X_te)), replace=False)
    sh_tr = expl.shap_values(X_tr[idx_tr]) if hasattr(expl, "shap_values") else None
    sh_te = expl.shap_values(X_te[idx_te]) if hasattr(expl, "shap_values") else None
    if sh_tr is None or sh_te is None:
        return {}
    m_tr = np.asarray(sh_tr).mean(axis=0)
    m_te = np.asarray(sh_te).mean(axis=0)
    signs = {}
    for i, f in enumerate(feats):
        signs[f] = {
            "train_shap": round(float(m_tr[i]), 4),
            "test_shap": round(float(m_te[i]), 4),
            "same_sign": bool(np.sign(m_tr[i]) == np.sign(m_te[i])) and abs(m_tr[i]) > 1e-8,
        }
    return {"signs": signs}


def main() -> int:
    parser = argparse.ArgumentParser(description="县级气候变量可迁移产量解释能力")
    parser.add_argument("--panel", type=str, default=str(PANEL))
    parser.add_argument("--seeds", type=str, default="42,43,44,45,46")
    parser.add_argument("--configs", type=str, default="CLIM3,CLIM5,CLIMG,CLIMG+S,CLIMG+P")
    parser.add_argument("--time-split", type=int, default=2019)
    args = parser.parse_args()

    df = pd.read_parquet(args.panel)
    df = df[df["log_yield"].notna()].copy()
    df["log_sown"] = np.log1p(df["农作物总播种面积_千公顷"].fillna(0))

    print("== 产量口径诊断 ==")
    print(json.dumps(_variance_share(df), ensure_ascii=False))

    seeds = [int(s) for s in args.seeds.split(",")]
    cfg_names = args.configs.split(",")
    outcome = []          # 汇总表 (config × seed)
    shap_rows = []        # 时间模型 SHAP 符号一致性 (取 seed42 首个 config 之外每个 config)

    for cfg in cfg_names:
        feats = CONFIGS[cfg]
        ok = [f for f in feats if f in df.columns]
        if len(ok) != len(feats):
            print(f"[跳过] {cfg}: 缺列 {set(feats) - set(ok)}")
            continue
        sub = df.dropna(subset=ok + ["log_yield"]).copy()
        X = sub[ok].values
        y = sub["log_yield"].values.astype(float)
        groups = sub["区县代码"].values
        counties = np.unique(groups)
        print(f"\n===== {cfg} | {len(ok)} 特征 | {len(sub)} 行 | {len(counties)} 县 =====")

        for seed in seeds:
            params = {**XGB_PARAMS, "random_state": seed}
            kf = KFold(n_splits=10, shuffle=True, random_state=seed)
            preds, trues = [], []
            for fold, (tr_i, te_i) in enumerate(kf.split(counties)):
                tr_c = set(counties[tr_i])
                tr_mask = np.isin(groups, list(tr_c))
                te_mask = ~tr_mask
                model = xgb.XGBRegressor(**params)
                model.fit(X[tr_mask], y[tr_mask])
                p = model.predict(X[te_mask])
                preds.append(p)
                trues.append(y[te_mask])
                _ = fold
            lco_r2 = r2_score(np.concatenate(trues), np.concatenate(preds))
            lco_rmse = mean_squared_error(np.concatenate(trues), np.concatenate(preds), squared=False)

            tr_t = (sub["年份"] <= args.time_split).values
            te_t = ~tr_t
            model_t = xgb.XGBRegressor(**params)
            model_t.fit(X[tr_t], y[tr_t])
            p_t = model_t.predict(X[te_t])
            time_r2 = r2_score(y[te_t], p_t)
            time_rmse = mean_squared_error(y[te_t], p_t, squared=False)

            outcome.append({
                "config": cfg, "n_feat": len(ok), "seed": seed,
                "lco_r2": round(lco_r2, 4), "lco_rmse": round(lco_rmse, 4),
                "time_r2": round(time_r2, 4), "time_rmse": round(time_rmse, 4),
            })
            print(f"  seed {seed}: LCO R²={lco_r2:+.4f}  时间外推 R²={time_r2:+.4f}")

        # SHAP 符号一致性（每 config 固定 seed 42 的时间模型）
        tr_t = (sub["年份"] <= args.time_split).values
        te_t = ~tr_t
        params42 = {**XGB_PARAMS, "random_state": 42}
        sh = _shap_sign_consistency(X[tr_t], y[tr_t], X[te_t], y[te_t], ok, params42)
        for f, s in sh.get("signs", {}).items():
            shap_rows.append({"config": cfg, "feature": f, **s})

    out_csv = PROJECT_ROOT / "reports" / "v6_12_climate_transfer_results.csv"
    shap_csv = PROJECT_ROOT / "reports" / "v6_12_climate_transfer_shap_signs.csv"
    pd.DataFrame(outcome).to_csv(out_csv, index=False)
    pd.DataFrame(shap_rows).to_csv(shap_csv, index=False)

    # 汇总：每 config 多种子 mean±std
    o = pd.DataFrame(outcome)
    agg = (o.groupby("config", sort=False)
             .agg(n_feat=("n_feat", "first"),
                  lco_r2_mean=("lco_r2", "mean"), lco_r2_std=("lco_r2", "std"),
                  time_r2_mean=("time_r2", "mean"), time_r2_std=("time_r2", "std"))
             .reset_index())
    agg["lco_r2"] = agg["lco_r2_mean"].map("{:+.4f}".format) + " ± " + agg["lco_r2_std"].map("{:.4f}".format)
    agg["time_r2"] = agg["time_r2_mean"].map("{:+.4f}".format) + " ± " + agg["time_r2_std"].map("{:.4f}".format)
    agg = agg.drop(columns=["lco_r2_mean", "lco_r2_std", "time_r2_mean", "time_r2_std"])

    lines = [
        "# 县级气候变量的可迁移产量解释能力 — 隔离实验报告",
        "",
        f"> 数据: {Path(args.panel).name} | 目标: log_yield = log(粮食总产量_吨)",
        f"> 协议: LCO 10 折按县分组 + 时间外推(≤{args.time_split} → 之后); 种子 {', '.join(map(str, seeds))}",
        f"> 混淆控制: 所有 CLIM* 配置均**不含** 播种面积/规模(log_sown) 与 省-年共享常量;",
        "  `CLIMG+S`/`CLIMG+P` 仅为对照，用于曝露「规模/省常量」在背解释力。",
        "",
        "## 产量口径诊断（为什么必须隔离）",
        "",
        "log_yield 是被「规模(播种面积)」主导的总量指标，若直接报「气候解释力」会失真：",
        "",
        f"- 样本(n=有单产): {_variance_share(df)['n']}，log_yield 方差 = {_variance_share(df)['var_logy']}",
        f"- log_yield 与 log(播种面积) 相关 = {_variance_share(df)['corr_area']}；与 log(单产) 相关 = {_variance_share(df)['corr_yhp']}",
        f"- 播种面积(log) 对 log_yield 方差的**解释份额 ≈ {_variance_share(df)['share_area']*100:.0f}%**",
        "",
        "## 迁移能力汇总（mean ± std，5 种子）",
        "",
        _to_md(agg),
        "",
        "| 配置 | 含义 |",
        "|---|---|",
        "| CLIM3 | 纯县级气候 3 维（temp/prec/sun），无规模、无省常量 |",
        "| CLIM5 | + 县级 SPEI ×2 |",
        "| CLIMG | + 生长季/极端指数（gs_*/gdd10/gs_aridity） |",
        "| CLIMG+S | CLIMG + 播种面积（规模）——曝露规模在背解释力 |",
        "| CLIMG+P | CLIMG + 省-年共享常量——原「官方」口径 |",
        "",
        "> 判读：**LCO R²** = 跨县空间迁移（能否解释未见县）；**时间外推 R²** = 跨时间迁移（能否解释未来年）。",
        "> 若纯气候 CLIM* 的 LCO/time 显著为正，则县级气候变量**具备**可迁移解释能力；",
        "> 若 CLIMG+S/P 比 CLIMG 高很多，说明**表面上**的「气候解释力」实际由规模/省常量承担。",
        "",
        "## 气候特征 SHAP 方向一致性（seed 42 时间模型，train≤2019 vs test>2019）",
        "",
        "同一气候特征在训练期(过去)与测试期(未来)的 SHAP 均值符号是否一致：",
        "- `same_sign=True` 且为气候主效应：该特征的**解释方向可跨时间迁移**（如「降水↑→产量↑」在未来仍成立）；",
        "- `same_sign=False` 或出现翻转：跨时间解释方向不稳定，需谨慎表述。",
        "",
        _to_md(pd.DataFrame(shap_rows)),
        "",
        "---",
        "",
        "> 复现: `python scripts/data/v6_12_climate_transfer.py --configs CLIM3,CLIM5,CLIMG,CLIMG+S,CLIMG+P --seeds 42,43,44,45,46`",
        "",
    ]
    rep = PROJECT_ROOT / "reports" / "v6_12_climate_transfer_summary.md"
    rep.write_text("\n".join(lines), encoding="utf-8")
    print(f"\n✅ 结果 -> {out_csv}")
    print(f"✅ SHAP -> {shap_csv}")
    print(f"✅ 报告 -> {rep}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
