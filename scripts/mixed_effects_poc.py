"""混合效应模型 v1 PoC — Issue #42 (熊鑫)

目的：定量证明 R²=0.907 中省份固定效应贡献多少 vs climate 边际效应贡献多少。
**不是**为了把 R² 推得更高。

模型：y_it = α_i + β X_it + ε_it
  - α_i: 31 省 random intercept
  - β:    11 维 fixed slope (climate 边际效应,跨省共享)
  - ε_it: 残差噪声

实施：按 docs/coord/2026-05-26_混合效应模型_PoC_计划.md §3 五步。

跑法：/tmp/dc-mixed/bin/python scripts/mixed_effects_poc.py
产出：
  - backend/models/mixed_effects_v1_results.json
  - backend/models/mixed_effects_v1_alpha.csv
  - backend/models/mixed_effects_v1_beta.csv
"""
from __future__ import annotations

import json
import hashlib
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd
import statsmodels.api as sm
import statsmodels.formula.api as smf
from scipy.stats import chi2

# ─── 路径 ──────────────────────────────────────────────────────────────────
DATA_PATH = Path("data/interim/paper_panel_v3.parquet")
OUT_DIR = Path("backend/models")
OUT_DIR.mkdir(parents=True, exist_ok=True)

# ─── 配置(与 PoC 计划 §2 对接) ─────────────────────────────────────────────
FEATURES = ["irr", "flood", "sun", "temp", "spei", "prec",
            "mech", "fert", "drou_a", "flood_a", "ndvi"]
FEATURES_DISPLAY = {
    "irr": "Irr", "flood": "Flood_R", "sun": "Sun", "temp": "Temp",
    "spei": "SPEI", "prec": "Prec", "mech": "Mech", "fert": "Fert",
    "drou_a": "Drou_A", "flood_a": "Flood_A", "ndvi": "NDVI",
}
TARGET = "yield_kg_per_ha"
GROUP_KEY = "province"

REML = True
OPTIMIZER = "lbfgs"
SEED = 2026
BOOTSTRAP_N = 200

# ─── §3.2 数据准备 ─────────────────────────────────────────────────────────
print("=" * 72)
print(f"§3.2 加载数据 — {DATA_PATH}")
print("=" * 72)

df = pd.read_parquet(DATA_PATH)
data_md5 = hashlib.md5(DATA_PATH.read_bytes()).hexdigest()[:12]
print(f"规模: {df.shape[0]} 行 × {df.shape[1]} 列  MD5[:12]={data_md5}")
print(f"省份数: {df[GROUP_KEY].nunique()}    年份: {df['year'].min()}-{df['year'].max()}")

n_missing = df[[*FEATURES, TARGET, GROUP_KEY]].isna().sum().sum()
print(f"目标列+11 维 X 缺失计: {n_missing}")
assert n_missing == 0, "PoC 计划禁止静默 dropna,如有缺失先在 card 里报告"

X_raw = df[FEATURES].copy()
X_mean = X_raw.mean()
X_std = X_raw.std(ddof=1)
X_z = (X_raw - X_mean) / X_std

assert X_z.shape == (403, 11), f"shape mismatch: {X_z.shape}"
assert df[GROUP_KEY].nunique() == 31

corr = X_z.corr()
high_corr_pairs = []
for i, f1 in enumerate(FEATURES):
    for f2 in FEATURES[i + 1:]:
        r = corr.loc[f1, f2]
        if abs(r) > 0.7:
            high_corr_pairs.append((f1, f2, float(r)))
print("\n共线性 |ρ|>0.7 对:")
for f1, f2, r in high_corr_pairs:
    print(f"  {f1:>8s} ~ {f2:<8s}  ρ = {r:+.3f}")
if not high_corr_pairs:
    print("  (none)")

# ─── §3.3 Fit MixedLM ──────────────────────────────────────────────────────
print()
print("=" * 72)
print("§3.3 Fit MixedLM — y ~ X + (1|province)  REML+lbfgs")
print("=" * 72)

data = X_z.copy()
data["y"] = df[TARGET].values
data[GROUP_KEY] = df[GROUP_KEY].values

formula = "y ~ " + " + ".join(FEATURES)
md = smf.mixedlm(formula, data, groups=data[GROUP_KEY])
mdf = md.fit(method=[OPTIMIZER], reml=REML)
print(f"converged={mdf.converged}  llf={mdf.llf:.4f}  scale(σ_ε²)={mdf.scale:.4f}")
print(f"σ_α²={mdf.cov_re.iloc[0, 0]:.4f}")
print()
print(mdf.summary())

# ─── §3.4 LRT vs pooled OLS ────────────────────────────────────────────────
print()
print("=" * 72)
print("§3.4 LRT — 混合效应 vs pooled OLS baseline")
print("=" * 72)

md_ml = smf.mixedlm(formula, data, groups=data[GROUP_KEY])
mdf_ml = md_ml.fit(method=[OPTIMIZER], reml=False)
ols = sm.OLS(data["y"], sm.add_constant(data[FEATURES])).fit()
ll_ols = float(ols.llf)
ll_mixed_ml = float(mdf_ml.llf)
LR = 2 * (ll_mixed_ml - ll_ols)
p_chibar = 0.5 * float(chi2.sf(LR, df=1))
p_chi2_1 = float(chi2.sf(LR, df=1))
print(f"  ll_pooled_OLS  = {ll_ols:.4f}")
print(f"  ll_mixed (ML)  = {ll_mixed_ml:.4f}")
print(f"  LR statistic   = {LR:.4f}")
print(f"  p (chi-bar-sq) = {p_chibar:.4g}  ← Self & Liang 1987 边界修正")
print(f"  p (chi²₁)      = {p_chi2_1:.4g}  ← 保守上界")

# ─── §3.5 α / β / ICC ──────────────────────────────────────────────────────
print()
print("=" * 72)
print("§3.5 α_i / β / ICC 提取")
print("=" * 72)

alpha_records = []
for prov, vec in mdf.random_effects.items():
    alpha_records.append({"province": prov, "alpha_hat": float(vec.iloc[0])})
alpha_df = pd.DataFrame(alpha_records).sort_values("alpha_hat").reset_index(drop=True)
alpha_df["rank"] = alpha_df.index + 1
print(f"\nα_i bottom-5 (省份天然单产最低):")
print(alpha_df.head().to_string(index=False))
print(f"\nα_i top-5 (省份天然单产最高):")
print(alpha_df.tail().to_string(index=False))

ci = mdf.conf_int()
beta_records = []
for f in FEATURES:
    beta_records.append({
        "feature": FEATURES_DISPLAY[f],
        "feature_raw": f,
        "beta_hat": float(mdf.fe_params[f]),
        "se": float(mdf.bse_fe[f]),
        "p_value": float(mdf.pvalues[f]),
        "ci_lo": float(ci.loc[f, 0]),
        "ci_hi": float(ci.loc[f, 1]),
        "significant_05": bool(mdf.pvalues[f] < 0.05),
    })
beta_df = pd.DataFrame(beta_records)
print(f"\n11 维 β estimate (REML, sorted by |β|):")
beta_df_sorted = beta_df.reindex(beta_df["beta_hat"].abs().sort_values(ascending=False).index)
print(beta_df_sorted[["feature", "beta_hat", "se", "p_value", "ci_lo", "ci_hi", "significant_05"]]
      .to_string(index=False))

var_alpha = float(mdf.cov_re.iloc[0, 0])
var_eps = float(mdf.scale)
icc = var_alpha / (var_alpha + var_eps)
print(f"\nICC point estimate = σ_α²/(σ_α²+σ_ε²) = {var_alpha:.2f}/({var_alpha:.2f}+{var_eps:.2f}) = {icc:.4f}")

# ICC 95% CI via parametric bootstrap
print(f"\n  Parametric bootstrap ICC 95% CI ({BOOTSTRAP_N} 次)...")
rng = np.random.default_rng(SEED)
icc_boot = []
n_failed = 0
sigma_alpha = float(np.sqrt(var_alpha))
sigma_eps = float(np.sqrt(var_eps))

X_with_const = sm.add_constant(data[FEATURES]).values
fe_full = np.concatenate([[float(mdf.fe_params["Intercept"])],
                          [float(mdf.fe_params[f]) for f in FEATURES]])
fitted_fixed = X_with_const @ fe_full
province_arr = data[GROUP_KEY].values
province_to_idx = {p: i for i, p in enumerate(mdf.random_effects.keys())}
prov_idx_arr = np.array([province_to_idx[p] for p in province_arr])

for b in range(BOOTSTRAP_N):
    alpha_sim = rng.normal(0, sigma_alpha, size=31)
    eps_sim = rng.normal(0, sigma_eps, size=len(data))
    y_sim = fitted_fixed + alpha_sim[prov_idx_arr] + eps_sim
    boot_data = data.copy()
    boot_data["y"] = y_sim
    try:
        md_b = smf.mixedlm(formula, boot_data, groups=boot_data[GROUP_KEY])
        mdf_b = md_b.fit(method=[OPTIMIZER], reml=REML)
        va = float(mdf_b.cov_re.iloc[0, 0])
        ve = float(mdf_b.scale)
        icc_b = va / (va + ve) if (va + ve) > 0 else np.nan
        if np.isfinite(icc_b):
            icc_boot.append(icc_b)
        else:
            n_failed += 1
    except Exception:
        n_failed += 1
    if (b + 1) % 50 == 0:
        print(f"    [{b+1}/{BOOTSTRAP_N}] ok={len(icc_boot)} failed={n_failed}")

icc_boot_arr = np.array(icc_boot)
if len(icc_boot_arr) > 10:
    icc_ci_lo = float(np.percentile(icc_boot_arr, 2.5))
    icc_ci_hi = float(np.percentile(icc_boot_arr, 97.5))
else:
    icc_ci_lo = None
    icc_ci_hi = None
print(f"\n  ICC = {icc:.4f}  95% CI [{icc_ci_lo}, {icc_ci_hi}]  "
      f"(bootstrap n={len(icc_boot)}/{BOOTSTRAP_N}, failed={n_failed})")

# ─── §4.1 持久化 ──────────────────────────────────────────────────────────
print()
print("=" * 72)
print("§4.1 持久化产出物")
print("=" * 72)

alpha_csv = OUT_DIR / "mixed_effects_v1_alpha.csv"
beta_csv = OUT_DIR / "mixed_effects_v1_beta.csv"
results_json = OUT_DIR / "mixed_effects_v1_results.json"

alpha_df.to_csv(alpha_csv, index=False, float_format="%.4f")
beta_df.to_csv(beta_csv, index=False, float_format="%.6f")

results = {
    "issue": 42,
    "model": "MixedLM (y ~ X + (1|province))",
    "data_path": str(DATA_PATH),
    "data_md5_12": data_md5,
    "n_rows": int(len(df)),
    "n_features": len(FEATURES),
    "n_groups": int(df[GROUP_KEY].nunique()),
    "feature_cols_raw": FEATURES,
    "feature_cols_display": [FEATURES_DISPLAY[f] for f in FEATURES],
    "target": TARGET,
    "group_key": GROUP_KEY,
    "estimator": {
        "reml": REML,
        "optimizer": OPTIMIZER,
        "converged": bool(mdf.converged),
        "x_standardization": "z-score (pandas std ddof=1, full-data fit)",
    },
    "variance_components": {
        "sigma_alpha_sq": var_alpha,
        "sigma_eps_sq": var_eps,
    },
    "icc": {
        "point": icc,
        "ci_lo_95": icc_ci_lo,
        "ci_hi_95": icc_ci_hi,
        "bootstrap_n_used": int(len(icc_boot)),
        "bootstrap_n_failed": int(n_failed),
        "bootstrap_n_target": BOOTSTRAP_N,
        "bootstrap_seed": SEED,
    },
    "lrt": {
        "ll_pooled_ols": ll_ols,
        "ll_mixed_ml": ll_mixed_ml,
        "lr_statistic": float(LR),
        "p_value_chibar": p_chibar,
        "p_value_chi2_1": p_chi2_1,
        "df_chibar": 1,
        "note": "Self & Liang 1987 边界 chi-bar-square 修正",
    },
    "intercept_fixed": float(mdf.fe_params["Intercept"]),
    "loglik_mixed_reml": float(mdf.llf),
    "alpha_summary": {
        "min": float(alpha_df["alpha_hat"].min()),
        "max": float(alpha_df["alpha_hat"].max()),
        "range": float(alpha_df["alpha_hat"].max() - alpha_df["alpha_hat"].min()),
        "std": float(alpha_df["alpha_hat"].std()),
    },
    "beta": [
        {k: r[k] for k in ["feature", "feature_raw", "beta_hat", "se", "p_value",
                            "ci_lo", "ci_hi", "significant_05"]}
        for r in beta_records
    ],
    "alpha": alpha_df.to_dict(orient="records"),
    "high_corr_pairs": [
        {"f1": f1, "f2": f2, "rho": r} for f1, f2, r in high_corr_pairs
    ],
    "x_zscore_stats": {
        "mean": {f: float(X_mean[f]) for f in FEATURES},
        "std": {f: float(X_std[f]) for f in FEATURES},
    },
    "generated_at": datetime.now().isoformat(timespec="seconds"),
    "script": "scripts/mixed_effects_poc.py",
}

results_json.write_text(json.dumps(results, ensure_ascii=False, indent=2))

for p in [alpha_csv, beta_csv, results_json]:
    print(f"  ✓ {p}  ({p.stat().st_size:,} bytes)")

print()
print("=" * 72)
n_sig = sum(1 for r in beta_records if r["significant_05"])
top_feat = beta_df_sorted.iloc[0]
print(
    f"PoC headline: ICC = {icc:.4f}  "
    f"95% CI [{icc_ci_lo}, {icc_ci_hi}]"
)
print(
    f"             LRT p (chi-bar) = {p_chibar:.4g}    "
    f"β 显著 (p<0.05): {n_sig}/11"
)
print(
    f"             top |β|: {top_feat['feature']} = {top_feat['beta_hat']:+.2f} kg/ha (per σ)"
)
print("=" * 72)
