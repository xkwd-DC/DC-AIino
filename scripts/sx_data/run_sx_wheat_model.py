"""
山西冬小麦首版交互模型: 极端气候 × 灌溉率 对单产的影响。

DV: log(wheat_yield_kgha)
X : 冬小麦生育期极端指数 + 灌溉率 + 极端×灌溉率 + 县FE + 年FE
核心: 交互项系数 —— 若"干旱/热害/晚霜"对单产不利(主效负),
      则与灌溉率的交互应为"正"(灌溉缓解), 即雨养更脆弱。
产出: reports/sx_wheat_model_summary.md
"""
import pandas as pd
import numpy as np
import re
from pathlib import Path

ROOT = Path(r"D:\DC\DC-AIino")
wheat = pd.read_parquet(ROOT / "data" / "interim" / "sx_wheat_panel.parquet")
clim = pd.read_parquet(ROOT / "data" / "interim" / "sx_wheat_extreme_index.parquet")
panel = pd.read_parquet(ROOT / "data" / "interim" / "paper_panel_sx_full_sown.parquet")

# 县名->adcode 从气候指数取(它来自 sx_county_centroids)
cmap = clim[["county", "adcode"]].drop_duplicates()
wheat["county"] = wheat["county"].astype(str).map(lambda s: re.sub(r"\s+", "", s))
cmap["county"] = cmap["county"].astype(str).map(lambda s: re.sub(r"\s+", "", s))
cmap["adcode"] = cmap["adcode"].astype("int64")
w = wheat.merge(cmap, on="county", how="left")
w = w[w["adcode"].notna()].copy()
w["adcode"] = w["adcode"].astype("int64")

# 县级耕地面积(算灌溉率)
ccult = (panel.groupby("adcode", as_index=False)
         .agg(cultivated_area_ha=("cultivated_area_ha", "mean")))
ccult["adcode"] = ccult["adcode"].astype("int64")
w = w.merge(ccult, on="adcode", how="left")
w["irr_rate"] = (w["irrig_eff_kha"] * 1000.0 / w["cultivated_area_ha"]).clip(0, 1)

# join 气候极端 (adcode + year==harvest_year)
c = clim[["adcode", "harvest_year", "winter_cold_days", "winter_tmin_min",
          "spring_frost_days", "spring_frost_late", "spring_cdd_max",
          "spring_precip", "grain_heat_days", "grain_rain_days", "sow_precip"]]
c["adcode"] = c["adcode"].astype("int64")
c["harvest_year"] = c["harvest_year"].astype(int)
w["year"] = w["year"].astype(int)
w = w.merge(c, left_on=["adcode", "year"], right_on=["adcode", "harvest_year"],
            how="inner")

# 只留真冬小麦县
w = w[w["wheat_sown_ha"] >= 500].copy()
w = w[(w["wheat_yield_kgha"] > 0) & w["irr_rate"].notna()].copy()
w["lny"] = np.log(w["wheat_yield_kgha"])

print("模型样本:", len(w), "| 县:", w["adcode"].nunique(),
      "| 年份:", w["year"].min(), "-", w["year"].max())


def z(s):
    return (s - s.mean()) / s.std()


# 关键极端(雨养最怕): 春旱(cdd高=不利)、春季降水(低=不利)、灌浆热害、晚霜
EXT = ["spring_cdd_max", "spring_precip", "grain_heat_days", "spring_frost_late"]
from linearmodels.panel import PanelOLS

sub = w.dropna(subset=["lny"] + EXT).copy()
sub["cid"] = sub["adcode"].astype(str)
sub = sub.set_index(["cid", "year"])

def build(ext):
    X = pd.DataFrame()
    X[ext] = z(sub[ext])
    X["irr_rate"] = sub["irr_rate"]
    X[f"{ext}xirr"] = z(sub[ext]) * sub["irr_rate"]
    return X

print("\n=== 各极端 与 灌溉率 交互 (县FE + 年FE, DV=log单产) ===")
rows = []
for ext in EXT:
    X = build(ext)
    try:
        mod = PanelOLS(sub["lny"], X, entity_effects=True, time_effects=True,
                       check_rank=False, drop_absorbed=True)
        res = mod.fit(cov_type="clustered", cluster_entity=True)
        rows.append({
            "extreme": ext,
            "main": round(res.params[ext], 3),
            "main_p": round(res.pvalues[ext], 3),
            "x_irr": round(res.params[f"{ext}xirr"], 3),
            "x_irr_p": round(res.pvalues[f"{ext}xirr"], 3),
            "n": int(res.nobs),
        })
        print(f"{ext:20s} 主效={res.params[ext]:+.3f}(p={res.pvalues[ext]:.3f})  "
              f"×灌溉率={res.params[f'{ext}xirr']:+.3f}(p={res.pvalues[f'{ext}xirr']:.3f})")
    except Exception as e:
        print(f"{ext:20s} ERR {e}")

tab = pd.DataFrame(rows)
rep = ROOT / "reports" / "sx_wheat_model_summary.md"
rep.write_text(
    "# 山西冬小麦 极端气候×灌溉率 交互(首版)\n\n"
    f"样本 {len(w)} 县域年, {w['adcode'].nunique()} 县, {w['year'].min()}-{w['year'].max()}\n\n"
    "DV=log(单产) | 县FE+年FE | 聚类县标准误\n\n"
    f"{tab.to_string(index=False)}\n\n"
    "解读: x_irr>0 且显著 => 灌溉率越高, 该极端对单产的负向影响越弱, 即雨养更脆弱。\n",
    encoding="utf-8")
print("\n报告已写:", rep)
