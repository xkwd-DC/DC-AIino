"""
山西县面板：气候因子归因回归（statsmodels, cluster县） + 异质性交互 + XGBoost-SHAP。
数据: data/interim/paper_panel_sx_full.parquet  (含气象/SPEI/NASAPOWER日尺度/高程)
窗口: 2012-2023。目标: log(粮食总产量)。
产出: reports/sx_analysis_summary.md
"""
import pandas as pd
import numpy as np
from pathlib import Path

ROOT = Path(r"D:\DC\DC-AIino")
df = pd.read_parquet(ROOT / "data" / "interim" / "paper_panel_sx_full.parquet")

df = df[(df["year"] >= 2012) & (df["year"] <= 2023)].copy()
df = df[df["grain_output_t"] > 0].dropna(subset=["grain_output_t"])
df["log_yield"] = np.log(df["grain_output_t"])

CLIM = ["gs_mean_tmax", "spei3_growing", "heat_jja", "cdd_max",
        "rainstorm_days", "dry_hot_wind", "autumn_rain_days"]
print("样本:", len(df), "| 县:", df["county_code"].nunique(),
      "| 年:", int(df["year"].min()), "-", int(df["year"].max()))


def run_attribution():
    import statsmodels.api as sm
    sub = df.dropna(subset=["log_yield"] + CLIM + ["mach_power_10kw"]).copy()
    X = sub[CLIM].copy()
    X["log_mach"] = np.log(sub["mach_power_10kw"])
    X["year"] = sub["year"].astype(float)
    X = sm.add_constant(X)
    m = sm.OLS(sub["log_yield"], X).fit(cov_type="cluster",
                                        cov_kwds={"groups": sub["county_code"].astype(str)})
    print("\n=== 气候归因 (cluster县, DV=log粮食总产量; 控制: 规模log农机+年份趋势) ===")
    print(f"R2={m.rsquared:.4f} | N={int(m.nobs)} | 县={sub['county_code'].nunique()}")
    tab = pd.DataFrame({"coef": m.params, "se": m.bse, "p": m.pvalues,
                        "t": m.tvalues}).round(4)
    print(tab.to_string())
    return m, tab


def run_hete():
    import statsmodels.api as sm
    sub = df.dropna(subset=["log_yield", "gs_mean_tmax", "mach_power_10kw", "elev_m"]).copy()
    med = sub["elev_m"].median()
    sub["high_elev"] = (sub["elev_m"] > med).astype(int)
    X = pd.DataFrame({
        "gs_mean_tmax": sub["gs_mean_tmax"],
        "high_elev": sub["high_elev"],
        "tmax_x_he": sub["gs_mean_tmax"] * sub["high_elev"],
        "log_mach": np.log(sub["mach_power_10kw"]),
    })
    for yr, g in sub.groupby("year"):
        X[f"y{yr}"] = (sub["year"] == yr).astype(int)
    X = sm.add_constant(X)
    m = sm.OLS(sub["log_yield"], X).fit(cov_type="cluster",
                                        cov_kwds={"groups": sub["county_code"].astype(str)})
    print(f"\n=== 异质性: 高温×高海拔(山地旱作)交互 (高海拔中位={med:.0f}m, 含年份dummy) ===")
    tab = pd.DataFrame({"coef": m.params, "se": m.bse, "p": m.pvalues,
                        "t": m.tvalues}).round(4)
    print(tab.loc[["gs_mean_tmax", "high_elev", "tmax_x_he", "log_mach", "const"]].to_string())
    return m, tab


def run_xgb():
    import xgboost as xgb
    import shap
    from sklearn.model_selection import GroupKFold
    from sklearn.metrics import r2_score
    sub = df.dropna(subset=["log_yield"] + CLIM + ["mach_power_10kw"]).copy()
    sub["log_mach"] = np.log(sub["mach_power_10kw"])
    X = sub[CLIM + ["log_mach"]]
    y = sub["log_yield"]
    gkf = GroupKFold(n_splits=10)
    oof = np.zeros(len(y))
    for tr, te in gkf.split(X, y, groups=sub["county_code"].astype(str)):
        mdl = xgb.XGBRegressor(n_estimators=400, max_depth=4, learning_rate=0.05,
                               subsample=0.8, colsample_bytree=0.8, random_state=42)
        mdl.fit(X.iloc[tr], y.iloc[tr]); oof[te] = mdl.predict(X.iloc[te])
    lco = r2_score(y, oof)
    mask = sub["year"] <= 2019
    m2 = xgb.XGBRegressor(n_estimators=400, max_depth=4, learning_rate=0.05,
                          subsample=0.8, colsample_bytree=0.8, random_state=42)
    m2.fit(X[mask], y[mask]); tp = m2.predict(X[~mask])
    t_r2 = r2_score(y[~mask], tp)
    m3 = xgb.XGBRegressor(n_estimators=400, max_depth=4, learning_rate=0.05,
                          subsample=0.8, colsample_bytree=0.8, random_state=42)
    m3.fit(X, y)
    imp = pd.Series(np.abs(shap.TreeExplainer(m3).shap_values(X)).mean(0),
                    index=X.columns).sort_values(ascending=False).round(4)
    print("\n=== XGBoost ===")
    print(f"LCO R2={lco:.4f} | 时间外推(<=2019->20-23) R2={t_r2:.4f}")
    print(imp.to_string())
    return imp, lco, t_r2


m, mtab = run_attribution()
hm, htab = run_hete()
imp, lco, t_r2 = run_xgb()

rep = ROOT / "reports" / "sx_analysis_summary.md"
rep.parent.mkdir(parents=True, exist_ok=True)
rep.write_text(
    "# 山西县极端气候-粮食因子分析摘要\n\n"
    f"样本 {len(df)} 县域年, {df['county_code'].nunique()} 县, 2012-2023\n\n"
    "## 气候归因(cluster县)\n"
    f"{mtab.to_string()}\n\n"
    "## 异质性 高温×高海拔\n"
    f"{htab.loc[['gs_mean_tmax','high_elev','tmax_x_he','log_mach','const']].to_string()}\n\n"
    "## XGBoost-SHAP\n"
    f"LCO R2={lco:.4f} | 时间外推 R2={t_r2:.4f}\n{imp.to_string()}\n", encoding="utf-8")
print("\n报告已写:", rep)
