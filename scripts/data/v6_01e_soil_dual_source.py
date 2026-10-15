#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""v6 Step 1e：土壤水分双源异质对照（气象 vs 气象+土壤水分）。

问题
====
补了 TerraClimate ``soil``（土壤水分）之后，县级层到底有没有边际贡献？
本脚本用**两套交叉验证口径**回答，因为只报一套会误导：

  kfold  5 折随机打乱（pooled）——测「解释力」：同一批县内，多了这路模态能不能
         把 log_yield 解释得更准。
  lco    留一省（leave-one-province-out）——测「空间迁移」：换一个没见过的省还能
         不能站住。log_yield 是水平值、省际均值差异极大，LCO 下 R² 本就偏低甚至
         为负，这是既有 v6_12「气候迁移」实验的已知性质，不是本模态的问题。

两套结论不一致时，**以 lco 判可迁移性、以 kfold 判解释力**，两个数字都要进材料。

特征集（沿用 ``v6_12_climate_transfer.py`` 的 CLIM5 / SEASONAL 口径）
================================================================
  CLIM5        = temp, prec, sun, spei_annual_mean, spei_growing_season_mean
  CLIMG        = CLIM5 + SEASONAL（11 个生长季/季节特征）
  CLIMG+SOIL   = CLIMG + soil_moisture_annual_mean + soil_moisture_gs_mean
  SOIL         = soil_moisture_annual_mean + soil_moisture_gs_mean
                 （单独一路，看它自己解释多少）

⚠️ 口径提醒（必须进论文/AIC 材料）
================================
``v6_12_climate_transfer.py:50`` 的 ``PROV_SHARED`` 有 **10 个**省-年共享常量：
  ndvi_yearly, ndvi_summer_peak, lst_day_growing_mean_k, lst_night_growing_mean_k,
  fert, irr, flood, drou_a, flood_a, cropland_ratio
它们不是县级观测，凡声称「县级 X 变量的边际贡献」都必须先把这一组排掉。
本脚本的特征集里**不含**这 10 个；``soil_moisture_*`` 是真正逐县聚合的
（TerraClimate 原生 1/24° 网格 → 县治最近格点），不受此限。

输入 : data/interim/paper_panel_v7_soil.parquet
输出 : reports/soil_moisture_dual_source.md
       reports/soil_moisture_dual_source.json

用法 : python scripts/data/v6_01e_soil_dual_source.py
"""
from __future__ import annotations

import json
import sys
import warnings
from pathlib import Path

import numpy as np
import pandas as pd

warnings.filterwarnings("ignore")

PROJECT_ROOT = Path(__file__).resolve().parents[2]
PANEL = PROJECT_ROOT / "data" / "interim" / "paper_panel_v7_soil.parquet"
REPORT_MD = PROJECT_ROOT / "reports" / "soil_moisture_dual_source.md"
REPORT_JSON = PROJECT_ROOT / "reports" / "soil_moisture_dual_source.json"

TARGET = "log_yield"
SEED = 42
KFOLD_N = 5

# 与 v6_12_climate_transfer.py 保持一致的特征分组
CLIM3 = ["temp", "prec", "sun"]
CLIM5 = CLIM3 + ["spei_annual_mean", "spei_growing_season_mean"]
SEASONAL = ["gs_tmax_mean", "gs_tmin_mean", "gs_ppt", "gs_srad", "gs_pet",
            "gdd10", "gs_aridity", "prec_cv", "gs_prec_share",
            "winter_temp", "seasonal_temp_range"]
CLIMG = CLIM5 + SEASONAL
SOIL = ["soil_moisture_annual_mean", "soil_moisture_gs_mean"]

CONFIGS = {
    "CLIM5": CLIM5,
    "CLIMG": CLIMG,
    "CLIMG+SOIL": CLIMG + SOIL,
    "SOIL": SOIL,
}
SCHEMES = {"kfold": f"{KFOLD_N} 折随机（测解释力）", "lco": "留一省（测空间迁移）"}

# PROV_SHARED（省-年共享常量，非县级观测）——显式排除，只在报告里提醒
PROV_SHARED_EXCLUDED = ["ndvi_yearly", "ndvi_summer_peak",
                        "lst_day_growing_mean_k", "lst_night_growing_mean_k",
                        "fert", "irr", "flood", "drou_a", "flood_a", "cropland_ratio"]

XGB_PARAMS = {
    "n_estimators": 300, "max_depth": 5, "learning_rate": 0.05,
    "subsample": 0.8, "colsample_bytree": 0.8,
    "reg_alpha": 0.1, "reg_lambda": 1.0, "n_jobs": -1,
    "tree_method": "hist", "verbosity": 0,
}


def make_folds(df: pd.DataFrame, scheme: str) -> list[tuple[str, np.ndarray, np.ndarray]]:
    """返回 [(折名, 训练行位置, 测试行位置)]。"""
    from sklearn.model_selection import KFold

    idx = np.arange(len(df))
    if scheme == "lco":
        folds = []
        for prov in sorted(df["省份"].unique()):
            test = idx[(df["省份"] == prov).to_numpy()]
            train = idx[(df["省份"] != prov).to_numpy()]
            folds.append((str(prov), train, test))
        return folds
    if scheme == "kfold":
        kf = KFold(n_splits=KFOLD_N, shuffle=True, random_state=SEED)
        return [(f"fold{i}", tr, te) for i, (tr, te) in enumerate(kf.split(idx))]
    raise ValueError(f"未知 CV 口径: {scheme}")


def run_cv(df: pd.DataFrame, feats: list[str], scheme: str) -> dict:
    """按指定口径跑一遍所有折，返回逐折指标与汇总。"""
    from sklearn.metrics import r2_score, mean_squared_error
    import xgboost as xgb

    y = df[TARGET].to_numpy()
    X = df[feats].to_numpy()
    folds = []
    for name, tr, te in make_folds(df, scheme):
        model = xgb.XGBRegressor(random_state=SEED, **XGB_PARAMS)
        model.fit(X[tr], y[tr])
        pred = model.predict(X[te])
        folds.append({
            "fold": name,
            "n_train": int(len(tr)),
            "n_test": int(len(te)),
            "r2": float(r2_score(y[te], pred)),
            "rmse": float(np.sqrt(mean_squared_error(y[te], pred))),
        })
    r2s = [f["r2"] for f in folds]
    return {
        "n_features": len(feats),
        "features": feats,
        "r2_mean": float(np.mean(r2s)),
        "r2_median": float(np.median(r2s)),
        "r2_std": float(np.std(r2s, ddof=1)) if len(r2s) > 1 else 0.0,
        "rmse_mean": float(np.mean([f["rmse"] for f in folds])),
        "folds": folds,
    }


def pairwise(results: dict, scheme: str, base: str, aug: str) -> dict:
    """base vs aug 的逐折配对 t 检验。"""
    from scipy import stats

    a = np.array([f["r2"] for f in results[scheme][base]["folds"]])
    b = np.array([f["r2"] for f in results[scheme][aug]["folds"]])
    t_stat, p_value = stats.ttest_rel(b, a)
    delta = float(b.mean() - a.mean())
    return {
        "base": base, "aug": aug,
        "base_r2": float(a.mean()), "aug_r2": float(b.mean()),
        "delta_r2": delta,
        "delta_pct": float(100.0 * delta / abs(a.mean())) if a.mean() else float("nan"),
        "t_stat": float(t_stat), "p_value": float(p_value),
        "n_folds": int(len(a)),
    }


def render(full: pd.DataFrame, results: dict, notes: list[str]) -> str:
    L: list[str] = []
    L.append("# 土壤水分（Soil Moisture）双源异质对照")
    L.append("")
    L.append("数据源：TerraClimate `soil`（土壤水分 mm，原生 1/24°≈4.6 km 月网格）"
             "→ 县级年度聚合（县治最近格点）。")
    L.append("")
    L.append("## 口径提醒")
    L.append("")
    L.append("- TerraClimate `soil` 的 `long_name` 就是 `soil_moisture_content`——它是"
             "**土壤水分**，**不是**土壤质地/有机质这类「土壤属性」。字段名与材料里一律写 "
             "`soil_moisture_*`。")
    L.append("- `v6_12_climate_transfer.py:50` 的 `PROV_SHARED` 有 **10 个**省-年共享常量：`"
             + "`, `".join(PROV_SHARED_EXCLUDED) + "`。它们不是县级观测，"
             "凡声称「县级变量的边际贡献」必须先把这一组排掉。")
    L.append("- 本对照的特征集里**不含**这 10 个；`soil_moisture_*` 是真正逐县聚合的。")
    L.append("- 两套口径不一致时：**`kfold` 判解释力，`lco` 判空间可迁移性**，两个数字都要报。")
    L.append("")
    L.append("## 样本")
    L.append("")
    L.append(f"- 面板：`{PANEL.name}`，{len(full)} 行 / {full['区县代码'].nunique()} 县 / "
             f"{int(full['年份'].min())}–{int(full['年份'].max())}")
    L.append(f"- 建模样本（`{TARGET}` 与全部特征非空）：{results['n_samples']} 行 / "
             f"{results['n_counties']} 县 / {results['n_provinces']} 省")
    L.append("")
    for scheme, label in SCHEMES.items():
        L.append(f"## {label}（`{scheme}`）")
        L.append("")
        L.append("| 特征集 | 特征数 | R² 均值 | R² 中位 | R² 标准差 | RMSE 均值 |")
        L.append("|---|---|---|---|---|---|")
        for name in CONFIGS:
            r = results[scheme][name]
            L.append(f"| {name} | {r['n_features']} | {r['r2_mean']:.4f} | {r['r2_median']:.4f} | "
                     f"{r['r2_std']:.4f} | {r['rmse_mean']:.4f} |")
        L.append("")
        d = results["delta"][scheme]
        L.append(f"- CLIMG → CLIMG+SOIL：{d['base_r2']:.4f} → {d['aug_r2']:.4f}"
                 f"（ΔR² = **{d['delta_r2']:+.4f}**，相对 {d['delta_pct']:+.2f}%），"
                 f"逐折配对 t 检验 t = {d['t_stat']:.3f}，p = {d['p_value']:.4f}（n={d['n_folds']} 折）")
        L.append(f"- 仅 SOIL 单独一路：R² 均值 {results[scheme]['SOIL']['r2_mean']:.4f}"
                 f"（对比 CLIM5 {results[scheme]['CLIM5']['r2_mean']:.4f}）")
        L.append("")
    L.append("## 逐省 R²（`lco` 口径）")
    L.append("")
    L.append("| 省份 | " + " | ".join(CONFIGS) + " |")
    L.append("|---" * (len(CONFIGS) + 1) + "|")
    for i, fold in enumerate(results["lco"]["CLIMG"]["folds"]):
        cells = [f"{results['lco'][n]['folds'][i]['r2']:.4f}" for n in CONFIGS]
        L.append(f"| {fold['fold']} | " + " | ".join(cells) + " |")
    L.append("")
    L.append("## 结论")
    L.append("")
    for line in results["verdict"]:
        L.append(f"- {line}")
    L.append("")
    if notes:
        L.append("## 备注")
        L.append("")
        for n in notes:
            L.append(f"- {n}")
        L.append("")
    return "\n".join(L)


def main() -> int:
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:  # noqa: BLE001 —— Windows GBK 控制台兜底
            pass

    full = pd.read_parquet(PANEL)
    need = [TARGET] + sorted({f for feats in CONFIGS.values() for f in feats})
    missing = [c for c in need if c not in full.columns]
    if missing:
        raise SystemExit(f"面板缺列: {missing}（先跑 v6_01d_terraclimate_soil.py）")

    df = full.dropna(subset=need).reset_index(drop=True)
    n_dropped = len(full) - len(df)
    n_no_coord = (full["区县代码"].nunique()
                  - full.dropna(subset=["lon", "lat"])["区县代码"].nunique())
    notes = [
        f"因 `{TARGET}` 或特征缺失剔除 {n_dropped} 行，其中 2023 年 "
        f"{int((full['年份'] == 2023).sum())} 行（`log_yield` 尚未回填，见 A1 工作流）。",
        f"{n_no_coord} 个县缺县治坐标，soil 无法聚合，已进入 dropna 的剔除数。",
    ]
    print(f"[dual-source] 建模样本 {len(df)} 行 / {df['区县代码'].nunique()} 县 / "
          f"{df['省份'].nunique()} 省")

    results: dict = {
        "n_samples": int(len(df)),
        "n_counties": int(df["区县代码"].nunique()),
        "n_provinces": int(df["省份"].nunique()),
        "cv_schemes": SCHEMES,
        "delta": {},
    }
    for scheme in SCHEMES:
        results[scheme] = {}
        for name, feats in CONFIGS.items():
            r = run_cv(df, feats, scheme)
            results[scheme][name] = r
            print(f"[dual-source] {scheme:6s} {name:12s} R²={r['r2_mean']:.4f} (±{r['r2_std']:.4f})")
        results["delta"][scheme] = pairwise(results, scheme, "CLIMG", "CLIMG+SOIL")

    dk, dl = results["delta"]["kfold"], results["delta"]["lco"]
    verdict = []
    for scheme, d in (("kfold", dk), ("lco", dl)):
        tag = ("显著" if d["delta_r2"] > 0 else "显著为负") if d["p_value"] < 0.05 else "不显著"
        verdict.append(f"`{scheme}`：ΔR² = {d['delta_r2']:+.4f}（p = {d['p_value']:.4f}，{tag}）")
    verdict.append(
        "判定口径：解释力看 `kfold`，空间可迁移性看 `lco`；两者不一致时材料里必须同时给出，"
        "并以 `lco` 作为可迁移性的判据。")
    if dk["delta_r2"] <= 0 and dl["delta_r2"] <= 0:
        verdict.append(
            "**如实结论：土壤水分这条模态没有带来可迁移的增益。** 若仍要继续用，应改口径试"
            "（如年内最低土壤水分、干旱持续期这类极值构造），而不是调整报告措辞。")
    results["verdict"] = verdict

    REPORT_MD.parent.mkdir(parents=True, exist_ok=True)
    REPORT_JSON.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
    REPORT_MD.write_text(render(full, results, notes), encoding="utf-8")
    print(f"[dual-source] 写入 {REPORT_MD.name} / {REPORT_JSON.name}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
