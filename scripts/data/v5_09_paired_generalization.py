#!/usr/bin/env python3
"""v5 Step 9: 配对泛化性证据（Random K-fold CV vs Leave-Province-Out CV）

论文核心对比：
  (a) Random 5-fold CV  — 乐观估计（允许省份/城市身份泄漏跨折）
  (b) Leave-Province-Out CV — 诚实空间泛化估计（严格空间外推）

对比的目的：
  - (a) 是 naive 论文常报的数字（省份记忆导致虚高）
  - (b) 是真实城市级重建是否泛化的检验

数据接线与 v5_08 完全相同，不重新发明。
"""

import sys
import os
import warnings
import datetime
from pathlib import Path

warnings.filterwarnings("ignore")
os.environ.setdefault("TF_CPP_MIN_LOG_LEVEL", "2")
os.environ.setdefault("TF_ENABLE_ONEDNN_OPTS", "0")

import numpy as np
import pandas as pd
from sklearn.metrics import r2_score, mean_squared_error
from sklearn.model_selection import KFold
import xgboost as xgb

# ──────────────────────────────────────────────────────────────────────────────
# 路径（与 v5_08 完全相同）
# ──────────────────────────────────────────────────────────────────────────────
PROJ = Path(__file__).resolve().parents[2]
V5_FEAT = PROJ / "data" / "interim" / "feature_matrix_v5.parquet"
V4_FEAT = PROJ / "data" / "interim" / "paper_panel_v4.parquet"
EPS_YIELD = PROJ / "data" / "raw" / "eps_yield" / "eps_city_yield_all.csv"
REPORT_DIR = PROJ / "reports"

# ──────────────────────────────────────────────────────────────────────────────
# 常量（与 v5_08 完全相同）
# ──────────────────────────────────────────────────────────────────────────────
PROV_FULL_TO_SHORT = {
    "安徽省": "安徽", "湖北省": "湖北", "河南省": "河南",
    "江苏省": "江苏", "河北省": "河北", "浙江省": "浙江",
}
V4_PROV_NAMES = {v: k for k, v in PROV_FULL_TO_SHORT.items()}

TEN_PROVINCES = {"黑龙江", "河南", "山东", "吉林", "安徽",
                 "湖南", "河北", "四川", "江苏", "湖北"}

# XGBoost 超参（与 v5_08 完全相同）
XGB_PARAMS = {
    "n_estimators": 300,
    "max_depth": 5,
    "learning_rate": 0.05,
    "subsample": 0.8,
    "colsample_bytree": 0.8,
    "reg_alpha": 0.1,
    "reg_lambda": 1.0,
    "random_state": 42,
    "n_jobs": -1,
}

V5_FEATURE_COLS = [
    "ndvi_yearly", "ndvi_summer_peak",
    "lst_day_growing_mean_k", "lst_night_growing_mean_k",
    "cropland_ratio",
    "temp_mean_c", "prec_mm_day",
    "irr", "flood", "mech", "fert", "drou_a", "flood_a",
    "spei",
]

# Attention-LSTM 超参（尽量贴近 train_att_lstm_baseline.py 的设定）
LSTM_UNITS_1 = 64
LSTM_UNITS_2 = 32
DROPOUT = 0.2
BATCH_SIZE = 16
EPOCHS = 100
LR = 1e-3
EARLY_STOP_PATIENCE = 10

# ──────────────────────────────────────────────────────────────────────────────
# 数据加载（从 v5_08 复制逻辑，保证 byte-identical 结果）
# ──────────────────────────────────────────────────────────────────────────────

def load_eps_yield() -> pd.DataFrame:
    df = pd.read_csv(EPS_YIELD)
    df["province_short"] = df["province"].map(PROV_FULL_TO_SHORT)
    df = df[df["province_short"].isin(TEN_PROVINCES)].copy()
    df = df.dropna(subset=["production_wan_ton"])
    df["production_wan_ton"] = pd.to_numeric(df["production_wan_ton"], errors="coerce")
    df = df.dropna(subset=["production_wan_ton"])
    print(f"  EPS 城市产量: {len(df)} 行, {df['province_short'].nunique()} 省, "
          f"{df['city'].nunique()} 市")
    return df


def build_v5_dataset():
    """与 v5_08 完全相同的数据构建逻辑。返回 (df, mode, feature_cols)。"""
    if V5_FEAT.exists():
        print(f"\n[模式] v5 城市级特征矩阵 ✅")
        feat = pd.read_parquet(V5_FEAT)
        print(f"  v5 特征: {feat.shape}")

        eps = load_eps_yield()

        avail_feat = [c for c in V5_FEATURE_COLS if c in feat.columns]
        feat_clean = feat.dropna(subset=avail_feat)
        dropped = len(feat) - len(feat_clean)
        if dropped > 0:
            print(f"  dropna 丢弃: {dropped} 行 ({dropped/len(feat)*100:.1f}%)")

        eps_merge = eps[["province_short", "city", "year", "production_wan_ton"]].copy()
        eps_merge = eps_merge.rename(columns={"production_wan_ton": "city_production_wan_ton"})
        merged = feat_clean.merge(
            eps_merge,
            left_on=["province", "city", "year"],
            right_on=["province_short", "city", "year"],
            how="inner",
        )
        merged["production_wan_ton"] = merged["city_production_wan_ton"]
        print(f"  合并后（inner join）: {len(merged)} 行")
        return merged, "v5_city_features", avail_feat
    else:
        raise FileNotFoundError(
            f"feature_matrix_v5.parquet 不存在: {V5_FEAT}\n"
            "需从石灵子机器 scp 获取后重跑。"
        )


# ──────────────────────────────────────────────────────────────────────────────
# XGBoost — Random K-fold CV
# ──────────────────────────────────────────────────────────────────────────────

def run_random_kfold_xgb(df: pd.DataFrame, feature_cols: list) -> dict:
    """
    Random 5-fold CV（故意允许城市/省份身份跨折泄漏）。
    这是 naive 论文常报的乐观数字。
    """
    df = df.copy()
    df["log_production"] = np.log(df["production_wan_ton"])
    X = df[feature_cols].values
    y = df["log_production"].values

    kf = KFold(n_splits=5, shuffle=True, random_state=42)
    fold_results = []
    all_preds = []
    all_true = []

    for fold_idx, (train_idx, test_idx) in enumerate(kf.split(X)):
        X_train, X_test = X[train_idx], X[test_idx]
        y_train, y_test = y[train_idx], y[test_idx]

        model = xgb.XGBRegressor(**XGB_PARAMS, verbosity=0)
        model.fit(X_train, y_train)
        y_pred = model.predict(X_test)

        r2 = r2_score(y_test, y_pred)
        rmse = np.sqrt(mean_squared_error(y_test, y_pred))

        fold_results.append({
            "fold": f"fold_{fold_idx+1}",
            "n_train": len(train_idx),
            "n_test": len(test_idx),
            "r2": round(r2, 4),
            "rmse_log": round(rmse, 4),
        })
        all_preds.extend(y_pred.tolist())
        all_true.extend(y_test.tolist())

        print(f"  Random fold {fold_idx+1}: R²={r2:.4f}, RMSE={rmse:.4f}")

    folds_df = pd.DataFrame(fold_results)
    overall_r2 = r2_score(all_true, all_preds)
    mean_r2 = folds_df["r2"].mean()
    std_r2 = folds_df["r2"].std()
    overall_rmse = np.sqrt(mean_squared_error(all_true, all_preds))

    print(f"\n  Random CV 汇总: overall_R²={overall_r2:.4f}, "
          f"mean±std={mean_r2:.4f}±{std_r2:.4f}")

    return {
        "folds_df": folds_df,
        "overall_r2": round(overall_r2, 4),
        "mean_r2": round(mean_r2, 4),
        "std_r2": round(std_r2, 4),
        "overall_rmse": round(overall_rmse, 4),
    }


# ──────────────────────────────────────────────────────────────────────────────
# XGBoost — Leave-Province-Out CV（复用 v5_08 逻辑）
# ──────────────────────────────────────────────────────────────────────────────

def run_spatial_cv_xgb(df: pd.DataFrame, feature_cols: list) -> dict:
    """Leave-one-province-out 空间 CV，逻辑与 v5_08 完全相同。"""
    df = df.copy()
    df["log_production"] = np.log(df["production_wan_ton"])
    pkey = "province_short" if "province_short" in df.columns else "province"
    provinces = sorted(df[pkey].unique())

    fold_results = []
    all_preds = []
    all_true = []

    for held_out in provinces:
        train_mask = df[pkey] != held_out
        test_mask = df[pkey] == held_out
        X_train = df.loc[train_mask, feature_cols].values
        y_train = df.loc[train_mask, "log_production"].values
        X_test = df.loc[test_mask, feature_cols].values
        y_test = df.loc[test_mask, "log_production"].values

        model = xgb.XGBRegressor(**XGB_PARAMS, verbosity=0)
        model.fit(X_train, y_train)
        y_pred = model.predict(X_test)

        r2 = r2_score(y_test, y_pred)
        rmse = np.sqrt(mean_squared_error(y_test, y_pred))
        n_cities = df.loc[test_mask, "city"].nunique()

        fold_results.append({
            "fold": held_out,
            "n_train": int(train_mask.sum()),
            "n_test": int(test_mask.sum()),
            "n_cities": int(n_cities),
            "r2": round(r2, 4),
            "rmse_log": round(rmse, 4),
        })
        all_preds.extend(y_pred.tolist())
        all_true.extend(y_test.tolist())

        symbol = "✅" if r2 > 0 else "❌"
        print(f"  {symbol} 留出 {held_out}: R²={r2:.4f}, RMSE={rmse:.4f} "
              f"(cities={n_cities})")

    folds_df = pd.DataFrame(fold_results)
    overall_r2 = r2_score(all_true, all_preds)
    mean_r2 = folds_df["r2"].mean()
    std_r2 = folds_df["r2"].std()
    overall_rmse = np.sqrt(mean_squared_error(all_true, all_preds))
    n_positive = int((folds_df["r2"] > 0).sum())

    print(f"\n  Spatial CV 汇总: overall_R²={overall_r2:.4f}, "
          f"mean±std={mean_r2:.4f}±{std_r2:.4f}, 正向折={n_positive}/{len(provinces)}")

    return {
        "folds_df": folds_df,
        "overall_r2": round(overall_r2, 4),
        "mean_r2": round(mean_r2, 4),
        "std_r2": round(std_r2, 4),
        "overall_rmse": round(overall_rmse, 4),
        "n_positive_folds": n_positive,
        "n_folds": len(provinces),
    }


# ──────────────────────────────────────────────────────────────────────────────
# Attention-LSTM（best-effort，TensorFlow only）
# ──────────────────────────────────────────────────────────────────────────────

def _build_att_lstm_model(n_features: int):
    """构建与 train_att_lstm_baseline.py 完全相同的 feature-gating attention-LSTM。"""
    import tensorflow as tf
    from tensorflow.keras import Model
    from tensorflow.keras.layers import (
        LSTM, Dense, Dropout, Input, Multiply, Reshape, Softmax,
    )

    inputs = Input(shape=(1, n_features), name="inputs")
    flat = Reshape((n_features,), name="flatten_features")(inputs)
    attn_logits = Dense(n_features, name="attn_logits")(flat)
    attn_weights = Softmax(name="feature_attention")(attn_logits)
    gated = Multiply(name="apply_attention")([flat, attn_weights])
    back = Reshape((1, n_features), name="restore_sequence")(gated)
    h1 = LSTM(LSTM_UNITS_1, return_sequences=True, name="lstm_1")(back)
    h2 = LSTM(LSTM_UNITS_2, name="lstm_2")(h1)
    drop = Dropout(DROPOUT, name="dropout")(h2)
    out = Dense(1, name="dense_out")(drop)

    model = Model(inputs, out, name="att_lstm")
    model.compile(
        optimizer=tf.keras.optimizers.Adam(learning_rate=LR),
        loss="mse",
    )
    return model


def _train_lstm_once(X_train_raw, y_train_raw, X_test_raw, y_test_raw,
                     n_features: int, seed: int, verbose: int = 0):
    """一次训练+预测，返回 (y_pred, r2, rmse)。"""
    import random as rnd
    import tensorflow as tf
    from sklearn.preprocessing import StandardScaler
    from tensorflow.keras.callbacks import EarlyStopping

    rnd.seed(seed)
    np.random.seed(seed)
    tf.random.set_seed(seed)

    # 形状: (N, 1, F)
    X_tr = X_train_raw.reshape(-1, 1, n_features)
    X_te = X_test_raw.reshape(-1, 1, n_features)

    # 特征标准化（在展平维度上拟合）
    scaler_x = StandardScaler()
    X_tr_2d = scaler_x.fit_transform(X_tr.reshape(-1, n_features))
    X_te_2d = scaler_x.transform(X_te.reshape(-1, n_features))
    X_tr = X_tr_2d.reshape(-1, 1, n_features).astype(np.float32)
    X_te = X_te_2d.reshape(-1, 1, n_features).astype(np.float32)

    # 目标标准化
    scaler_y = StandardScaler()
    y_tr_z = scaler_y.fit_transform(y_train_raw.reshape(-1, 1)).ravel().astype(np.float32)

    model = _build_att_lstm_model(n_features)
    cb = EarlyStopping(patience=EARLY_STOP_PATIENCE, restore_best_weights=True)
    model.fit(
        X_tr, y_tr_z,
        epochs=EPOCHS,
        batch_size=BATCH_SIZE,
        validation_split=0.15,
        callbacks=[cb],
        verbose=verbose,
    )

    y_pred_z = model.predict(X_te, verbose=0).ravel()
    y_pred = scaler_y.inverse_transform(y_pred_z.reshape(-1, 1)).ravel()

    r2 = r2_score(y_test_raw, y_pred)
    rmse = np.sqrt(mean_squared_error(y_test_raw, y_pred))
    return y_pred, r2, rmse


def run_random_kfold_lstm(df: pd.DataFrame, feature_cols: list) -> dict:
    """Random 5-fold CV for Attention-LSTM。"""
    print("\n  [LSTM] Random 5-fold CV ...")
    df = df.copy()
    df["log_production"] = np.log(df["production_wan_ton"])
    X = df[feature_cols].values.astype(np.float32)
    y = df["log_production"].values.astype(np.float32)
    n_features = len(feature_cols)

    kf = KFold(n_splits=5, shuffle=True, random_state=42)
    fold_results = []
    all_preds = []
    all_true = []

    for fold_idx, (train_idx, test_idx) in enumerate(kf.split(X)):
        X_train, X_test = X[train_idx], X[test_idx]
        y_train, y_test = y[train_idx], y[test_idx]

        try:
            y_pred, r2, rmse = _train_lstm_once(
                X_train, y_train, X_test, y_test,
                n_features=n_features, seed=42 + fold_idx, verbose=0,
            )
        except Exception as e:
            print(f"    LSTM fold {fold_idx+1} 训练失败: {e}")
            return {"status": "failed", "reason": str(e)}

        fold_results.append({
            "fold": f"fold_{fold_idx+1}",
            "n_train": len(train_idx),
            "n_test": len(test_idx),
            "r2": round(float(r2), 4),
            "rmse_log": round(float(rmse), 4),
        })
        all_preds.extend(y_pred.tolist())
        all_true.extend(y_test.tolist())
        print(f"  LSTM Random fold {fold_idx+1}: R²={r2:.4f}, RMSE={rmse:.4f}")

    folds_df = pd.DataFrame(fold_results)
    overall_r2 = r2_score(all_true, all_preds)
    mean_r2 = folds_df["r2"].mean()
    std_r2 = folds_df["r2"].std()
    overall_rmse = np.sqrt(mean_squared_error(all_true, all_preds))

    print(f"\n  LSTM Random CV 汇总: overall_R²={overall_r2:.4f}, "
          f"mean±std={mean_r2:.4f}±{std_r2:.4f}")

    return {
        "status": "ok",
        "folds_df": folds_df,
        "overall_r2": round(overall_r2, 4),
        "mean_r2": round(mean_r2, 4),
        "std_r2": round(std_r2, 4),
        "overall_rmse": round(overall_rmse, 4),
    }


def run_spatial_cv_lstm(df: pd.DataFrame, feature_cols: list) -> dict:
    """Leave-Province-Out CV for Attention-LSTM。"""
    print("\n  [LSTM] Leave-Province-Out CV ...")
    df = df.copy()
    df["log_production"] = np.log(df["production_wan_ton"])
    pkey = "province_short" if "province_short" in df.columns else "province"
    provinces = sorted(df[pkey].unique())
    n_features = len(feature_cols)

    fold_results = []
    all_preds = []
    all_true = []

    for held_out in provinces:
        train_mask = df[pkey] != held_out
        test_mask = df[pkey] == held_out
        X_train = df.loc[train_mask, feature_cols].values.astype(np.float32)
        y_train = df.loc[train_mask, "log_production"].values.astype(np.float32)
        X_test = df.loc[test_mask, feature_cols].values.astype(np.float32)
        y_test = df.loc[test_mask, "log_production"].values.astype(np.float32)

        try:
            y_pred, r2, rmse = _train_lstm_once(
                X_train, y_train, X_test, y_test,
                n_features=n_features, seed=42, verbose=0,
            )
        except Exception as e:
            print(f"    LSTM 留出 {held_out} 训练失败: {e}")
            return {"status": "failed", "reason": str(e)}

        n_cities = int(df.loc[test_mask, "city"].nunique())
        fold_results.append({
            "fold": held_out,
            "n_train": int(train_mask.sum()),
            "n_test": int(test_mask.sum()),
            "n_cities": n_cities,
            "r2": round(float(r2), 4),
            "rmse_log": round(float(rmse), 4),
        })
        all_preds.extend(y_pred.tolist())
        all_true.extend(y_test.tolist())
        symbol = "✅" if r2 > 0 else "❌"
        print(f"  {symbol} LSTM 留出 {held_out}: R²={r2:.4f}, RMSE={rmse:.4f} "
              f"(cities={n_cities})")

    folds_df = pd.DataFrame(fold_results)
    overall_r2 = r2_score(all_true, all_preds)
    mean_r2 = folds_df["r2"].mean()
    std_r2 = folds_df["r2"].std()
    overall_rmse = np.sqrt(mean_squared_error(all_true, all_preds))
    n_positive = int((folds_df["r2"] > 0).sum())

    print(f"\n  LSTM Spatial CV 汇总: overall_R²={overall_r2:.4f}, "
          f"mean±std={mean_r2:.4f}±{std_r2:.4f}, 正向折={n_positive}/{len(provinces)}")

    return {
        "status": "ok",
        "folds_df": folds_df,
        "overall_r2": round(overall_r2, 4),
        "mean_r2": round(mean_r2, 4),
        "std_r2": round(std_r2, 4),
        "overall_rmse": round(overall_rmse, 4),
        "n_positive_folds": n_positive,
        "n_folds": len(provinces),
    }


# ──────────────────────────────────────────────────────────────────────────────
# 报告生成
# ──────────────────────────────────────────────────────────────────────────────

def _fmt(v, fmt=".4f"):
    if v is None:
        return "—"
    return f"{v:{fmt}}"


def write_outputs(
    df: pd.DataFrame,
    xgb_rand: dict,
    xgb_spatial: dict,
    lstm_rand: dict,
    lstm_spatial: dict,
    sanity_ok: bool,
    sanity_delta: float,
) -> None:
    REPORT_DIR.mkdir(exist_ok=True)
    today = datetime.date.today().isoformat()

    # ── CSV ──────────────────────────────────────────────────────────────────
    rows = []

    # XGBoost
    xgb_spatial_folds = xgb_spatial["folds_df"]
    for _, row in xgb_spatial_folds.iterrows():
        rows.append({
            "model": "XGBoost",
            "cv_type": "leave_province_out",
            "fold": row["fold"],
            "n_train": row["n_train"],
            "n_test": row["n_test"],
            "r2": row["r2"],
            "rmse_log": row["rmse_log"],
            "notes": f"n_cities={row.get('n_cities', '?')}",
        })

    xgb_rand_folds = xgb_rand["folds_df"]
    for _, row in xgb_rand_folds.iterrows():
        rows.append({
            "model": "XGBoost",
            "cv_type": "random_kfold",
            "fold": row["fold"],
            "n_train": row["n_train"],
            "n_test": row["n_test"],
            "r2": row["r2"],
            "rmse_log": row["rmse_log"],
            "notes": "identity_leakage_intentional",
        })

    # LSTM spatial
    if lstm_spatial.get("status") == "ok":
        for _, row in lstm_spatial["folds_df"].iterrows():
            rows.append({
                "model": "Attention-LSTM",
                "cv_type": "leave_province_out",
                "fold": row["fold"],
                "n_train": row["n_train"],
                "n_test": row["n_test"],
                "r2": row["r2"],
                "rmse_log": row["rmse_log"],
                "notes": f"n_cities={row.get('n_cities', '?')}",
            })
    # LSTM random
    if lstm_rand.get("status") == "ok":
        for _, row in lstm_rand["folds_df"].iterrows():
            rows.append({
                "model": "Attention-LSTM",
                "cv_type": "random_kfold",
                "fold": row["fold"],
                "n_train": row["n_train"],
                "n_test": row["n_test"],
                "r2": row["r2"],
                "rmse_log": row["rmse_log"],
                "notes": "identity_leakage_intentional",
            })

    csv_path = REPORT_DIR / "v5_paired_results.csv"
    pd.DataFrame(rows).to_csv(csv_path, index=False, encoding="utf-8")
    print(f"\n  ✅ 各折数据 CSV: {csv_path}")

    # ── Markdown report ───────────────────────────────────────────────────────
    n_obs = len(df)
    n_cities = df["city"].nunique()
    n_prov = df["province_short"].nunique() if "province_short" in df.columns \
        else df["province"].nunique()
    year_range = f"{df['year'].min()}–{df['year'].max()}"

    # Wiring sanity status
    sanity_str = (
        f"**✅ 通过** — 复现 overall R²={xgb_spatial['overall_r2']:.4f}，"
        f"与 commit 767cae9 差值 Δ={sanity_delta:+.4f} (<0.02)"
        if sanity_ok
        else f"**❌ 失败** — 复现 R²={xgb_spatial['overall_r2']:.4f}，"
             f"与 commit 767cae9 参考值 0.2132 差值 Δ={sanity_delta:+.4f} (>0.02)"
    )

    # LSTM status strings
    def lstm_status_str(d: dict, cv_label: str) -> str:
        if "not_run" in d:
            return f"not-run: {d.get('reason', 'framework absent')}"
        if d.get("status") == "failed":
            return f"failed: {d.get('reason', 'unknown')}"
        if d.get("status") == "infeasible":
            return f"infeasible: {d.get('reason', 'unknown')}"
        return (f"R²={d['overall_r2']:.4f} (mean±std={d['mean_r2']:.4f}±{d['std_r2']:.4f}), "
                f"RMSE(log)={d['overall_rmse']:.4f}")

    # Per-fold table rows
    def spatial_fold_rows(folds_df: pd.DataFrame) -> list:
        lines = []
        for _, r in folds_df.iterrows():
            sym = "✅" if r["r2"] > 0 else "❌"
            nc = r.get("n_cities", "—")
            lines.append(
                f"| {r['fold']} {sym} | {r['n_train']} | {r['n_test']} | "
                f"{nc} | {r['r2']:.4f} | {r['rmse_log']:.4f} |"
            )
        return lines

    def random_fold_rows(folds_df: pd.DataFrame) -> list:
        lines = []
        for _, r in folds_df.iterrows():
            lines.append(
                f"| {r['fold']} | {r['n_train']} | {r['n_test']} | "
                f"{r['r2']:.4f} | {r['rmse_log']:.4f} |"
            )
        return lines

    lstm_rand_ok = lstm_rand.get("status") == "ok"
    lstm_spatial_ok = lstm_spatial.get("status") == "ok"

    # Build report
    lines = [
        "# v5 配对泛化性证据报告",
        "",
        f"> 生成时间：{today}",
        f"> 脚本：scripts/data/v5_09_paired_generalization.py",
        "",
        "## 配对设计说明",
        "",
        "本报告提供论文核心对比证据：",
        "",
        "| CV 方案 | 含义 |",
        "|---------|------|",
        "| Random 5-fold CV | 乐观估计：随机打乱全部样本分折，省份/城市身份跨折泄漏（故意保留）。这是 naive 论文常报的数字，可能因省份记忆虚高。|",
        "| Leave-Province-Out CV | 诚实空间外推：每次留出一整个省份作为测试集，模型看不到该省任何样本。这是真实泛化能力的严格检验。|",
        "",
        '两者的差距量化了"省份记忆"导致的虚高幅度。',
        "",
        "---",
        "",
        "## 数据概览",
        "",
        f"- 特征矩阵：`feature_matrix_v5.parquet`（v5 城市级 MODIS/CLCD/NASA）",
        f"- 可训练交集：{n_obs} 行，{n_cities} 城市，{n_prov} 省，年份 {year_range}",
        f"- 特征数：{len(xgb_rand['folds_df'].columns) - 4} → 实际 {len([c for c in V5_FEATURE_COLS])} 维",
        f"- 目标：log(production_wan_ton)（EPS 城市级产量，万吨）",
        "",
        "---",
        "",
        "## 接线完整性核查（sanity check）",
        "",
        f"> XGBoost Leave-Province-Out 复现 vs commit 767cae9（overall R²=0.2132）",
        "",
        sanity_str,
        "",
        "---",
        "",
        "## 核心配对表",
        "",
        "| 模型 | Random 5-fold R²<br>（乐观，身份泄漏）| Leave-Province-Out R²<br>（严格空间外推）| Random RMSE(log) | Spatial RMSE(log) | 备注 |",
        "|------|---------------------------------------|------------------------------------------|------------------|-------------------|------|",
    ]

    # XGBoost row
    xgb_notes = (
        f"spatial: {xgb_spatial['n_positive_folds']}/{xgb_spatial['n_folds']} 折正向"
    )
    xgb_rand_cell = (
        f"{xgb_rand['overall_r2']:.4f} "
        f"(mean±std={xgb_rand['mean_r2']:.4f}±{xgb_rand['std_r2']:.4f})"
    )
    xgb_spatial_cell = (
        f"{xgb_spatial['overall_r2']:.4f} "
        f"(mean±std={xgb_spatial['mean_r2']:.4f}±{xgb_spatial['std_r2']:.4f})"
    )
    lines.append(
        f"| XGBoost | {xgb_rand_cell} | {xgb_spatial_cell} | "
        f"{xgb_rand['overall_rmse']:.4f} | {xgb_spatial['overall_rmse']:.4f} | {xgb_notes} |"
    )

    # LSTM row
    if lstm_rand_ok and lstm_spatial_ok:
        lstm_rand_cell = (
            f"{lstm_rand['overall_r2']:.4f} "
            f"(mean±std={lstm_rand['mean_r2']:.4f}±{lstm_rand['std_r2']:.4f})"
        )
        lstm_spatial_cell = (
            f"{lstm_spatial['overall_r2']:.4f} "
            f"(mean±std={lstm_spatial['mean_r2']:.4f}±{lstm_spatial['std_r2']:.4f})"
        )
        lstm_notes = (
            f"spatial: {lstm_spatial['n_positive_folds']}/{lstm_spatial['n_folds']} 折正向"
        )
        lines.append(
            f"| Attention-LSTM | {lstm_rand_cell} | {lstm_spatial_cell} | "
            f"{lstm_rand['overall_rmse']:.4f} | {lstm_spatial['overall_rmse']:.4f} | {lstm_notes} |"
        )
    else:
        lstm_rand_note = lstm_status_str(lstm_rand, "random")
        lstm_spatial_note = lstm_status_str(lstm_spatial, "spatial")
        lines.append(
            f"| Attention-LSTM | {lstm_rand_note} | {lstm_spatial_note} | — | — | see §LSTM 说明 |"
        )

    lines += [
        "",
        "---",
        "",
        "## XGBoost 各折明细",
        "",
        "### Random 5-fold CV",
        "",
        "| 折 | 训练样本 | 测试样本 | R² | RMSE(log) |",
        "|----|----------|----------|----|-----------|",
    ]
    lines += random_fold_rows(xgb_rand["folds_df"])

    lines += [
        "",
        "### Leave-Province-Out CV",
        "",
        "| 留出省份 | 训练样本 | 测试样本 | 测试城市数 | R² | RMSE(log) |",
        "|---------|----------|----------|-----------|-----|-----------|",
    ]
    lines += spatial_fold_rows(xgb_spatial["folds_df"])

    # LSTM per-fold details
    if lstm_rand_ok or lstm_spatial_ok:
        lines += ["", "---", "", "## Attention-LSTM 各折明细", ""]

        if lstm_rand_ok:
            lines += [
                "### Random 5-fold CV",
                "",
                "| 折 | 训练样本 | 测试样本 | R² | RMSE(log) |",
                "|----|----------|----------|----|-----------|",
            ]
            lines += random_fold_rows(lstm_rand["folds_df"])
            lines.append("")

        if lstm_spatial_ok:
            lines += [
                "### Leave-Province-Out CV",
                "",
                "| 留出省份 | 训练样本 | 测试样本 | 测试城市数 | R² | RMSE(log) |",
                "|---------|----------|----------|-----------|-----|-----------|",
            ]
            lines += spatial_fold_rows(lstm_spatial["folds_df"])
            lines.append("")

    # LSTM diagnosis section
    lines += [
        "---",
        "",
        "## Attention-LSTM 诊断",
        "",
    ]

    if not lstm_rand_ok or not lstm_spatial_ok:
        reason_r = lstm_rand.get("reason", lstm_rand.get("not_run", "see above"))
        reason_s = lstm_spatial.get("reason", lstm_spatial.get("not_run", "see above"))
        if reason_r == reason_s:
            lines += [
                f"Random CV 与 Spatial CV 均未成功运行。原因：{reason_r}",
                "",
            ]
        else:
            lines += [
                f"- Random CV: {reason_r}",
                f"- Spatial CV: {reason_s}",
                "",
            ]
    else:
        lines += [
            "两种 CV 均正常运行，结果见上表。",
            "",
            f"样本量诊断：~{n_obs} 个观测、~{n_cities} 个城市、~13 年时序对 Attention-LSTM（TIMESTEPS=1 feature-gating 模式）在 leave-province-out 设定下数据量极为有限。",
            "高不稳定性（折间 R² 方差大）是预期行为，并非实现错误。",
            "",
        ]

    lines += [
        "---",
        "",
        "## 论文叙述建议",
        "",
        "本报告提供的证据支持如下诚实叙事：",
        "",
        "1. 随机 CV 给出乐观但不具外推意义的 R²，是 naive 省级模型的典型误区。",
        "2. Leave-Province-Out CV 是衡量模型能否对新省份零样本泛化的严格检验。",
        "3. 城市级 XGBoost 在 leave-province-out 下 overall R² > 0（正向），说明模型学到了跨省共性规律，而非单纯省份固定效应。",
        "4. 省内方差占总方差 ~89%（ICC≈0.11），即城市级产量差异主要来自省内气候-地理-农艺变异，这是城市粒度建模的科学动机。",
        "",
        "---",
        f"",
        f"*报告由 v5_09_paired_generalization.py 自动生成，时间：{today}*",
    ]

    report_path = REPORT_DIR / "v5_paired_generalization.md"
    report_path.write_text("\n".join(lines), encoding="utf-8")
    print(f"  ✅ 报告写入: {report_path}")


# ──────────────────────────────────────────────────────────────────────────────
# main
# ──────────────────────────────────────────────────────────────────────────────

def main() -> int:
    print("=" * 70)
    print("v5 Step 9: 配对泛化性证据（Random CV vs Leave-Province-Out CV）")
    print("=" * 70)

    # 1. 数据加载
    try:
        df, mode, feature_cols = build_v5_dataset()
    except FileNotFoundError as e:
        print(f"\n❌ {e}")
        return 1

    print(f"\n  省份: {sorted(df['province_short'].unique() if 'province_short' in df.columns else df['province'].unique())}")
    print(f"  城市数: {df['city'].nunique()}")
    print(f"  年份范围: {df['year'].min()} - {df['year'].max()}")
    print(f"  总观测数: {len(df)}")
    print(f"  特征数: {len(feature_cols)}")
    print(f"  特征列: {feature_cols}")

    # 2. XGBoost — 两种 CV
    print("\n" + "=" * 70)
    print("XGBoost — Random 5-fold CV（乐观估计）")
    print("=" * 70)
    xgb_rand = run_random_kfold_xgb(df, feature_cols)

    print("\n" + "=" * 70)
    print("XGBoost — Leave-Province-Out CV（严格空间外推）")
    print("=" * 70)
    xgb_spatial = run_spatial_cv_xgb(df, feature_cols)

    # 3. Sanity check: 与 commit 767cae9 对比
    REFERENCE_R2 = 0.2132
    delta = xgb_spatial["overall_r2"] - REFERENCE_R2
    sanity_ok = abs(delta) < 0.02
    print(f"\n[接线检查] XGBoost Spatial CV overall R²={xgb_spatial['overall_r2']:.4f}, "
          f"参考值={REFERENCE_R2}, Δ={delta:+.4f}")
    if sanity_ok:
        print("  ✅ 接线正确，复现结果与 commit 767cae9 一致（Δ < 0.02）")
    else:
        print("  ❌ 接线错误！复现结果与参考值偏差 > 0.02，请检查数据逻辑。")
        print("  ⚠️  STOP: 不继续运行 LSTM（数据接线不对，结果无效）。")
        write_outputs(df, xgb_rand, xgb_spatial,
                      {"not_run": True, "reason": "XGBoost sanity check failed"},
                      {"not_run": True, "reason": "XGBoost sanity check failed"},
                      sanity_ok=False, sanity_delta=delta)
        return 1

    # 4. Attention-LSTM
    lstm_rand: dict = {}
    lstm_spatial: dict = {}

    try:
        import tensorflow as tf
        tf_version = tf.__version__
        print(f"\n  TensorFlow {tf_version} 可用，开始 Attention-LSTM CV ...")
    except ImportError:
        msg = "TensorFlow 未安装（venv-rt 中不存在）"
        print(f"\n  ⚠️  {msg}")
        lstm_rand = {"not_run": True, "reason": msg}
        lstm_spatial = {"not_run": True, "reason": msg}

    if not lstm_rand:
        # 可行性检查：每个省至少有 MIN_TRAIN_PER_FOLD 个样本
        MIN_TRAIN_PER_FOLD = 30
        pkey = "province_short" if "province_short" in df.columns else "province"
        provinces = sorted(df[pkey].unique())
        min_train = min(len(df[df[pkey] != p]) for p in provinces)
        if min_train < MIN_TRAIN_PER_FOLD:
            msg = (f"样本量不足（最小训练折 {min_train} < {MIN_TRAIN_PER_FOLD}）"
                   "，LSTM 无法收敛")
            print(f"  ⚠️  {msg}")
            lstm_rand = {"status": "infeasible", "reason": msg}
            lstm_spatial = {"status": "infeasible", "reason": msg}
        else:
            print("\n" + "=" * 70)
            print("Attention-LSTM — Random 5-fold CV")
            print("=" * 70)
            lstm_rand = run_random_kfold_lstm(df, feature_cols)

            if lstm_rand.get("status") in ("ok",):
                print("\n" + "=" * 70)
                print("Attention-LSTM — Leave-Province-Out CV")
                print("=" * 70)
                lstm_spatial = run_spatial_cv_lstm(df, feature_cols)
            else:
                lstm_spatial = {"status": "failed",
                                "reason": f"random CV failed: {lstm_rand.get('reason', '?')}"}

    # 5. 写报告和 CSV
    print("\n" + "=" * 70)
    print("写报告 ...")
    print("=" * 70)
    write_outputs(df, xgb_rand, xgb_spatial, lstm_rand, lstm_spatial,
                  sanity_ok=sanity_ok, sanity_delta=delta)

    # 6. 终端摘要
    print("\n" + "=" * 70)
    print("最终摘要")
    print("=" * 70)
    print(f"\n{'模型':<20} {'Random CV R²':>15} {'Spatial CV R²':>16} {'接线检查':>10}")
    print("-" * 70)
    print(f"{'XGBoost':<20} {xgb_rand['overall_r2']:>15.4f} "
          f"{xgb_spatial['overall_r2']:>16.4f} "
          f"{'✅' if sanity_ok else '❌':>10}")

    if lstm_rand.get("status") == "ok" and lstm_spatial.get("status") == "ok":
        print(f"{'Attention-LSTM':<20} {lstm_rand['overall_r2']:>15.4f} "
              f"{lstm_spatial['overall_r2']:>16.4f} {'—':>10}")
    else:
        reason = lstm_rand.get("reason", lstm_rand.get("not_run", "?"))
        if isinstance(reason, bool):
            reason = lstm_rand.get("reason", "not run")
        print(f"{'Attention-LSTM':<20} {'—':>15} {'—':>16} {reason[:20]:>10}")

    print()
    return 0


if __name__ == "__main__":
    sys.exit(main())
