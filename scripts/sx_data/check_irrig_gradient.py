"""可行性闸门: 2023 山西冬小麦县 灌溉率分布。

用 20-14 有效灌溉面积(千公顷) / 现有面板 cultivated_area_ha(公顷) 得到**灌溉覆盖率**。
过滤到真正种冬小麦的县(wheat_sown_ha 超阈值), 看灌溉梯度是否足以支撑
"雨养 vs 灌溉 剂量响应"对照。
"""
import pandas as pd
from pathlib import Path

ROOT = Path(r"D:\DC\DC-AIino")
wheat = pd.read_parquet(ROOT / "data" / "interim" / "sx_wheat_2023_smoke.parquet")
panel = pd.read_parquet(ROOT / "data" / "interim" / "paper_panel_sx_full_sown.parquet")

# 用 county 名匹配(去空白/统一)
panel["county"] = panel["county"].astype(str).str.strip()
# 面板是 县x年, 折叠到县(取耕地面积均值, 避免 join 爆炸)
panel1 = (panel.groupby("county", as_index=False)
          .agg(adcode=("adcode", "first"), cultivated_area_ha=("cultivated_area_ha", "mean")))
wheat["county"] = wheat["county"].astype(str).str.strip()
m = wheat.merge(panel1, on="county", how="left")

m["irrig_eff_ha"] = m["irrig_eff_kha"] * 1000.0
m["irr_rate"] = m["irrig_eff_ha"] / m["cultivated_area_ha"]   # 有效灌溉覆盖率

# 真冬小麦县: 播种面积 >= 500 ha (排除几乎不种麦的县)
ww = m[m["wheat_sown_ha"] >= 500].copy()
print("2023 冬小麦县(播种>=500ha):", len(ww), "| 匹配到耕地面积:", ww["cultivated_area_ha"].notna().sum())
print("\n灌溉覆盖率分布:")
print("  min", round(ww["irr_rate"].min(), 3), "| p25", round(ww["irr_rate"].quantile(.25), 3),
      "| 中位", round(ww["irr_rate"].median(), 3), "| p75", round(ww["irr_rate"].quantile(.75), 3),
      "| max", round(ww["irr_rate"].max(), 3))
print("  低灌(<0.3):", int((ww["irr_rate"] < 0.3).sum()),
      "| 中灌(0.3-0.6):", int(((ww["irr_rate"] >= 0.3) & (ww["irr_rate"] < 0.6)).sum()),
      "| 高灌(>=0.6):", int((ww["irr_rate"] >= 0.6).sum()))

print("\n按灌溉率排序(高->低) top15:  (对比: 是否旱区/灌区分明)")
cols = ["county", "wheat_sown_ha", "wheat_yield_kgha", "irrig_eff_ha", "cultivated_area_ha", "irr_rate"]
print(ww.sort_values("irr_rate", ascending=False)[cols].head(15).round(3).to_string(index=False))
print("\n低灌溉 top10:")
print(ww.sort_values("irr_rate", ascending=True)[cols].head(10).round(3).to_string(index=False))

out = ROOT / "data" / "interim" / "sx_wheat_2023_panel.parquet"
ww.to_parquet(out, index=False)
print("\n落盘:", out, "| 行", len(ww))
