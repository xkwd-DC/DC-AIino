#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""v6 Step 5：LSTM leave-county-out（与 v6_04 XGB 同 split / 同特征 / 同目标，可比）。

数据：data/interim/paper_panel_v6_climate.parquet
样本：log_yield 非空 + 14 维特征非空（同 v6_04，10,407 行）
目标：log_yield（与 v6_04 XGB 同口径）
CV：KFold(10, shuffle=True, random_state=42) 按县分组 —— 与 v6_04 完全同 split
时间外推：训练 ≤2019 → 测试 2020-2022（2023 年产量缺失）
结构：TIMESTEPS=1（v5 惯例：把 LSTM 当非线性回归器）
      Input(1,14) → LSTM(96) → LSTM(48) → Dropout(0.2) → Dense(1)
      StandardScaler 仅在训练折 fit，测试折 transform（防泄漏）

输出：reports/v6_lstm_lco_report.md + reports/v6_lstm_fold_results.csv
"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd

# Windows GBK console 下 ²/✅ 等字符会 UnicodeEncodeError；强制 UTF-8 输出
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.stderr.reconfigure(encoding="utf-8", errors="replace")

import os
os.environ.setdefault("TF_CPP_MIN_LOG_LEVEL", "2")
os.environ.setdefault("TF_ENABLE_ONEDNN_OPTS", "0")

import tensorflow as tf
from sklearn.metrics import r2_score, mean_squared_error
from sklearn.model_selection import KFold
from sklearn.preprocessing import StandardScaler
from tensorflow.keras.callbacks import EarlyStopping
from tensorflow.keras.layers import Dense, Dropout, Input, LSTM
from tensorflow.keras.models import Sequential

PROJECT_ROOT = Path(__file__).resolve().parents[2]
PANEL = PROJECT_ROOT / "data" / "interim" / "paper_panel_v6_climate.parquet"
REPORT = PROJECT_ROOT / "reports" / "v6_lstm_lco_report.md"
FOLDS = PROJECT_ROOT / "reports" / "v6_lstm_fold_results.csv"

# 与 v6_04 完全相同的特征集合
FEATURES = [
    "temp", "prec", "sun",
    "spei_annual_mean", "spei_growing_season_mean", "ndvi_yearly",
    "lst_day_growing_mean_k", "fert", "irr", "flood", "drou_a", "flood_a",
    "cropland_ratio", "log_sown",
]

TIMESTEPS = 1
LSTM_UNITS_1, LSTM_UNITS_2 = 96, 48
DROPOUT, BATCH_SIZE, EPOCHS, LR = 0.2, 32, 300, 1e-3
EARLY_STOP_PATIENCE = 30
RANDOM_STATE = 42


def build_model(n_features: int) -> Sequential:
    tf.keras.utils.set_random_seed(RANDOM_STATE)
    model = Sequential([
        Input((TIMESTEPS, n_features)),
        LSTM(LSTM_UNITS_1, return_sequences=True),
        LSTM(LSTM_UNITS_2),
        Dropout(DROPOUT),
        Dense(1),
    ])
    model.compile(optimizer=tf.keras.optimizers.Adam(LR), loss="mse")
    return model


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

    # ── leave-county-out 10 折（与 v6_04 同 split）──
    kf = KFold(n_splits=10, shuffle=True, random_state=RANDOM_STATE)
    rows, preds, trues = [], [], []
    for fold, (tr_i, te_i) in enumerate(kf.split(counties)):
        tr_c = set(counties[tr_i])
        tr_mask = np.isin(groups, list(tr_c))
        te_mask = ~tr_mask
        scaler = StandardScaler().fit(X[tr_mask])
        Xtr = scaler.transform(X[tr_mask]).reshape(-1, TIMESTEPS, len(FEATURES))
        Xte = scaler.transform(X[te_mask]).reshape(-1, TIMESTEPS, len(FEATURES))
        model = build_model(len(FEATURES))
        model.fit(Xtr, y[tr_mask], batch_size=BATCH_SIZE, epochs=EPOCHS,
                  validation_split=0.1,
                  callbacks=[EarlyStopping(patience=EARLY_STOP_PATIENCE, restore_best_weights=True)],
                  verbose=0)
        p = model.predict(Xte, verbose=0).ravel()
        r2 = r2_score(y[te_mask], p)
        rmse = mean_squared_error(y[te_mask], p, squared=False)
        rows.append({"fold": fold + 1, "n_train": tr_mask.sum(), "n_test": te_mask.sum(),
                     "r2": round(r2, 4), "rmse": round(rmse, 4)})
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
    model_t = build_model(len(FEATURES))
    model_t.fit(Xt_tr, y[tr_t], batch_size=BATCH_SIZE, epochs=EPOCHS,
                validation_split=0.1,
                callbacks=[EarlyStopping(patience=EARLY_STOP_PATIENCE, restore_best_weights=True)],
                verbose=0)
    p_t = model_t.predict(Xt_te, verbose=0).ravel()
    time_r2 = r2_score(y[te_t], p_t)
    time_rmse = mean_squared_error(y[te_t], p_t, squared=False)
    print(f"Time-holdout (≤2019→2020-22): R²={time_r2:+.4f} RMSE={time_rmse:.4f}")

    fold_df = pd.DataFrame(rows)
    FOLDS.parent.mkdir(parents=True, exist_ok=True)
    fold_df.to_csv(FOLDS, index=False)

    lines = [
        "# v6 LSTM Leave-County-Out 报告（与 XGB 同 split 可比）",
        "",
        f"- 样本: {len(df)} 行（{df['区县代码'].nunique()} 县 × {df['年份'].min()}–{df['年份'].max()} 非平衡面板，10 主产省；部分县缺 1–10 年，2023 年产量缺失）",
        f"- 目标: log_yield = log(粮食总产量_吨)  特征 ({len(FEATURES)}): " + ", ".join(FEATURES),
        f"- 结构: LSTM(96)→LSTM(48)→Dropout(0.2)→Dense(1), TIMESTEPS=1, LR={LR}, EPOCHS={EPOCHS}",
        f"- LCO overall R² = **{overall_r2:+.4f}** (RMSE {overall_rmse:.4f})",
        f"- 时间外推 R² (≤2019 → 2020-22，2023 年产量缺失) = **{time_r2:+.4f}** (RMSE {time_rmse:.4f})",
        "",
        "## 各折结果",
        "",
        fold_df.to_markdown(index=False),
        "",
        "## 对比",
        "",
        "| 版本 | CV | R² |",
        "|---|---|---|",
        "| v6 XGBoost | LCO | +0.6604 |",
        f"| v6 LSTM (本报告) | LCO | {overall_r2:+.4f} |",
        f"| v6 时间外推 | ≤2019→20-22 | {time_r2:+.4f} |",
        "",
    ]
    REPORT.write_text("\n".join(lines), encoding="utf-8")
    print(f"✅ 报告 -> {REPORT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
