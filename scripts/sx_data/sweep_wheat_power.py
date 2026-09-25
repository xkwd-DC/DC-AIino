"""稳健性扫描: 看现有山西冬小麦样本能否做出显著的"春旱×灌溉"交互。

变体: 小麦阈值 {100,300,500} x 灌溉定义 {连续, 分组(雨养<0.3/灌溉>0.6)} x 年份固定 {有,无}
核心暴露: spring_cdd_max(春旱连续无雨), spring_precip(春季降水)
"""
import pandas as pd
import numpy as np
import re
from pathlib import Path
from linearmodels.panel import PanelOLS

ROOT = Path(r"D:\DC\DC-AIino")
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
w = w[(w["wheat_yield_kgha"] > 0) & w["irr_rate"].notna()].copy()
w["lny"] = np.log(w["wheat_yield_kgha"])

def z(s): return (s - s.mean()) / s.std()


def fit(sub, ext, use_irr, year_fe):
    sub = sub.dropna(subset=["lny", ext]).copy()
    sub["cid"] = sub["adcode"].astype(str)
    sub = sub.set_index(["cid", "year"])
    X = pd.DataFrame()
    X[ext] = z(sub[ext])
    if use_irr == "cont":
        X["irr"] = sub["irr_rate"]; X[f"{ext}xirr"] = z(sub[ext]) * sub["irr_rate"]
    else:
        sub["rf"] = (sub["irr_rate"] < 0.3).astype(float); sub["ig"] = (sub["irr_rate"] > 0.6).astype(float)
        X["rainfed"] = sub["rf"]; X[f"{ext}xrf"] = z(sub[ext]) * sub["rf"]
    mod = PanelOLS(sub["lny"], X, entity_effects=True, time_effects=year_fe,
                   check_rank=False, drop_absorbed=True)
    res = mod.fit(cov_type="clustered", cluster_entity=True)
    key = f"{ext}xirr" if use_irr == "cont" else f"{ext}xrf"
    return int(res.nobs), res.params[ext], res.pvalues[ext], res.params[key], res.pvalues[key]


res = []
for thr in [100, 300, 500]:
    sub = w[w["wheat_sown_ha"] >= thr]
    for ext in ["spring_cdd_max", "spring_precip"]:
        for use_irr in ["cont", "grp"]:
            for yfe in [True, False]:
                try:
                    n, m, mp, i, ip = fit(sub, ext, use_irr, yfe)
                    res.append({"thr": thr, "extreme": ext, "irr": use_irr, "yearFE": yfe,
                                "N": n, "main": round(m, 3), "main_p": round(mp, 3),
                                "x_irr": round(i, 3), "x_irr_p": round(ip, 3)})
                except Exception as e:
                    print("ERR", thr, ext, use_irr, yfe, str(e)[:40])

tab = pd.DataFrame(res)
import os; os.makedirs(ROOT / "reports", exist_ok=True)
(ROOT / "reports" / "sx_wheat_power_sweep.md").write_text(
    "# 山西冬小麦 春旱×灌溉 稳健性扫描\n\n目标: 现有样本能否做出显著交互。\n\n"
    f"{tab.to_string(index=False)}\n\n解读: x_irr>0 且 x_irr_p<0.05 => 灌溉缓解春旱 (雨养脆弱)。\n", encoding="utf-8")
pd.set_option("display.width", 200)
print(tab.round(3).to_string(index=False))
