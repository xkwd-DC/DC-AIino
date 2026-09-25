"""山西冬小麦核心图: 单产×春旱×灌溉 交互 + 灌溉梯度分布。"""
import pandas as pd
import numpy as np
import re
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from pathlib import Path

ROOT = Path(r"D:\DC\DC-AIino")
FIG = ROOT / "docs" / "figures"
FIG.mkdir(parents=True, exist_ok=True)

wheat = pd.read_parquet(ROOT / "data" / "interim" / "sx_wheat_panel.parquet")
clim = pd.read_parquet(ROOT / "data" / "interim" / "sx_wheat_extreme_index.parquet")
panel = pd.read_parquet(ROOT / "data" / "interim" / "paper_panel_sx_full_sown.parquet")

wheat["county"] = wheat["county"].astype(str).map(lambda s: re.sub(r"\s+", "", s))
cmap = clim[["county", "adcode"]].drop_duplicates()
cmap["county"] = cmap["county"].astype(str).map(lambda s: re.sub(r"\s+", "", s))
cmap["adcode"] = cmap["adcode"].astype("int64")
w = wheat.merge(cmap, on="county", how="left")
w = w[w["adcode"].notna()].copy(); w["adcode"] = w["adcode"].astype("int64")
ccult = (panel.groupby("adcode", as_index=False).agg(cultivated_area_ha=("cultivated_area_ha", "mean")))
ccult["adcode"] = ccult["adcode"].astype("int64")
w = w.merge(ccult, on="adcode", how="left")
w["irr_rate"] = (w["irrig_eff_kha"] * 1000.0 / w["cultivated_area_ha"]).clip(0, 1)
c = clim[["adcode", "harvest_year", "spring_cdd_max", "spring_precip"]].copy()
c["adcode"] = c["adcode"].astype("int64"); c["harvest_year"] = c["harvest_year"].astype(int)
w["year"] = w["year"].astype(int)
w = w.merge(c, left_on=["adcode", "year"], right_on=["adcode", "harvest_year"], how="inner")
w = w[(w["wheat_sown_ha"] >= 300) & (w["wheat_yield_kgha"] > 0)].dropna(subset=["irr_rate", "spring_cdd_max", "wheat_yield_kgha"]).copy()
w["lny"] = np.log(w["wheat_yield_kgha"])
w["grp"] = np.where(w["irr_rate"] < 0.3, "Rain-fed(<0.3)", np.where(w["irr_rate"] > 0.6, "Irrigated(>0.6)", "Mid"))

print("图样本:", len(w), "县:", w["adcode"].nunique())

# Fig 1: 春旱CDD vs 单产, 按灌溉分组
fig, ax = plt.subplots(figsize=(6.5, 4.6))
colors = {"Rain-fed(<0.3)": "#d62728", "Mid": "#ff7f0e", "Irrigated(>0.6)": "#1f77b4"}
for g in ["Rain-fed(<0.3)", "Mid", "Irrigated(>0.6)"]:
    s = w[w["grp"] == g]
    if len(s) < 4:
        continue
    ax.scatter(s["spring_cdd_max"], s["lny"], s=14, alpha=0.55, c=colors[g], label=f"{g} (n={len(s)})")
    # 按组拟合线
    z = np.polyfit(s["spring_cdd_max"], s["lny"], 1)
    xs = np.linspace(s["spring_cdd_max"].min(), s["spring_cdd_max"].max(), 50)
    ax.plot(xs, z[0] * xs + z[1], c=colors[g], lw=1.8)
ax.set_xlabel("spring_cdd_max (consecutive dry days), Mar-Jun")
ax.set_ylabel("ln(wheat yield, kg/ha)")
ax.set_title("Spring-drought effect: rain-fed counties respond more")
ax.legend(frameon=False, fontsize=8); ax.grid(alpha=0.25)
fig.tight_layout(); fig.savefig(FIG / "fig_sx_wheat_drought_irrig.png", dpi=150)
print("图1:", FIG / "fig_sx_wheat_drought_irrig.png")

# Fig 2: 灌溉率分布(真麦县)
fig, ax = plt.subplots(figsize=(6.2, 3.8))
ax.hist(w["irr_rate"].unique() if False else w["irr_rate"], bins=16, color="#1f77b4", alpha=0.75)
ax.axvline(0.3, color="#d62728", ls="--", lw=1.2); ax.axvline(0.6, color="#2ca02c", ls="--", lw=1.2)
ax.set_xlabel("irrigation rate (effective irrigated / cultivated)")
ax.set_ylabel("count-year frequency")
ax.set_title("Irrigation-rate distribution across Shanxi wheat counties (0.3/0.6 bands)")
ax.grid(alpha=0.25)
fig.tight_layout(); fig.savefig(FIG / "fig_sx_wheat_irrig_hist.png", dpi=150)
print("图2:", FIG / "fig_sx_wheat_irrig_hist.png")
