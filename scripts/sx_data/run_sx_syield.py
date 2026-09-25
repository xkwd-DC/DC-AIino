"""
单产分析（甩掉盆地/面积混杂）: DV = log(yield_ton_per_ha_sown)。
覆盖诊断 + 归因(年份趋势+县级控制) + 县内识别(县城FE)。
关键看: 用单产后"关键期高温 gs_tmax"符号是否转负显著。
产出: reports/sx_syield_summary.md
"""
import pandas as pd
import numpy as np
from pathlib import Path

ROOT = Path(r"D:\DC\DC-AIino")
df = pd.read_parquet(ROOT / "data" / "interim" / "paper_panel_sx_full_sown.parquet")
# 并入 NASA T2M_MAX 计算的 TX90p（相对极端高温）
tx = pd.read_csv(ROOT / "data" / "interim" / "tx90p_sx_county.csv")
tx["code"] = tx["adcode"].astype(int).astype(str).str.zfill(6)
df["code"] = df["county_code"].astype(int).astype(str).str.zfill(6)
df = df.merge(tx[["code", "year", "tx90p_days", "tx90p_jja", "tmax_max", "tx90p_thr"]],
              on=["code", "year"], how="left")
df = df[(df["year"] >= 2012) & (df["year"] <= 2023)].copy()
df = df[df["yield_ton_per_ha_sown"] > 0].dropna(subset=["yield_ton_per_ha_sown"])
df["log_syield"] = np.log(df["yield_ton_per_ha_sown"])

print("分析窗口 2012-2023 | 单产样本:", len(df), "| 县:", df["county_code"].nunique())
print("年度单产覆盖:")
print(df.groupby("year").size().to_string())

CLIM = ["gs_mean_tmax", "spei3_growing", "cdd_max", "rainstorm_days",
        "autumn_rain_days", "tx90p_days"]


def z(s):
    return (s - s.mean()) / s.std()


def run_attribution():
    import statsmodels.api as sm
    sub = df.dropna(subset=["log_syield"] + CLIM + ["mach_power_10kw"]).copy()
    sub["log_syield"] = np.log(sub["yield_ton_per_ha_sown"])
    X = sub[CLIM].copy()
    X["log_mach"] = np.log(sub["mach_power_10kw"])
    X["year"] = sub["year"].astype(float)
    X = sm.add_constant(X)
    m = sm.OLS(sub["log_syield"], X).fit(cov_type="cluster",
                                         cov_kwds={"groups": sub["county_code"].astype(str)})
    print("\n=== 单产归因 (年份趋势+县级控制, DV=log单产) ===")
    print(f"R2={m.rsquared:.4f} | N={int(m.nobs)} | 县={sub['county_code'].nunique()}")
    tab = pd.DataFrame({"coef": m.params, "se": m.bse, "p": m.pvalues}).round(4)
    print(tab.to_string())
    return m, tab


def run_within():
    from linearmodels.panel import PanelOLS
    sub = df.dropna(subset=["log_syield"] + CLIM + ["mach_power_10kw"]).copy()
    sub["county"] = sub["county_code"].astype(str)
    sub = sub.set_index(["county", "year"])
    y = sub["log_syield"]
    X = pd.DataFrame({k: z(sub[k]) for k in CLIM})
    X["log_mach"] = sub["mach_power_10kw"]
    X["year"] = sub.index.get_level_values("year").astype(float)
    mod = PanelOLS(y, X, entity_effects=True, time_effects=False, check_rank=False, drop_absorbed=True)
    res = mod.fit(cov_type="clustered", cluster_entity=True)
    print("\n=== 县内识别 (县城FE, DV=log单产) ===")
    print(f"within R2={res.rsquared_within:.4f} | N={len(y)}")
    tab = pd.DataFrame({"coef": res.params, "se": res.std_errors, "p": res.pvalues}).round(4)
    print(tab.to_string())
    return res, tab


_, atab = run_attribution()
_, wtab = run_within()

rep = ROOT / "reports" / "sx_syield_summary.md"
rep.write_text(
    "# 山西县 单产 归因与县内识别\n\n"
    f"样本 {len(df)} 县域年, {df['county_code'].nunique()} 县, 2012-2023\n\n"
    "## 单产归因 (年份趋势+县级控制)\n"
    f"{atab.to_string()}\n\n## 县内识别 (县城FE)\n{wtab.to_string()}\n", encoding="utf-8")
print("\n报告已写:", rep)
