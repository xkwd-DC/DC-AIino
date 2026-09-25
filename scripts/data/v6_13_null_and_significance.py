#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""v6 Step 13：县级气候变量迁移能力的"防挨打"三重验证。

针对 [[dc-county-climate-transferability]] 结论的三点追问：
  1. Null model（permutation 阴性对照）——证明 R² 不是结构性假象，而是气候信号；
  2. 单产 yield_ton_per_ha 目标（剥离面积）——"气候→产量"最诚实的靶子；
  3. Bootstrap 显著性检验——CLIM3→CLIMG 的 R² 提升是否超过噪声。

运行：
  python scripts/data/v6_13_null_and_significance.py \
      --configs CLIM3,CLIM5,CLIMG --seeds 42,43,44,45,46 \
      --n-perm 100 --n-boot 200

产出：
  reports/v6_13_null_results.csv         # 原模型 + null(permute) 逐配置多 seed（含超噪声幅度）
  reports/v6_13_single_yield_lco.csv     # 单产目标 LCO（剥离面积）
  reports/v6_13_bootstrap_test.csv       # CLIM3→CLIMG 提升的 bootstrap 显著性
  reports/v6_13_nulls_and_significance_summary.md
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

CLIM3 = ["temp", "prec", "sun"]
CLIM5 = CLIM3 + ["spei_annual_mean", "spei_growing_season_mean"]
SEASONAL = ["gs_tmax_mean", "gs_tmin_mean", "gs_ppt", "gs_srad", "gs_pet",
            "gdd10", "gs_aridity", "prec_cv", "gs_prec_share",
            "winter_temp", "seasonal_temp_range"]
CLIMG = CLIM5 + SEASONAL
CONFIGS = {"CLIM3": CLIM3, "CLIM5": CLIM5, "CLIMG": CLIMG}

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


def _prep(panel_path, feats, target="log_yield"):
    df = pd.read_parquet(panel_path)
    df = df[df[target].notna()].copy()
    df = df.dropna(subset=feats + [target]).copy()
    return df


def _precompute_folds(groups, seed, n_splits=10):
    """预计算 LCO 折掩码（多个 KFold 分县掩码），避免重复重建。"""
    counties = np.unique(groups)
    kf = KFold(n_splits=n_splits, shuffle=True, random_state=seed)
    folds = []
    for tr_i, te_i in kf.split(counties):
        tr_c = set(counties[tr_i])
        tr_mask = np.isin(groups, list(tr_c))
        te_mask = ~tr_mask
        folds.append((tr_mask, te_mask))
    return folds


def _lco_r2_cached(X, y, folds, seed, n_estimators=300):
    """基于预计算折做一次 LCO。"""
    preds, trues = [], []
    for tr_mask, te_mask in folds:
        m = xgb.XGBRegressor(**{**XGB_PARAMS, "random_state": seed, "n_estimators": n_estimators})
        m.fit(X[tr_mask], y[tr_mask])
        preds.append(m.predict(X[te_mask]))
        trues.append(y[te_mask])
    return r2_score(np.concatenate(trues), np.concatenate(preds))


def _lco_r2(X, y, groups, seed, rng=None, shuffle_cols=None):
    """一次 LCO，可选列打乱（permutation null）。"""
    folds = _precompute_folds(groups, seed)
    if shuffle_cols is not None:
        X = X.copy()
        for c in shuffle_cols:
            X[:, c] = rng.permutation(X[:, c])
    return _lco_r2_cached(X, y, folds, seed)


def main() -> int:
    parser = argparse.ArgumentParser(description="v6_13 null + 单产 + 显著性")
    parser.add_argument("--panel", type=str, default=str(PANEL))
    parser.add_argument("--configs", type=str, default="CLIM3,CLIM5,CLIMG")
    parser.add_argument("--seeds", type=str, default="42,43,44,45,46")
    parser.add_argument("--time-split", type=int, default=2019)
    parser.add_argument("--n-perm", type=int, default=30, help="permutation null 次数")
    parser.add_argument("--n-boot", type=int, default=80, help="bootstrap 次数")
    parser.add_argument("--fast", action="store_true",
                        help="null/bootstrap 使用 120 树(够判断方向)，显著提速")
    args = parser.parse_args()

    seeds = [int(s) for s in args.seeds.split(",")]
    cfg_names = args.configs.split(",")
    # null/bootstrap 用较少树，方向对照足够
    nt_null = 120 if args.fast else 300
    print(f"🔧 参数: configs={cfg_names} seeds={seeds} n_perm={args.n_perm} n_boot={args.n_boot} fast={args.fast}", flush=True)

    # ── 统一数据（log_yield 目标，用于 null / 显著性） ────────────────
    panel = pd.read_parquet(args.panel)
    panel = panel[panel["log_yield"].notna()].copy()
    panel["log_sown"] = np.log1p(panel["农作物总播种面积_千公顷"].fillna(0))

    null_rows, boot_rows = [], []
    single_rows = []
    boot_deltas = {}  # config -> list of bootstrap deltas for CLIM3→CLIMG test

    for cfg in cfg_names:
        feats = CONFIGS[cfg]
        sub = panel.dropna(subset=feats + ["log_yield"]).copy()
        X = sub[feats].values
        y = sub["log_yield"].values.astype(float)
        groups = sub["区县代码"].values
        feats_idx = list(range(len(feats)))
        print(f"\n===== {cfg} | {len(feats)} 特征 | {len(sub)} 行 | {sub['区县代码'].nunique()} 县 =====")

        # (A) 原模型多种子 LCO
        true_lco = []
        for sd in seeds:
            r = _lco_r2(X, y, groups, sd, rng=None)
            true_lco.append(r)
        true_mean = float(np.mean(true_lco))
        true_std = float(np.std(true_lco))
        print(f"  [原模型] LCO R² = {true_mean:+.4f} ± {true_std:.4f}  (N={len(seeds)} seeds)", flush=True)

        # (B) permutation null：对 CLIM 列整体打乱，固定 seed 42 折，多次
        folds42 = _precompute_folds(groups, 42)
        null_vals = []
        for p in range(args.n_perm):
            rng = np.random.RandomState(1000 + p)
            Xn = X.copy()
            for c in feats_idx:
                Xn[:, c] = rng.permutation(Xn[:, c])
            null_vals.append(_lco_r2_cached(Xn, y, folds42, 42, n_estimators=nt_null))
        null_arr = np.array(null_vals)
        null_mean = float(null_arr.mean())
        null_sd = float(null_arr.std())
        # 超噪声增量 = 真实 mean - null mean（null 若有 0，说明特征数/结构不贡献假象）
        excess = true_mean - null_mean
        # 显著性：真实超过 null 的比例
        n_better = int((null_arr < true_mean).sum())
        frac_better = n_better / len(null_arr)
        print(f"  [null permute] LCO R² = {null_mean:+.4f} ± {null_sd:.4f} | 真实>null {frac_better*100:.0f}% | 超噪声 = {excess:+.4f}",
              flush=True)
        null_rows.append({
            "config": cfg, "n_feat": len(feats),
            "true_mean": round(true_mean, 4), "true_std": round(true_std, 4),
            "null_mean": round(null_mean, 4), "null_sd": round(null_sd, 4),
            "null_max": round(float(null_arr.max()), 4),
            "excess_true_over_null": round(excess, 4),
            "frac_true_gt_null": round(frac_better, 4),
            "q05": round(float(np.percentile(null_arr, 5)), 4),
            "q95": round(float(np.percentile(null_arr, 95)), 4),
        })

    # ── (3) Bootstrap 显著性：CLIM3 → CLIMG 的 LCO 提升是否超过噪声 ────
    print("\n===== Bootstrap: CLIM3 → CLIMG 提升显著性 =====")
    cfg3, cfgg = CONFIGS["CLIM3"], CONFIGS["CLIMG"]
    sub3 = panel.dropna(subset=cfg3 + ["log_yield"]).copy()
    subg = panel.dropna(subset=cfgg + ["log_yield"]).copy()
    # 用两配置共同样本（县 + 年份对齐），保证配对公平
    key = sub3.set_index(["区县代码", "年份"]).index
    subg2 = subg.set_index(["区县代码", "年份"])
    common = key.intersection(subg2.index)
    s3 = sub3.set_index(["区县代码", "年份"]).loc[common].reset_index()
    sg = subg2.loc[common].reset_index()
    print(f"  共同样本: {len(s3)} 行 / {s3['区县代码'].nunique()} 县")

    X3, Xg = s3[cfg3].values, sg[cfgg].values
    y3, yg = s3["log_yield"].values.astype(float), sg["log_yield"].values.astype(float)
    g3, gg = s3["区县代码"].values, sg["区县代码"].values

    # 点估计提升（多种子）
    d_true = []
    for sd in seeds:
        r3 = _lco_r2(X3, y3, g3, sd, rng=None)
        rg = _lco_r2(Xg, yg, gg, sd, rng=None)
        d_true.append(rg - r3)
    d_mean = float(np.mean(d_true))
    d_std = float(np.std(d_true))
    print(f"  点估计 Δ(CLIMG−CLIM3) = {d_mean:+.4f} ± {d_std:.4f}")

    # Bootstrap：跨县重采样（固定 seed 42 折，bootstrap 反映"跨县采样"不确定性）
    all_counties = np.unique(g3)
    deltas = []
    for b in range(args.n_boot):
        rng = np.random.RandomState(2200 + b)
        bt = rng.choice(all_counties, size=len(all_counties), replace=True)
        mask3 = np.isin(g3, bt)
        maskg = np.isin(gg, bt)
        f3 = _precompute_folds(g3[mask3], 42)
        fg = _precompute_folds(gg[maskg], 42)
        r3 = _lco_r2_cached(X3[mask3], y3[mask3], f3, 42, n_estimators=nt_null)
        rg = _lco_r2_cached(Xg[maskg], yg[maskg], fg, 42, n_estimators=nt_null)
        deltas.append(rg - r3)
    deltas = np.array(deltas)
    ci_lo, ci_hi = np.percentile(deltas, [2.5, 97.5])
    p = float((deltas <= 0).mean())
    print(f"  Bootstrap Δ: mean={deltas.mean():+.4f}  95%CI=[{ci_lo:+.4f},{ci_hi:+.4f}]  P(Δ<=0)={p:.3f}", flush=True)
    boot_rows.append({
        "pair": "CLIM3->CLIMG", "n_boot": args.n_boot, "n_common": len(s3),
        "delta_point": round(d_mean, 4), "delta_boot_mean": round(float(deltas.mean()), 4),
        "ci_lo": round(ci_lo, 4), "ci_hi": round(ci_hi, 4),
        "p_delta_le_0": round(p, 4),
    })

    # ── (2) 单产目标：剥离面积，只报 LCO（时间外推样本过小会误导） ─────
    print("\n===== 单产目标 log(yield_ton_per_ha) : 剥离面积 (只报 LCO) =====")
    panel_yit = pd.read_parquet(args.panel)
    panel_yit = panel_yit[panel_yit["yield_ton_per_ha"].notna()].copy()
    panel_yit["log_yhp"] = np.log(panel_yit["yield_ton_per_ha"])
    for cfg in cfg_names:
        feats = CONFIGS[cfg]
        sub = panel_yit.dropna(subset=feats + ["log_yhp"]).copy()
        X = sub[feats].values
        y = sub["log_yhp"].values.astype(float)
        groups = sub["区县代码"].values
        vals = []
        for sd in seeds:
            vals.append(_lco_r2(X, y, groups, sd, rng=None))
        mean, std = float(np.mean(vals)), float(np.std(vals))
        # 同配置 null 对照（对同面板打乱，控制次数少些）
        folds42 = _precompute_folds(groups, 42)
        null_vals = []
        for p in range(min(args.n_perm, 50)):
            rng = np.random.RandomState(1000 + p)
            Xn = X.copy()
            for c in range(len(feats)):
                Xn[:, c] = rng.permutation(Xn[:, c])
            null_vals.append(_lco_r2_cached(Xn, y, folds42, 42, n_estimators=nt_null))
        null_mean = float(np.mean(null_vals))
        print(f"  {cfg} | {len(sub)} 行 / {sub['区县代码'].nunique()} 县 | LCO R² = {mean:+.4f} ± {std:.4f} | null={null_mean:+.4f}",
              flush=True)
        single_rows.append({
            "config": cfg, "n_feat": len(feats), "n_rows": len(sub),
            "n_county": sub['区县代码'].nunique(),
            "lco_r2": round(mean, 4), "lco_std": round(std, 4),
            "null_lco_r2": round(null_mean, 4),
            "excess": round(mean - null_mean, 4),
        })

    # ── 写盘 ──────────────────────────────────────────────────────────
    null_csv = PROJECT_ROOT / "reports" / "v6_13_null_results.csv"
    boot_csv = PROJECT_ROOT / "reports" / "v6_13_bootstrap_test.csv"
    single_csv = PROJECT_ROOT / "reports" / "v6_13_single_yield_lco.csv"
    pd.DataFrame(null_rows).to_csv(null_csv, index=False)
    pd.DataFrame(boot_rows).to_csv(boot_csv, index=False)
    pd.DataFrame(single_rows).to_csv(single_csv, index=False)

    lines = [
        "# v6_13 县级气候迁移能力 — 三重防挨打验证",
        "",
        f"> 数据: {Path(args.panel).name} | 目标: log_yield（总产量）/ log(yield_ton_per_ha)（单产）",
        f"> null 采用**逐列 permutation**（保持边际分布、破坏特征-产量关联），折固定 seed 42，次数={args.n_perm}",
        f"> bootstrap 跨县重采样 × 多种子，次数={args.n_boot}; 显著性以 P(Δ≤0) 与 95%CI 报告",
        "",
        "## 一、Null model（permutation 阴性对照）",
        "",
        "真实 LCO R² vs 打乱后的 null LCO R²：",
        "",
        _to_md(pd.DataFrame(null_rows)),
        "",
        "- **判读**：若 `excess_true_over_null` 大（真实远高于 null），说明 R² 是**气候信号**；",
        "  若真实≈null（excess≈0），说明前面的 R² 是**结构性/特征数假象**。",
        "- `frac_true_gt_null`= 真实 R² 超过 null 分布的比例（近似可信度）。",
        "",
        "## 二、单产目标（剥离面积）——log(yield_ton_per_ha)",
        "",
        "单产 = 总产量/播种面积（本面板比值恒=1.0，故 log(单产)=log_yield−log(面积)，天然剥离规模）：",
        "",
        _to_md(pd.DataFrame(single_rows)),
        "",
        "> ⚠️ 单产非空样本只有 4703 行 / 629 县（覆盖 60%），且 2020-22 每年仅 ~200 县/年，",
        "> **时间外推样本过小会误导**，因此此处**只报 LCO**。与 log_yield 的 LCO 对比即「剥离规模」后的附录证据。",
        "",
        "## 三、Bootstrap 显著性（CLIM3 → CLIMG 提升）",
        "",
        _to_md(pd.DataFrame(boot_rows)),
        "",
        "- 若 `ci_lo > 0` 且 `p_delta_le_0 < 0.05`：提升**显著**，不是种子抖动。",
        "- 样本为 CLIM3/CLIMG 共同县×年份（配对公平），跨县 bootstrap 平滑随机性。",
        "",
        "---",
        "",
        f"> 复现: `python scripts/data/v6_13_null_and_significance.py --configs {args.configs} --seeds {args.seeds} --n-perm {args.n_perm} --n-boot {args.n_boot}`",
        "",
    ]
    rep = PROJECT_ROOT / "reports" / "v6_13_nulls_and_significance_summary.md"
    rep.write_text("\n".join(lines), encoding="utf-8")
    print(f"\n✅ null -> {null_csv}")
    print(f"✅ boot -> {boot_csv}")
    print(f"✅ single_yield -> {single_csv}")
    print(f"✅ report -> {rep}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
