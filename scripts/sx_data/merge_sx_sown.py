"""
把《山西统计年鉴》分县粮食播种面积 并入 山西县面板 (paper_panel_sx_full.parquet)。
- 用 sx_county_centroids.csv 作为权威 县名->adcode 映射
- 处理政区改名别名 + 同名(城区/郊区/矿区)按城市消歧
- 新增 grain_sown_kha(千公顷) + yield_ton_per_ha_sown(用粮食播种面积算的单产)
"""
import pandas as pd
import numpy as np
from pathlib import Path

ROOT = Path(r"D:\DC\DC-AIino")
SOWN = ROOT / "data" / "interim" / "sx_sown"

# 政区改名别名(旧名->新名, 同 adcode)
RENAME = {
    "苛岚县": "岢岚县",   # 常见异体写法 -> 岢岚县(140929)
    "大同县": "云州区",   # 140215
    "太谷县": "太谷区",   # 140703
    "怀仁县": "怀仁市",   # 140681
    "屯留县": "屯留区",   # 140405
    "长治县": "上党区",   # 140404
    "潞城市": "潞城区",   # 140406
}

# 同名县 -> (城市, adcode)
AMBIG = {
    ("阳泉市", "城区"): "140302",
    ("晋城市", "城区"): "140502",
    ("长治市", "城区"): "140406",
    ("长治市", "郊区"): "140411",
    ("阳泉市", "郊区"): "140311",
    ("大同市", "矿区"): "140203",
    ("阳泉市", "矿区"): "140303",
}

cent = pd.read_csv(ROOT / "data" / "interim" / "sx_county_centroids.csv")
cent["county"] = cent["county"].str.replace(r"\s+", "", regex=True)
cent["adcode"] = cent["adcode"].astype(int).astype(str).str.zfill(6)

# 也用面板自身的"县名->县代码"作补充(含旧县名: 南郊区/大同县/长治县...)
panel0 = pd.read_parquet(ROOT / "data" / "interim" / "paper_panel_sx.parquet")
panel0["_code"] = panel0["county_code"].astype(int).astype(str).str.zfill(6)
panel0["_nm"] = panel0["county"].astype(str).str.replace(r"\s+", "", regex=True)
extra = panel0.groupby("_nm")["_code"].apply(lambda s: sorted(set(s))).to_dict()

name2codes = cent.groupby("county")["adcode"].apply(list).to_dict()
for k, v in extra.items():
    if k not in name2codes:
        name2codes[k] = v


def resolve(city, county):
    county = county.replace(" ", "")
    if county in ("市辖区", "省直辖县级行政区划", "县市区"):
        return None
    if (city, county) in AMBIG:
        return AMBIG[(city, county)]
    if county in RENAME:
        county = RENAME[county]
    # 单字号: OCR 截断, 尝试补齐 县/区/市
    if len(county) == 1:
        for suffix in ("县", "区", "市"):
            cand = county + suffix
            if (city, cand) in AMBIG:
                return AMBIG[(city, cand)]
            if cand in name2codes:
                return name2codes[cand][0]
    codes = name2codes.get(county, [])
    if len(codes) == 1:
        return codes[0]
    return None


all_rows = []
for y in range(2005, 2024):
    df = pd.read_csv(SOWN / f"{y}.csv")
    for _, r in df.iterrows():
        if str(r["county"]).strip() in ("市辖区", "省直辖县级行政区划", "县市区"):
            continue
        code = resolve(str(r["city"]), str(r["county"]))
        all_rows.append({
            "adcode": code,
            "year": int(r["data_year"]),
            "county_src": str(r["county"]).strip(),
            "grain_sown_ha": float(r["grain_sown_ha"]),
        })

raw = pd.DataFrame(all_rows)
matched = raw[raw["adcode"].notna()]
unmatched = raw[raw["adcode"].isna()].copy()
print("=== 映射结果 ===")
print("总行:", len(raw), "| 匹配:", len(matched), "| 未匹配:", len(unmatched))
if len(unmatched):
    print("未匹配(多为开发区/风景名胜区等):")
    print(unmatched[["city", "year", "county_src", "grain_sown_ha"]] if "city" in unmatched else
          unmatched.groupby(["year", "county_src"]).size())

matched = matched.drop_duplicates(subset=["adcode", "year"])
matched["grain_sown_kha"] = matched["grain_sown_ha"] / 1000.0
matched = matched[["adcode", "year", "grain_sown_kha", "grain_sown_ha"]]
matched.to_csv(ROOT / "data" / "interim" / "sx_county_sown_filled.csv", index=False, encoding="utf-8-sig")
print("已输出 sx_county_sown_filled.csv | 唯一 (adcode,year):", len(matched))

# ---- 并入面板 ----
panel = pd.read_parquet(ROOT / "data" / "interim" / "paper_panel_sx_full.parquet")
panel["adcode"] = panel["county_code"].astype(int).astype(str).str.zfill(6)
panel = panel.merge(matched[["adcode", "year", "grain_sown_kha"]],
                    on=["adcode", "year"], how="left")

panel["grain_sown_kha"] = panel.groupby(["adcode", "year"])["grain_sown_kha"].transform("first")
# 用粮食播种面积重算单产(千克/公顷)
sown_ha = panel["grain_sown_kha"] * 1000.0
panel["yield_ton_per_ha_sown"] = np.where(
    sown_ha > 0, panel["grain_output_t"] / sown_ha, np.nan)

out = ROOT / "data" / "interim" / "paper_panel_sx_full_sown.parquet"
panel.to_parquet(out, index=False)
print("已输出:", out)

cols = ["year", "grain_output_t", "sown_area_kha", "grain_sown_kha",
        "yield_ton_per_ha", "yield_ton_per_ha_sown"]
diag = panel[cols].notna().mean().mul(100).round(1)
print("\n=== 合并后关键字段覆盖(%) ===")
print(diag.to_string())
