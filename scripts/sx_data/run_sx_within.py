"""
县内识别: 用 NASA 日尺度因子 (heat_jja / cdd_max / 暴雨 / 干热风 / 秋淋) 做县城固定效应回归。
去除"县间盆地混杂"后，检验"某县比其常年更热/更干的年份是否减产"（县内识别）。
DV=log(粮食总产量); 县城FE + 年份趋势 + 规模(log农机); cluster县; 关键变量做标准化。
产出: reports/sx_within_county_summary.md
"""
import pandas as pd
import numpy as np
from pathlib import Path

ROOT = Path(r"D:\DC\DC-AIino")
df = pd.read_parquet(ROOT / "data" / "interim" / "paper_panel_sx_full.parquet")
df = df[(df["year"] >= 2012) & (df["year"] <= 2023)].copy()
df = df[df["grain_output_t"] > 0].dropna(subset=["grain_output_t"])
df["log_yield"] = np.log(df["grain_output_t"])

DFAC = ["gs_mean_tmax", "cdd_max", "rainstorm_days", "autumn_rain_days"]
sub = df.dropna(subset=["log_yield"] + DFAC + ["mach_power_10kw"]).copy()
sub["log_mach"] = np.log(sub["mach_power_10kw"])
sub["county"] = sub["county_code"].astype(str)

# 县内(去县均值)标准差 —— 判断每个因子是否有足够的"县内变异"可供识别
print("样本:", len(sub), "| 县:", sub["county"].nunique())
print("\n=== 县内变异(去县均值后SD) ===")
print("\n=== 县内变异(去县均值后SD) — 用于判断可识别性 ===")
for c in DFAC:
    w = sub.groupby("county")[c].transform("mean")
    print(f"  {c}: 总SD={sub[c].std():.2f}  县内SD={(sub[c]-w).std():.2f}")

from linearmodels.panel import PanelOLS
sub = sub.set_index(["county", "year"])
y = sub["log_yield"]

# 仅含县内变异识别的核心因子（标准化）
def z(s):
    return (s - s.mean()) / s.std()

X = pd.DataFrame({k: z(sub[k]) for k in DFAC})
X["log_mach"] = sub["log_mach"]
X["year"] = sub.index.get_level_values("year").astype(float)

# 模型A: 县城FE + 年份趋势 + 日尺度因子
mod = PanelOLS(y, X, entity_effects=True, time_effects=False, check_rank=False, drop_absorbed=True)
res = mod.fit(cov_type="clustered", cluster_entity=True)
print("\n=== 县内识别: 县城FE + 日尺度因子 (标准化系数) ===")
print(f"within R2={res.rsquared_within:.4f} | N={len(y)}")
print(pd.DataFrame({"coef": res.params, "se": res.std_errors, "p": res.pvalues})
      .round(4).to_string())

# 模型B: 稳健性——用"生长季平均最高温"与"年降水集中度"换参看符号稳定性
sub["gs_tmax_anom"] = sub["gs_mean_tmax"] - sub.groupby("county")["gs_mean_tmax"].transform("mean")
X2 = pd.DataFrame({"gs_tmax_w": z(sub["gs_tmax_anom"]), "cdd_max": z(sub["cdd_max"]),
                   "rainstorm_days": z(sub["rainstorm_days"]),
                   "autumn_rain_days": z(sub["autumn_rain_days"]),
                   "log_mach": sub["log_mach"], "year": sub.index.get_level_values("year").astype(float)})
mod2 = PanelOLS(y, X2, entity_effects=True, time_effects=False, check_rank=False, drop_absorbed=True)
res2 = mod2.fit(cov_type="clustered", cluster_entity=True)
print("\n=== 稳健性: 生长季高温县内异常(去县均值) ===")
print(pd.DataFrame({"coef": res2.params, "se": res2.std_errors, "p": res2.pvalues})
      .round(4).to_string())

# 汇总
rep = ROOT / "reports" / "sx_within_county_summary.md"
rep.write_text(
    "# 山西县内识别: NASA日尺度因子 × 县城固定效应\n\n"
    f"样本 {len(y)} 县域年, {sub.index.get_level_values(0).nunique()} 县, 2012-2023\n\n"
    "## 县城FE + 年份趋势 + 日尺度因子 (标准化系数)\n"
    f"{pd.DataFrame({'coef':res.params,'se':res.std_errors,'p':res.pvalues}).round(4).to_string()}\n\n"
    "## 稳健性(heat_days)\n"
    f"{pd.DataFrame({'coef':res2.params,'se':res2.std_errors,'p':res2.pvalues}).round(4).to_string()}\n",
    encoding="utf-8")
print("\n报告已写:", rep)
