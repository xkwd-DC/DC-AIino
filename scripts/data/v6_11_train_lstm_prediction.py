#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""v6 Step 11：真时序 LSTM / Attention-LSTM 预测（滑动窗口 TIMESTEPS>1）。

背景：v6_05/v6_06 用 TIMESTEPS=1 把 LSTM 当 MLP，时序表达力为 0，LCO 仅 0.07。
本脚本改为**真时序**：按县内年份升序构造滑动窗口，用前 W 年特征序列 → 预测第 W+1 年目标。

目标（2 口径）：
  A. log_yield（绝对产量）
  B. y_anom（县 OLS 线性趋势残差 = 产量异常/增减产）

特征：县级气候 + 生长季/极端指数（可 --prov-ablate 剔除省-年恒量）。
协议：与 XGB 同 —— LCO 10 折按县分组 + 时间外推(≤2019→2020-22)；种子默认 42。

用法:
  python scripts/data/v6_11_train_lstm_prediction.py [--target log_yield|y_anom] [--prov-ablate] [--seeds 42]
输出: reports/v6_lstm_pred_{target}{_provablate}_report.md + fold csv
"""
import argparse
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.stderr.reconfigure(encoding="utf-8", errors="replace")

import os
os.environ.setdefault("TF_CPP_MIN_LOG_LEVEL", "2")
os.environ.setdefault("TF_ENABLE_ONEDNN_OPTS", "0")

import numpy as np
import pandas as pd
import tensorflow as tf
from sklearn.metrics import r2_score, mean_squared_error
from sklearn.model_selection import KFold
from sklearn.preprocessing import StandardScaler
from tensorflow.keras import Model
from tensorflow.keras.callbacks import EarlyStopping
from tensorflow.keras.layers import LSTM, Dense, Dropout, Input, Lambda, Multiply, Reshape, Softmax
from tensorflow.keras.models import Sequential

PROJECT_ROOT = Path(__file__).resolve().parents[2]
PANEL = PROJECT_ROOT / "data" / "interim" / "paper_panel_v7_prediction.parquet"

BASE = ["temp", "prec", "sun",
        "spei_annual_mean", "spei_growing_season_mean", "ndvi_yearly",
        "lst_day_growing_mean_k", "fert", "irr", "flood", "drou_a", "flood_a",
        "cropland_ratio", "log_sown"]
SEASONAL = ["gs_tmax_mean", "gs_tmin_mean", "gs_ppt", "gs_srad", "gs_pet",
            "gdd10", "gs_aridity", "prec_cv", "gs_prec_share",
            "winter_temp", "seasonal_temp_range"]
PROV_SHARED = ["spei_annual_mean", "spei_growing_season_mean", "ndvi_yearly",
               "lst_day_growing_mean_k", "fert", "irr", "flood", "drou_a",
               "flood_a", "cropland_ratio"]

WINDOW = 3
LSTM_UNITS_1, LSTM_UNITS_2 = 64, 32
DROPOUT, BATCH_SIZE, EPOCHS, LR = 0.2, 32, 120, 1e-3
EARLY_STOP_PATIENCE = 12


def detrend_county(df, y_col="log_yield", id_col="区县代码", yr_col="年份", min_pts=3):
    out = pd.Series(np.nan, index=df.index, dtype=float)
    for cid, g in df.groupby(id_col):
        y = g[y_col].values.astype(float); t = g[yr_col].values.astype(float)
        if len(t) >= min_pts:
            trend = np.polyval(np.polyfit(t, y, 1), t)
        else:
            trend = np.full(len(t), y.mean())
        out.loc[g.index] = y - trend
    return out


def build_seq(df, feats, target, window=WINDOW, id_col="区县代码", yr_col="年份"):
    """按县构造滑动窗口序列。返回 (X_seq, y, group) 与对齐的目标行。"""
    rows, yrows = [], []
    for cid, g in df.sort_values(yr_col).groupby(id_col):
        g = g.reset_index(drop=True)
        x = g[feats].values.astype(np.float32)
        yv = g[target].values.astype(np.float32)
        for t in range(len(g) - window):
            rows.append(x[t:t + window])
            yrows.append(yv[t + window])
    return np.asarray(rows, dtype=np.float32), np.asarray(yrows, dtype=np.float32)


def build_lstm(n_features, seed=42):
    tf.keras.utils.set_random_seed(seed)
    m = Sequential([
        Input((WINDOW, n_features)),
        LSTM(LSTM_UNITS_1, return_sequences=True),
        LSTM(LSTM_UNITS_2),
        Dropout(DROPOUT),
        Dense(1),
    ])
    m.compile(optimizer=tf.keras.optimizers.Adam(LR), loss="mse")
    return m


def build_att(n_features, seed=42):
    tf.keras.utils.set_random_seed(seed)
    inp = Input((WINDOW, n_features))
    # timestep-wise attention（真时序下用时间步注意更自然）
    x = LSTM(LSTM_UNITS_1, return_sequences=True)(inp)
    x = LSTM(LSTM_UNITS_2, return_sequences=True)(x)
    x = Dropout(DROPOUT)(x)
    # 时间维 softmax 注意力
    att = Dense(1, activation="tanh")(x)
    att = Softmax(axis=1)(att)
    h = Multiply()([x, att])
    h = Lambda(lambda z: tf.reduce_sum(z, axis=1))(h)
    out = Dense(1)(h)
    m = Model(inp, out)
    m.compile(optimizer=tf.keras.optimizers.Adam(LR), loss="mse")
    return m


def main() -> int:
    parser = argparse.ArgumentParser(description="真时序 LSTM/Att-LSTM 产量异常预测")
    parser.add_argument("--panel", type=str, default=str(PANEL))
    parser.add_argument("--target", type=str, default="log_yield", choices=["log_yield", "y_anom"])
    parser.add_argument("--prov-ablate", action="store_true")
    parser.add_argument("--seeds", type=str, default="42")
    parser.add_argument("--model", type=str, default="lstm", choices=["lstm", "att"])
    args = parser.parse_args()

    panel_path = Path(args.panel)
    df = pd.read_parquet(panel_path)
    df = df[df["log_yield"].notna()].copy()
    df["log_sown"] = np.log1p(df["农作物总播种面积_千公顷"].fillna(0))
    df["y_anom"] = detrend_county(df)
    feats = BASE + SEASONAL
    if args.prov_ablate:
        feats = [f for f in feats if f not in PROV_SHARED]
    df = df.dropna(subset=feats + ["年份", "区县代码"])
    print(f"采样: {len(df)} 行, {df['区县代码'].nunique()} 县 | 特征 {len(feats)} | 目标 {args.target} | model {args.model}")

    X, y = build_seq(df, feats, args.target)
    # group：每窗口的县（取该行所在县）
    gseq = []
    for cid, g in df.sort_values("年份").groupby("区县代码"):
        gseq += [cid] * (len(g) - WINDOW)
    groups = np.asarray(gseq)
    print(f"序列: {X.shape[0]} 窗口, {len(np.unique(groups))} 县")

    seeds = [int(s) for s in args.seeds.split(",")]
    suffix = f"_{args.target}" + ("_provablate" if args.prov_ablate else "") + f"_{args.model}"
    report_path = PROJECT_ROOT / "reports" / f"v6_lstm_pred{suffix}_report.md"
    folds_path = PROJECT_ROOT / "reports" / f"v6_lstm_pred{suffix}_fold_results.csv"

    rows, seed_rows = [], []
    for seed in seeds:
        print(f"\n── seed {seed} ──")
        kf = KFold(n_splits=10, shuffle=True, random_state=seed)
        counties = np.unique(groups)
        preds, trues = [], []
        for fold, (tr_i, te_i) in enumerate(kf.split(counties)):
            tr_c = set(counties[tr_i])
            tr_mask = np.isin(groups, list(tr_c))
            te_mask = ~tr_mask
            scaler = StandardScaler().fit(X[tr_mask].reshape(-1, X.shape[-1]))
            Xtr = scaler.transform(X[tr_mask].reshape(-1, X.shape[-1])).reshape(-1, WINDOW, X.shape[-1])
            Xte = scaler.transform(X[te_mask].reshape(-1, X.shape[-1])).reshape(-1, WINDOW, X.shape[-1])
            model = build_att(len(feats), seed) if args.model == "att" else build_lstm(len(feats), seed)
            model.fit(Xtr, y[tr_mask], batch_size=BATCH_SIZE, epochs=EPOCHS,
                      validation_split=0.1, shuffle=False,
                      callbacks=[EarlyStopping(patience=EARLY_STOP_PATIENCE, restore_best_weights=True)],
                      verbose=0)
            p = model.predict(Xte, verbose=0).ravel()
            r2 = r2_score(y[te_mask], p); rmse = mean_squared_error(y[te_mask], p, squared=False)
            rows.append({"seed": seed, "fold": fold + 1, "r2": round(r2, 4), "rmse": round(rmse, 4),
                         "n_train": tr_mask.sum(), "n_test": te_mask.sum()})
            preds.append(p); trues.append(y[te_mask])
        overall_r2 = r2_score(np.concatenate(trues), np.concatenate(preds))
        overall_rmse = mean_squared_error(np.concatenate(trues), np.concatenate(preds), squared=False)
        print(f"  LCO overall: R²={overall_r2:+.4f}  RMSE={overall_rmse:.4f}")

        # 时间外推：训练窗口终止年 ≤2019
        # 窗口对应目标年是 g 序列的 t+WINDOW 年；用 df 年份近似：窗口末年 ≤ 2019-? 复杂，改用按目标年
        # 简化：以窗口起点构造目标年
        # 重建 窗口→目标年 映射
        target_years = []
        for cid, g in df.sort_values("年份").groupby("区县代码"):
            yrs = g["年份"].values
            target_years += list(yrs[WINDOW:])
        ty = np.asarray(target_years, dtype=int)
        tr_t = ty <= 2019
        te_t = ~tr_t
        scaler_t = StandardScaler().fit(X[tr_t].reshape(-1, X.shape[-1]))
        Xt_tr = scaler_t.transform(X[tr_t].reshape(-1, X.shape[-1])).reshape(-1, WINDOW, X.shape[-1])
        Xt_te = scaler_t.transform(X[te_t].reshape(-1, X.shape[-1])).reshape(-1, WINDOW, X.shape[-1])
        model_t = build_att(len(feats), seed) if args.model == "att" else build_lstm(len(feats), seed)
        model_t.fit(Xt_tr, y[tr_t], batch_size=BATCH_SIZE, epochs=EPOCHS,
                    validation_split=0.1, shuffle=False,
                    callbacks=[EarlyStopping(patience=EARLY_STOP_PATIENCE, restore_best_weights=True)], verbose=0)
        p_t = model_t.predict(Xt_te, verbose=0).ravel()
        time_r2 = r2_score(y[te_t], p_t); time_rmse = mean_squared_error(y[te_t], p_t, squared=False)
        print(f"  Time-holdout (≤2019→2020-22): R²={time_r2:+.4f} RMSE={time_rmse:.4f}")

        seed_rows.append({"seed": seed, "lco_r2": round(overall_r2, 4), "lco_rmse": round(overall_rmse, 4),
                          "time_r2": round(time_r2, 4), "time_rmse": round(time_rmse, 4)})

    pd.DataFrame(rows).to_csv(folds_path, index=False)
    lines = [
        "# v6 真时序 LSTM 产量异常预测报告",
        "",
        f"- 面板: {panel_path.name} | 模型: {args.model} | 窗口: {WINDOW} 年",
        f"- 目标: **{args.target}**" + ("（绝对产量）" if args.target == "log_yield" else "（县趋势残差=产量异常）"),
        f"- 特征 ({len(feats)}): " + ", ".join(feats),
        f"- 协议: LCO 10 折按县分组 + 时间外推(≤2019→2020-22); 种子 {', '.join(map(str, seeds))}",
        "",
        "## 多种子结果",
        "",
    ]
    lines += _to_md(pd.DataFrame(seed_rows)).split("\n")
    lines += ["", "## 各折结果", "", ] + _to_md(pd.DataFrame(rows)).split("\n")
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text("\n".join(lines), encoding="utf-8")
    print(f"✅ 报告 -> {report_path}")
    return 0


def _to_md(df):
    cols = list(df.columns)
    header = "| " + " | ".join(str(c) for c in cols) + " |"
    sep = "|" + "|".join("---" for _ in cols) + "|"
    body = "\n".join("| " + " | ".join(str(v) for v in row) + " |" for row in df.itertuples(index=False))
    return "\n".join([header, sep, body])


if __name__ == "__main__":
    sys.exit(main())
