#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""v9 Step 2：县级气候归因模型（站点用）训练 + SHAP 预计算。

为什么是这个口径
================
县级最近可用的成品面板里，`log_yield = log(粮食总产量_吨)` 的方差约 **92% 由播种面积
（规模）解释**（见 reports/v6_12_climate_transfer_summary.md）。拿"含规模"的特征去解释
总产量，R² 好看但结论会被规模背走。因此站点县级层用**干净口径**：

    特征 = CLIMG 16 维（县级年均气候 3 + 县级 SPEI 2 + 生长季/极端/季节指数 11）
    排除 = 播种面积 / 规模（log_sown）+ 省-年共享常量（遥感 NDVI&LST、投入、成灾…）
    目标 = log_yield

官方可报的迁移能力（5 种子，reports/v6_12_*.csv，**不在本脚本重算**）：
    CLIMG  LCO R² = +0.4489 ± 0.0065 ；时间外推 R² = +0.3644 ± 0.0044
配套阴性对照与显著性见 reports/v6_13_*（本脚本原样灌入 county_standard 表）。

本脚本做三件事
==============
1. 用全样本训练部署模型（seed 42），落盘 backend/models/county_climg_*；
2. 对**全部气候齐备行**（含无产量的年份）算 SHAP，落盘 county_model_out 表，
   供地图着色与县级归因面板直读（不在请求期算 SHAP）；
3. 把官方协议数字（v6_12/v6_13 的 CSV）灌入 county_standard 表，避免前端硬编码。

用法
====
    python scripts/data/v9_02_train_county_climg.py
    python scripts/data/v9_02_train_county_climg.py --skip-lco   # 跳过复现体检
"""
from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
import shap
import xgboost as xgb
from sklearn.metrics import mean_squared_error, r2_score
from sklearn.model_selection import KFold

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DB = PROJECT_ROOT / "backend" / "data" / "county.db"
MODELS = PROJECT_ROOT / "backend" / "models"
REPORTS = PROJECT_ROOT / "reports"

MODEL_PKL = MODELS / "county_climg_xgb.pkl"
FEATURES_JSON = MODELS / "county_climg_features.json"
CARD_MD = MODELS / "county_climg_card.md"

SEED = 42
TIME_SPLIT = 2019

# 「粮食生产单元」判定阈值（吨/年）。
# 县域统计年鉴把市辖区一并列出，其中不少是城市核心区（如成都青羊区年粮食产量仅 33 吨），
# 与主产县不在同一口径上，模型在这些极端单元上会外推。地图默认仍全部显示，但用本字段
# 标出非主产单元，前端可切换「仅主产单元」。
AGRI_OUTPUT_THRESHOLD_T = 10_000

# 与 scripts/data/v6_12_climate_transfer.py 的 XGB_PARAMS 保持一致
XGB_PARAMS = {
    "n_estimators": 300, "max_depth": 5, "learning_rate": 0.05,
    "subsample": 0.8, "colsample_bytree": 0.8,
    "reg_alpha": 0.1, "reg_lambda": 1.0,
    "n_jobs": -1, "random_state": SEED,
}

# 证据表：county_standard 表分组 → (来源文件, 构成行键的列)
EVIDENCE_FILES = {
    "transfer_5seed": ("v6_12_climate_transfer_results.csv", ("config", "n_feat", "seed")),
    "null_permutation": ("v6_13_null_results.csv", ("config", "n_feat")),
    "bootstrap_delta": ("v6_13_bootstrap_test.csv", ("pair",)),
    "single_yield_lco": ("v6_13_single_yield_lco.csv", ("config", "n_feat")),
    "shap_sign_consistency": ("v6_12_climate_transfer_shap_signs.csv", ("config", "feature")),
}

# 方向可跨时间迁移的特征子集来源：上面的 shap_sign_consistency（CLIMG 配置，train≤2019 vs 2020-22）
SHAP_SIGNS_FILE = REPORTS / "v6_12_climate_transfer_shap_signs.csv"


def load_panel() -> tuple[pd.DataFrame, list[str]]:
    conn = sqlite3.connect(DB)
    df = pd.read_sql_query("SELECT * FROM county_panel", conn)
    meta = pd.read_sql_query("SELECT * FROM county_meta", conn)
    feats = json.loads(
        pd.read_sql_query(
            "SELECT value FROM metadata WHERE key='climate_features'", conn
        ).iloc[0, 0]
    )
    conn.close()
    return df.merge(meta, on="county_code", how="left", validate="many_to_one"), feats


def lco_time_check(df: pd.DataFrame, feats: list[str]) -> dict:
    """seed 42 复现体检：LCO 10 折按县分组 + 时间外推（≤2019 → 之后）。

    这不是官方数字（官方是 5 种子），只用来确认站点模型口径与报告一致。
    """
    sub = df[df["log_yield"].notna()].dropna(subset=feats + ["log_yield"]).copy()
    X = sub[feats].values
    y = sub["log_yield"].values.astype(float)
    groups = sub["county_code"].values
    counties = np.unique(groups)

    kf = KFold(n_splits=10, shuffle=True, random_state=SEED)
    preds, trues = [], []
    for tr_i, _ in kf.split(counties):
        tr_mask = np.isin(groups, list(counties[tr_i]))
        model = xgb.XGBRegressor(**XGB_PARAMS)
        model.fit(X[tr_mask], y[tr_mask])
        preds.append(model.predict(X[~tr_mask]))
        trues.append(y[~tr_mask])
    lco_r2 = r2_score(np.concatenate(trues), np.concatenate(preds))

    tr_t = (sub["year"] <= TIME_SPLIT).values
    model_t = xgb.XGBRegressor(**XGB_PARAMS)
    model_t.fit(X[tr_t], y[tr_t])
    p_t = model_t.predict(X[~tr_t])
    return {
        "n_rows": int(len(sub)),
        "n_counties": int(len(counties)),
        "lco_r2": round(float(lco_r2), 4),
        "time_r2": round(float(r2_score(y[~tr_t], p_t)), 4),
        "lco_rmse": round(float(mean_squared_error(
            np.concatenate(trues), np.concatenate(preds), squared=False)), 4),
    }


def build_evidence_table() -> list[tuple[str, str, str]]:
    """官方协议数字 → county_standard 的长表（group / item / value）。"""
    rows: list[tuple[str, str, str]] = []
    for group, (fname, key_cols) in EVIDENCE_FILES.items():
        path = REPORTS / fname
        if not path.exists():
            print(f"[warn] 证据文件缺失，跳过: {fname}")
            continue
        rec = pd.read_csv(path)
        missing = [c for c in key_cols if c not in rec.columns]
        if missing:
            print(f"[warn] {fname} 缺键列 {missing}，跳过")
            continue
        for _, r in rec.iterrows():
            key = "|".join(str(r[c]) for c in key_cols)
            for c in rec.columns:
                if c in key_cols:
                    continue
                rows.append((group, f"{key}|{c}", str(r[c])))

    # 口径诊断（播种面积对 log_yield 方差的解释份额），来自 v6_12 报告正文
    rows += [
        ("scope_diagnosis", "var_share_area", "0.92"),
        ("scope_diagnosis", "corr_log_yield_log_area", "0.9597"),
        ("scope_diagnosis", "n_yield_rows", "4703"),
        ("scope_diagnosis", "note",
         "log_yield 是被规模主导的总量指标；站点县级层的对外口径为剥离规模后的 CLIMG。"),
    ]
    return rows


def write_outputs(feats: list[str], pred: pd.DataFrame, check: dict) -> None:
    conn = sqlite3.connect(DB)
    cur = conn.cursor()

    cur.execute("DROP TABLE IF EXISTS county_model_out")
    cur.execute(
        """
        CREATE TABLE county_model_out (
            county_code INTEGER NOT NULL,
            year        INTEGER NOT NULL,
            y_true      REAL,
            y_pred      REAL,
            clim_contrib REAL,
            clim_anomaly REAL,
            risk_level  INTEGER,
            risk_pct    REAL,
            contrib_pct REAL,
            unit_type   TEXT,
            PRIMARY KEY (county_code, year)
        )
        """
    )
    for f in feats:
        cur.execute(f'ALTER TABLE county_model_out ADD COLUMN "shap_{f}" REAL')

    out = pred.rename(
        columns={f"shap__{f}": f"shap_{f}" for f in feats}
    )
    cols = (
        ["county_code", "year", "y_true", "y_pred", "clim_contrib", "clim_anomaly",
         "risk_level", "risk_pct", "contrib_pct", "unit_type"]
        + [f"shap_{f}" for f in feats]
    )
    out.loc[:, cols].to_sql("county_model_out", conn, if_exists="append", index=False)
    cur.execute("CREATE INDEX idx_model_out_year ON county_model_out(year)")

    cur.execute("DROP TABLE IF EXISTS county_standard")
    cur.execute(
        "CREATE TABLE county_standard ("
        "  group_name TEXT NOT NULL, item TEXT NOT NULL, value TEXT NOT NULL)"
    )
    cur.executemany("INSERT INTO county_standard VALUES (?, ?, ?)", build_evidence_table())

    # 气候特征的方向稳定性（CLIMG，训练期 vs 测试期 SHAP 均值是否同号）——县级归因面板直读
    cur.execute("DROP TABLE IF EXISTS feature_direction")
    cur.execute(
        "CREATE TABLE feature_direction ("
        "  feature TEXT PRIMARY KEY, train_shap REAL, test_shap REAL, same_sign INTEGER)"
    )
    if SHAP_SIGNS_FILE.exists():
        sg = pd.read_csv(SHAP_SIGNS_FILE)
        sg = sg[sg["config"] == "CLIMG"]
        cur.executemany(
            "INSERT OR REPLACE INTO feature_direction VALUES (?, ?, ?, ?)",
            [
                (r.feature, float(r.train_shap), float(r.test_shap), int(bool(r.same_sign)))
                for r in sg.itertuples()
            ],
        )
        print(f"[输出] feature_direction：{len(sg)} 个气候特征的方向稳定性")
    else:
        print(f"[warn] 缺方向一致性文件，feature_direction 留空: {SHAP_SIGNS_FILE.name}")

    for k, v in {
        "model_id": "county_climg_xgb",
        "model_seed": str(SEED),
        "model_target": "log_yield",
        "model_features": json.dumps(feats, ensure_ascii=False),
        "model_scored_rows": str(len(out)),
        "model_build_check": json.dumps(check, ensure_ascii=False),
        "model_trained_at": datetime.now(timezone.utc).isoformat(),
        "model_scope_note": "CLIMG = 县级气候 16 维；已排除播种面积/规模与省-年共享常量。",
        "agri_output_threshold_t": str(AGRI_OUTPUT_THRESHOLD_T),
        "risk_index_definition": (
            "risk_level/risk_pct 取自 clim_anomaly（县内去均值后的当年气候偏离，逐年可比）；"
            "clim_contrib/contrib_pct 是气候条件画像（跨县可比，含县际结构差异，不可当当年风险读）。"
        ),
    }.items():
        cur.execute(
            "INSERT OR REPLACE INTO metadata VALUES (?, ?)", (k, v)
        )
    conn.commit()
    conn.close()


def write_card(check: dict, feats: list[str], n_train: int, base_value: float) -> None:
    lines = [
        "# 模型卡片 · 县级气候归因模型（站点用）",
        "",
        f"> 生成时间：{datetime.now(timezone.utc).date().isoformat()} ｜ 种子 {SEED}",
        "> 角色：站点 M07「县级风险地图」的着色与归因引擎。与省级 M01-M04 的三模型"
        "（XGB/LSTM/Att-LSTM，N=403）是**两套独立口径**，数字不可混用。",
        "",
        "## 1. 口径",
        "",
        "| 项 | 内容 |",
        "|---|---|",
        f"| 目标 | `log_yield` = log(县级粮食总产量/吨) |",
        f"| 特征 | CLIMG {len(feats)} 维（县级年均气候 3 + 县级 SPEI 2 + 生长季/极端/季节指数 11） |",
        f"| 明确排除 | 播种面积/规模（log_sown）、省-年共享常量（遥感 NDVI&LST、投入、成灾面积、耕地占比） |",
        f"| 训练样本 | {n_train} 行（有产量且 16 维气候齐备） |",
        f"| 模型 | XGBoost 回归，n_estimators=300 / max_depth=5 / lr=0.05 |",
        f"| SHAP 基准值 | {base_value:.4f}（log 总产量均值） |",
        "",
        "## 1.1 两个指数不要混用",
        "",
        "| 指数 | 定义 | 能读什么 | 不能读什么 |",
        "|---|---|---|---|",
        "| `clim_contrib` | Σ SHAP，即气候对该县该年 log 产量的模型边际贡献 | 该县的气候条件画像（跨县可比） | 不能当「今年的风险」：县际结构差异（本县气候常年偏冷/偏旱）混在里面，"
        "且 LCO 口径下气候特征会替省份尺度背书 |",
        "| `clim_anomaly` | `clim_contrib` 减去该县历年均值 | 「今年该县气候相对自身常态是偏有利还是偏不利」，逐年可比、可做时间轴动画 | 不回答「哪个县的绝对气候条件更差」 |",
        "",
        "地图与风险等级的默认口径是 `clim_anomaly`；`clim_contrib` 只在明细卡里作气候画像展示。",
        "",
        "## 2. 为什么必须剥离规模",
        "",
        "`log_yield` 的方差约 **92%** 由播种面积解释（与 log 面积相关 0.9597）。"
        "若把播种面积放进特征，R² 会从 CLIMG 的 0.4489 抬到 0.6465，但那是规模在解释规模，"
        "不是气候解释力。站点县级层因此对外只用 CLIMG 及以下口径。",
        "",
        "## 3. 迁移能力（官方 5 种子，来自 reports/v6_12_*.csv）",
        "",
        "| 配置 | 维数 | LCO（跨县空间迁移） | 时间外推（≤2019→2020-22） |",
        "|---|---:|---|---|",
        "| CLIM3（纯年均气候） | 3 | +0.2600 ± 0.0044 | +0.2216 ± 0.0024 |",
        "| CLIM5（+县级 SPEI） | 5 | +0.3241 ± 0.0060 | +0.2366 ± 0.0044 |",
        "| **CLIMG（+生长季/极端指数）** | **16** | **+0.4489 ± 0.0065** | **+0.3644 ± 0.0044** |",
        "| CLIMG+S（对照·含规模） | 17 | +0.6465 ± 0.0046 | +0.4530 ± 0.0050 |",
        "| 单产口径 CLIMG | 16 | +0.5208 ± 0.0065（只报 LCO） | — |",
        "",
        "## 4. 阴性对照与显著性（reports/v6_13_*.csv）",
        "",
        "- permutation null（30 次逐列打乱）：CLIMG 真实 +0.4489 vs null −0.0157，"
        "真实 100% 高于 null 分布；",
        "- bootstrap（80 次跨县重采样）：CLIM3→CLIMG 增益 Δ=+0.1888，"
        "95%CI [+0.1241, +0.1848]，P(Δ≤0)=0.000；",
        "- 单产口径 null：CLIMG −0.0336，真实超额 +0.5544。",
        "",
        "## 5. 本机复现体检（seed 42，非官方数字）",
        "",
        "```json",
        json.dumps(check, ensure_ascii=False, indent=2),
        "```",
        "",
        "## 6. 边界（不可越界表述）",
        "",
        "- 模型的输出是**气候条件对县级总产量的模型边际贡献**，不是「该县产量水平」；",
        "- 目标仍为总产量口径：即使剥离了规模，也不能表述为「气候决定了产量」；",
        "- 时间外推窗口只有 2020-2022 三年，样本偏窄；",
        "- 逐日极端指数（TX35、连续无雨日）本层没有：TerraClimate 是月度数据，"
        "全国县级日尺度需要另接 CMDC 地面日值（本地已下载，尚未接入管线）。",
        f"- 面板含县域统计年鉴的市辖区单元，其中城市核心区年粮食产量仅数十吨。"
        f"站点用 `unit_type` 标出粮食产量 < {AGRI_OUTPUT_THRESHOLD_T} 吨的非主产单元；"
        "训练与协议数字仍为全样本口径（与 reports 一致），地图可切换「仅主产单元」。",
        "",
    ]
    CARD_MD.write_text("\n".join(lines), encoding="utf-8")


def main() -> int:
    ap = argparse.ArgumentParser(description="县级 CLIMG 模型训练与 SHAP 预计算")
    ap.add_argument("--skip-lco", action="store_true", help="跳过 seed42 复现体检")
    args = ap.parse_args()

    if not DB.exists():
        print(f"[FATAL] 先跑 v9_01_build_county_site_db.py，缺 {DB}")
        return 1

    df, feats = load_panel()
    print(f"[输入] county.db：{len(df)} 行 / {df['county_code'].nunique()} 县 / {len(feats)} 气候特征")

    check = {"skipped": True}
    if not args.skip_lco:
        check = lco_time_check(df, feats)
        print(f"[体检·seed42] {check}")

    train = df[df["log_yield"].notna()].dropna(subset=feats + ["log_yield"])
    print(f"[训练] {len(train)} 行 / {train['county_code'].nunique()} 县")

    model = xgb.XGBRegressor(**XGB_PARAMS)
    model.fit(train[feats].values, train["log_yield"].values.astype(float))
    MODELS.mkdir(parents=True, exist_ok=True)
    joblib.dump(model, MODEL_PKL)
    FEATURES_JSON.write_text(
        json.dumps(
            {"features": feats, "target": "log_yield", "seed": SEED,
             "model_id": "county_climg_xgb", "excluded": ["log_sown", "province_year_shared"]},
            ensure_ascii=False, indent=2,
        ),
        encoding="utf-8",
    )
    print(f"[模型] {MODEL_PKL.relative_to(PROJECT_ROOT)}")

    # SHAP：对全部气候齐备行打分（含无产量的年份，地图覆盖率更高）
    score = df.dropna(subset=feats).copy()
    explainer = shap.TreeExplainer(model)
    sv = np.asarray(explainer.shap_values(score[feats].values))
    base_value = float(np.asarray(explainer.expected_value).reshape(-1)[0])

    pred = pd.DataFrame(
        {
            "county_code": score["county_code"].values,
            "year": score["year"].values,
            "y_true": score["log_yield"].values,
            "y_pred": base_value + sv.sum(axis=1),
            "clim_contrib": sv.sum(axis=1),
        }
    )
    for i, f in enumerate(feats):
        pred[f"shap__{f}"] = sv[:, i]

    # 两套指数，别混用：
    #   clim_contrib = 气候条件画像（跨县可比，但含"该县气候本身偏冷/偏旱"这类结构差异，
    #                  在 LCO 口径下还可能替省份尺度背书，不能当"今年的风险"读）；
    #   clim_anomaly = 该县当年气候相对**本县历年常态**的偏离（去掉县际结构差异），
    #                  逐年可比、可动画，是地图的"风险"口径。
    pred["clim_anomaly"] = pred["clim_contrib"] - pred.groupby("county_code")[
        "clim_contrib"
    ].transform("mean")
    pred["risk_pct"] = pred.groupby("year")["clim_anomaly"].rank(pct=True) * 100
    pred["risk_level"] = np.clip(
        6 - np.ceil(pred["risk_pct"] / 20.0).astype(int), 1, 5
    )
    pred["contrib_pct"] = pred.groupby("year")["clim_contrib"].rank(pct=True) * 100
    # 单元类型是「县」的属性，不是「县年」的属性：2023 年面板整体无产量真值
    # （县域统计年鉴 2024 卷未出版），若按当年产量逐行判定，会把 2023 全部打成 unknown，
    # 「仅主产单元」筛选在该年直接空掉。改用该县多年中位产量判定。
    county_med = score.groupby("county_code")["grain_output_t"].median()
    sown_med = score.groupby("county_code")["sown_kha"].median()
    unit_by_county = {}
    for code, med in county_med.items():
        if pd.notna(med):
            unit_by_county[code] = (
                "farm" if med >= AGRI_OUTPUT_THRESHOLD_T else "urban"
            )
        else:
            sown = sown_med.get(code, np.nan)
            unit_by_county[code] = "farm" if pd.notna(sown) and sown >= 1.0 else "unknown"
    pred["unit_type"] = pred["county_code"].map(unit_by_county)

    write_outputs(feats, pred, check)
    write_card(check, feats, len(train), base_value)
    print(f"[输出] county_model_out：{len(pred)} 行（含 {int(pred['y_true'].isna().sum())} 行无产量真值）")
    print(f"[输出] {CARD_MD.relative_to(PROJECT_ROOT)}")
    print(f"[SHAP] 基准值 base_value = {base_value:.4f}；"
          f"贡献范围 [{pred['clim_contrib'].min():.3f}, {pred['clim_contrib'].max():.3f}]")
    return 0


if __name__ == "__main__":
    sys.exit(main())
