#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""v6 Step 6：Attention-LSTM leave-county-out（feature-level attention gating）。

在 v6_05 LSTM 上增加 feature-level attention gating（v5 设计）：
  Input (1,14) → Reshape (14,) → Dense(14) → Softmax → 与特征逐位相乘
                → Reshape (1,14) → LSTM(64) → LSTM(32) → Dropout(0.2) → Dense(1)

TIMESTEPS=1 时 timestep attention 无东西可注意，改在特征维学软掩码；
权重可与 XGB SHAP 做"一致性"对照（论文三模型互补归因）。

与 v6_04/v6_05 同 split / 同特征 / 同目标，三模型可比。

输出：reports/v6_att_lstm_lco_report.md + v6_att_lstm_fold_results.csv
      + reports/v6_att_lstm_weights.csv（各折 attention 权重均值，供 SHAP 对照）
"""
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


def build_att_model(n_features: int) -> tuple[Model, Model]:
    """返回 (主模型, attention 权重提取模型)。"""
    tf.keras.utils.set_random_seed(RANDOM_STATE)
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
    df = pd.read_parquet(PANEL)
    df = df[df["log_yield"].notna()].copy()
    df["log_sown"] = np.log1p(df["农作物总播种面积_千公顷"].fillna(0))
    df = df.dropna(subset=FEATURES)
    print(f"训练样本: {len(df)} 行, {df['区县代码'].nunique()} 县, {df['年份'].nunique()} 年")

    X = df[FEATURES].values.astype(np.float32)
    y = df["log_yield"].values.astype(np.float32)
    groups = df["区县代码"].values
    counties = np.unique(groups)

    # ── leave-county-out 10 折（与 v6_04/v6_05 同 split）──
    kf = KFold(n_splits=10, shuffle=True, random_state=RANDOM_STATE)
    rows, preds, trues, w_rows = [], [], [], []
    for fold, (tr_i, te_i) in enumerate(kf.split(counties)):
        tr_c = set(counties[tr_i])
        tr_mask = np.isin(groups, list(tr_c))
        te_mask = ~tr_mask
        scaler = StandardScaler().fit(X[tr_mask])
        Xtr = scaler.transform(X[tr_mask]).reshape(-1, TIMESTEPS, len(FEATURES))
        Xte = scaler.transform(X[te_mask]).reshape(-1, TIMESTEPS, len(FEATURES))
        model, att_model = build_att_model(len(FEATURES))
        model.fit(Xtr, y[tr_mask], batch_size=BATCH_SIZE, epochs=EPOCHS,
                  validation_split=0.1,
                  callbacks=[EarlyStopping(patience=EARLY_STOP_PATIENCE, restore_best_weights=True)],
                  verbose=0)
        p = model.predict(Xte, verbose=0).ravel()
        w = att_model.predict(Xtr, verbose=0).mean(axis=0)  # 训练集上的平均软掩码
        r2 = r2_score(y[te_mask], p)
        rmse = mean_squared_error(y[te_mask], p, squared=False)
        rows.append({"fold": fold + 1, "n_train": tr_mask.sum(), "n_test": te_mask.sum(),
                     "r2": round(r2, 4), "rmse": round(rmse, 4)})
        w_rows.append({"fold": fold + 1, **{f: float(v) for f, v in zip(FEATURES, w)}})
        preds.append(p)
        trues.append(y[te_mask])
        print(f"  fold {fold + 1:>2}: R²={r2:+.4f} RMSE={rmse:.4f} (test n={te_mask.sum()})")

    overall_r2 = r2_score(np.concatenate(trues), np.concatenate(preds))
    overall_rmse = mean_squared_error(np.concatenate(trues), np.concatenate(preds), squared=False)
    print(f"\nLCO overall: R²={overall_r2:+.4f}  RMSE={overall_rmse:.4f}")

    # ── 时间外推: train ≤2019 → test 2020-2023 ──
    tr_t = (df["年份"] <= 2019).values
    te_t = ~tr_t
    scaler_t = StandardScaler().fit(X[tr_t])
    Xt_tr = scaler_t.transform(X[tr_t]).reshape(-1, TIMESTEPS, len(FEATURES))
    Xt_te = scaler_t.transform(X[te_t]).reshape(-1, TIMESTEPS, len(FEATURES))
    model_t, _ = build_att_model(len(FEATURES))
    model_t.fit(Xt_tr, y[tr_t], batch_size=BATCH_SIZE, epochs=EPOCHS,
                validation_split=0.1,
                callbacks=[EarlyStopping(patience=EARLY_STOP_PATIENCE, restore_best_weights=True)],
                verbose=0)
    p_t = model_t.predict(Xt_te, verbose=0).ravel()
    time_r2 = r2_score(y[te_t], p_t)
    time_rmse = mean_squared_error(y[te_t], p_t, squared=False)
    print(f"Time-holdout (≤2019→2020-23): R²={time_r2:+.4f} RMSE={time_rmse:.4f}")

    fold_df = pd.DataFrame(rows)
    FOLDS.parent.mkdir(parents=True, exist_ok=True)
    fold_df.to_csv(FOLDS, index=False)
    pd.DataFrame(w_rows).to_csv(WEIGHTS, index=False)

    # attention 权重均值表（论文与 SHAP 对照用）
    w_mean = pd.DataFrame(w_rows).drop(columns="fold").mean().sort_values(ascending=False)
    w_md = w_mean.rename_axis("feature").reset_index(name="att_weight").to_markdown(index=False)

    lines = [
        "# v6 Attention-LSTM Leave-County-Out 报告（feature-level attention gating）",
        "",
        f"- 样本: {len(df)} 行 = {df['区县代码'].nunique()} 县 × {df['年份'].nunique()} 年（10 主产省）",
        f"- 目标: log_yield  特征 ({len(FEATURES)}): " + ", ".join(FEATURES),
        "- 结构: Input→Reshape→Dense(softmax 软掩码)→Multiply→LSTM(64)→LSTM(32)→Dropout→Dense(1)",
        f"- LCO overall R² = **{overall_r2:+.4f}** (RMSE {overall_rmse:.4f})",
        f"- 时间外推 R² (≤2019 → 2020-23) = **{time_r2:+.4f}** (RMSE {time_rmse:.4f})",
        "",
        "## 各折结果",
        "",
        fold_df.to_markdown(index=False),
        "",
        "## 特征 attention 权重均值（与 XGB SHAP 对照）",
        "",
        w_md,
        "",
        "## 对比",
        "",
        "| 版本 | CV | R² |",
        "|---|---|---|",
        "| v6 XGBoost | LCO | +0.6604 |",
        "| v6 LSTM | LCO | 见 v6_lstm_lco_report.md |",
        f"| v6 Attention-LSTM (本报告) | LCO | {overall_r2:+.4f} |",
        "",
    ]
    REPORT.write_text("\n".join(lines), encoding="utf-8")
    print(f"✅ 报告 -> {REPORT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
