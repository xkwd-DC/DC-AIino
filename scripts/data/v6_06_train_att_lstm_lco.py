#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""v6 Step 6：Attention-LSTM leave-county-out（feature-level attention gating）。

在 v6_05 LSTM 上增加 feature-level attention gating（v5 设计）：
  Input (1,14) → Reshape (14,) → Dense(14) → Softmax → 与特征逐位相乘
                → Reshape (1,14) → LSTM(64) → LSTM(32) → Dropout(0.2) → Dense(1)

TIMESTEPS=1 时 timestep attention 无东西可注意，改在特征维学软掩码；
权重可与 XGB 时间模型 gain 重要性做对照（v6 未计算 SHAP）。

与 v6_04/v6_05 同 split / 同特征 / 同目标，三模型可比。

用法:
  python scripts/data/v6_06_train_att_lstm_lco.py                             # 官方口径 (seed 42, 省级 SPEI)
  python scripts/data/v6_06_train_att_lstm_lco.py --seeds 42,43,44,45,46      # 多种子稳健性
  python scripts/data/v6_06_train_att_lstm_lco.py --panel paper_panel_v6_climate_full.parquet  # 县级 SPEI 补跑
输出：reports/v6_att_lstm{_面板名}_report.md + 同名 fold/seed_results.csv + weights.csv（支持断点续跑）
"""
import argparse
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.stderr.reconfigure(encoding="utf-8", errors="replace")

import os
os.environ.setdefault("TF_CPP_MIN_LOG_LEVEL", "2")
os.environ.setdefault("TF_ENABLE_ONEDNN_OPTS", "0")

import tensorflow as tf
from sklearn.metrics import r2_score, mean_squared_error
from sklearn.model_selection import KFold
from sklearn.preprocessing import StandardScaler
from tensorflow.keras import Model
from tensorflow.keras.callbacks import EarlyStopping
from tensorflow.keras.layers import (
    LSTM, Dense, Dropout, Input, Multiply, Reshape, Softmax,
)

PROJECT_ROOT = Path(__file__).resolve().parents[2]
PANEL = PROJECT_ROOT / "data" / "interim" / "paper_panel_v6_climate.parquet"
REPORT = PROJECT_ROOT / "reports" / "v6_att_lstm_lco_report.md"
FOLDS = PROJECT_ROOT / "reports" / "v6_att_lstm_fold_results.csv"
WEIGHTS = PROJECT_ROOT / "reports" / "v6_att_lstm_weights.csv"

FEATURES = [
    "temp", "prec", "sun",
    "spei_annual_mean", "spei_growing_season_mean", "ndvi_yearly",
    "lst_day_growing_mean_k", "fert", "irr", "flood", "drou_a", "flood_a",
    "cropland_ratio", "log_sown",
]

TIMESTEPS = 1
LSTM_UNITS_1, LSTM_UNITS_2 = 64, 32
DROPOUT, BATCH_SIZE, EPOCHS, LR = 0.2, 16, 100, 1e-3
EARLY_STOP_PATIENCE = 10
RANDOM_STATE = 42


def build_att_model(n_features: int, seed: int = RANDOM_STATE) -> tuple[Model, Model]:
    """返回 (主模型, attention 权重提取模型)。"""
    tf.keras.utils.set_random_seed(seed)
    inp = Input((TIMESTEPS, n_features))
    flat = Reshape((n_features,))(inp)
    gate = Dense(n_features, activation="softmax", name="att_gate")(flat)  # 软掩码
    gated = Multiply()([flat, gate])
    x = Reshape((TIMESTEPS, n_features))(gated)
    x = LSTM(LSTM_UNITS_1, return_sequences=True)(x)
    x = LSTM(LSTM_UNITS_2)(x)
    x = Dropout(DROPOUT)(x)
    out = Dense(1)(x)
    model = Model(inp, out)
    model.compile(optimizer=tf.keras.optimizers.Adam(LR), loss="mse")
    att_model = Model(inp, model.get_layer("att_gate").output)
    return model, att_model


def main() -> int:
    parser = argparse.ArgumentParser(description="v6 Attention-LSTM LCO")
    parser.add_argument("--panel", type=str, default=str(PANEL),
                        help="特征矩阵 parquet 路径（如 paper_panel_v6_climate_full.parquet，县级 SPEI）")
    parser.add_argument("--seeds", type=str, default="42",
                        help="种子列表（逗号分隔，同时控制折划分与权重初始化；默认 42）")
    args = parser.parse_args()
    panel_path = Path(args.panel)
    # 非默认面板 → 报告加后缀区分（与 v6_04 同约定）; 默认保持官方文件名 v6_att_lstm_lco_report.md
    suffix = "" if panel_path.name == PANEL.name else f"_{panel_path.stem.replace('paper_panel_', '')}"
    report_path = REPORT if suffix == "" else Path(str(REPORT).replace("v6_att_lstm_lco_report.md", f"v6_att_lstm{suffix}_report.md"))
    folds_path = Path(str(FOLDS).replace("v6_att_lstm_fold_results.csv", f"v6_att_lstm{suffix}_fold_results.csv"))
    seed_csv_path = Path(str(folds_path).replace("_fold_results.csv", "_seed_results.csv"))
    weights_path = Path(str(WEIGHTS).replace("v6_att_lstm_weights.csv", f"v6_att_lstm{suffix}_weights.csv"))

    df = pd.read_parquet(panel_path)
    df = df[df["log_yield"].notna()].copy()
    df["log_sown"] = np.log1p(df["农作物总播种面积_千公顷"].fillna(0))
    df = df.dropna(subset=FEATURES)
    print(f"训练样本: {len(df)} 行, {df['区县代码'].nunique()} 县, {df['年份'].nunique()} 年 | 面板: {panel_path.name}")

    X = df[FEATURES].values.astype(np.float32)
    y = df["log_yield"].values.astype(np.float32)
    groups = df["区县代码"].values
    counties = np.unique(groups)

    seeds = [int(s) for s in args.seeds.split(",")]
    # ── 断点续跑: fold CSV 里已有的 seed 跳过 ──
    done = set()
    if folds_path.exists():
        try:
            done = set(pd.read_csv(folds_path, usecols=["seed"]).iloc[:, 0].astype(int))
        except Exception:
            done = set()
    todo = [s for s in seeds if s not in done]
    if todo != seeds:
        print(f"[resume] 已完成 seeds {sorted(done)}，本次只跑 {todo}")

    for seed in todo:
        print(f"\n── seed {seed} ──")
        # ── leave-county-out 10 折（折划分随 seed 变化）──
        kf = KFold(n_splits=10, shuffle=True, random_state=seed)
        fold_rows, preds, trues, w_rows = [], [], [], []
        for fold, (tr_i, te_i) in enumerate(kf.split(counties)):
            tr_c = set(counties[tr_i])
            tr_mask = np.isin(groups, list(tr_c))
            te_mask = ~tr_mask
            scaler = StandardScaler().fit(X[tr_mask])
            Xtr = scaler.transform(X[tr_mask]).reshape(-1, TIMESTEPS, len(FEATURES))
            Xte = scaler.transform(X[te_mask]).reshape(-1, TIMESTEPS, len(FEATURES))
            model, att_model = build_att_model(len(FEATURES), seed)
            model.fit(Xtr, y[tr_mask], batch_size=BATCH_SIZE, epochs=EPOCHS,
                      validation_split=0.1,
                      callbacks=[EarlyStopping(patience=EARLY_STOP_PATIENCE, restore_best_weights=True)],
                      verbose=0)
            p = model.predict(Xte, verbose=0).ravel()
            w = att_model.predict(Xtr, verbose=0).mean(axis=0)  # 训练集上的平均软掩码
            r2 = r2_score(y[te_mask], p)
            rmse = mean_squared_error(y[te_mask], p, squared=False)
            fold_rows.append({"seed": seed, "fold": fold + 1, "n_train": tr_mask.sum(), "n_test": te_mask.sum(),
                              "r2": round(r2, 4), "rmse": round(rmse, 4)})
            w_rows.append({"seed": seed, "fold": fold + 1, **{f: float(v) for f, v in zip(FEATURES, w)}})
            preds.append(p)
            trues.append(y[te_mask])
            print(f"  seed {seed} fold {fold + 1:>2}: R²={r2:+.4f} RMSE={rmse:.4f} (test n={te_mask.sum()})")

        overall_r2 = r2_score(np.concatenate(trues), np.concatenate(preds))
        overall_rmse = mean_squared_error(np.concatenate(trues), np.concatenate(preds), squared=False)
        print(f"  LCO overall: R²={overall_r2:+.4f}  RMSE={overall_rmse:.4f}")

        # ── 时间外推: train ≤2019 → test 2020-2023 ──
        tr_t = (df["年份"] <= 2019).values
        te_t = ~tr_t
        scaler_t = StandardScaler().fit(X[tr_t])
        Xt_tr = scaler_t.transform(X[tr_t]).reshape(-1, TIMESTEPS, len(FEATURES))
        Xt_te = scaler_t.transform(X[te_t]).reshape(-1, TIMESTEPS, len(FEATURES))
        model_t, _ = build_att_model(len(FEATURES), seed)
        model_t.fit(Xt_tr, y[tr_t], batch_size=BATCH_SIZE, epochs=EPOCHS,
                    validation_split=0.1,
                    callbacks=[EarlyStopping(patience=EARLY_STOP_PATIENCE, restore_best_weights=True)],
                    verbose=0)
        p_t = model_t.predict(Xt_te, verbose=0).ravel()
        time_r2 = r2_score(y[te_t], p_t)
        time_rmse = mean_squared_error(y[te_t], p_t, squared=False)
        print(f"  Time-holdout (≤2019→2020-22): R²={time_r2:+.4f} RMSE={time_rmse:.4f}")

        # ── 落盘（追加式，支持断点续跑）──
        folds_path.parent.mkdir(parents=True, exist_ok=True)
        pd.DataFrame(fold_rows).to_csv(folds_path, index=False,
                                       mode="a" if folds_path.exists() else "w",
                                       header=not folds_path.exists())
        pd.DataFrame(w_rows).to_csv(weights_path, index=False,
                                    mode="a" if weights_path.exists() else "w",
                                    header=not weights_path.exists())
        pd.DataFrame([{"seed": seed, "lco_r2": round(overall_r2, 4), "lco_rmse": round(overall_rmse, 4),
                       "time_r2": round(time_r2, 4), "time_rmse": round(time_rmse, 4)}]
                     ).to_csv(seed_csv_path, index=False,
                              mode="a" if seed_csv_path.exists() else "w",
                              header=not seed_csv_path.exists())

    fold_df = pd.read_csv(folds_path) if folds_path.exists() else pd.DataFrame()
    seed_df = pd.read_csv(seed_csv_path) if seed_csv_path.exists() else pd.DataFrame()
    w_df = pd.read_csv(weights_path) if weights_path.exists() else pd.DataFrame()
    # XGB 同面板参考值（省级 SPEI 0.6604 / 县级 SPEI 0.6625）
    xgb_ref = "0.6625" if suffix else "0.6604"

    # attention 权重均值表（论文与 XGB gain 重要性对照用；多种子取跨 seed 均值）
    w_mean = w_df.drop(columns=["seed", "fold"]).mean().sort_values(ascending=False)
    w_md = w_mean.rename_axis("feature").reset_index(name="att_weight").to_markdown(index=False)

    lstm_ref = "v6_lstm_lco_report.md" if not suffix else f"v6_lstm{suffix}_report.md"
    lines = [
        "# v6 Attention-LSTM Leave-County-Out 报告（feature-level attention gating）",
        "",
        f"- 样本: {len(df)} 行（{df['区县代码'].nunique()} 县 × {df['年份'].min()}–{df['年份'].max()} 非平衡面板，10 主产省；部分县缺 1–10 年，2023 年产量缺失）",
        f"- 面板: {panel_path.name}（{'县级 SPEI' if suffix else '省级 SPEI'}）",
        f"- 目标: log_yield  特征 ({len(FEATURES)}): " + ", ".join(FEATURES),
        "- 结构: Input→Reshape→Dense(softmax 软掩码)→Multiply→LSTM(64)→LSTM(32)→Dropout→Dense(1)",
        "",
        "## 多种子结果",
        "",
        seed_df.to_markdown(index=False),
        "",
        f"- 种子集: {', '.join(map(str, seeds))}。"
        + ("seed 42 行即官方 v2（R²=+0.0412，省级 SPEI，与首轮同 split 可比）。"
           if 42 in seeds and not suffix else "均值±std 报告多种子稳健性。"),
        "",
        "## 各折结果",
        "",
        fold_df.to_markdown(index=False),
        "",
        "## 特征 attention 权重均值（与 XGB 时间模型 gain 重要性对照，非 SHAP）",
        "",
        w_md,
        "",
        "## 对比",
        "",
        "| 版本 | CV | R² |",
        "|---|---|---|",
        f"| v6 XGBoost | LCO | +{xgb_ref} |",
        f"| v6 LSTM | LCO | 见 {lstm_ref} |",
        f"| v6 Attention-LSTM (本报告, seed {seeds[0]}) | LCO | {seed_df['lco_r2'].iloc[0]:+.4f} |",
        "",
    ]
    report_path.write_text("\n".join(lines), encoding="utf-8")
    print(f"✅ 报告 -> {report_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
