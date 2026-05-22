"""Attention-LSTM 基线（v3 真实单产，11 维含 NDVI）

在 LSTM 基线（路线 E 第 2 项）上增加 **feature-level attention gating**：
  Input (1, 11) → Reshape (11,) → Dense(11) → Softmax → 与 features 逐位相乘
                → Reshape (1, 11) → LSTM(64) → LSTM(32) → Dropout(0.2) → Dense(1)

为什么是 feature-gating 而不是 timestep self-attention：
  TIMESTEPS=1（论文 N=403 = 31 省 × 13 年，每省每年一行）→ 时间轴只有 1 个位置，
  timestep-level attention 无东西可注意。改在 11 个特征维上学软掩码（输入-相关的权重），
  这套权重可以与 XGB SHAP 做"一致性"对照（doc 06 §3.2 任务）。

跑法：/home/xxfql/DC-AIino/.venv/bin/python /home/xxfql/DC-AIino/train_att_lstm_baseline.py

背景：project_v3_real_yield_finding.md（2026-05-17 v3 反转，路线 E 第 4 项 Attention 升级）
"""
from pathlib import Path
import json
import hashlib
import os
import random
from datetime import datetime

import joblib
import numpy as np
import pandas as pd
from sklearn.metrics import r2_score, root_mean_squared_error
from sklearn.model_selection import train_test_split
from sklearn.preprocessing import StandardScaler

os.environ.setdefault("TF_CPP_MIN_LOG_LEVEL", "2")
os.environ.setdefault("TF_ENABLE_ONEDNN_OPTS", "0")

import tensorflow as tf
from tensorflow.keras import Model
from tensorflow.keras.callbacks import EarlyStopping
from tensorflow.keras.layers import (
    LSTM, Dense, Dropout, Input, Multiply, Reshape, Softmax,
)

# ─── 路径 / target ─────────────────────────────────────────────────────────
DATA_PATH = Path("data/interim/paper_panel_v3.parquet")
MODELS_DIR = Path("backend/models")
MODELS_DIR.mkdir(parents=True, exist_ok=True)

TARGET_COL = "yield_kg_per_ha"

# ─── 超参 ──────────────────────────────────────────────────────────────────
TIMESTEPS = 1
LSTM_UNITS_1 = 64
LSTM_UNITS_2 = 32
DROPOUT = 0.2
BATCH_SIZE = 16
EPOCHS = 100
LR = 1e-3
EARLY_STOP_PATIENCE = 10

SEEDS = list(range(10))
R2_TARGET = 0.62

LOWERCASE_TO_TRAINING = {
    "irr": "Irr", "flood": "Flood_R", "sun": "Sun", "temp": "Temp",
    "spei": "SPEI", "prec": "Prec", "mech": "Mech", "fert": "Fert",
    "drou_a": "Drou_A", "flood_a": "Flood_A",
    "ndvi": "NDVI",
}
FEATURE_COLS_LOWER = list(LOWERCASE_TO_TRAINING.keys())
FEATURE_COLS_TRAINING = list(LOWERCASE_TO_TRAINING.values())
N_FEATURES = len(FEATURE_COLS_LOWER)

ATTENTION_LAYER_NAME = "feature_attention"  # 推理时按名取这一层输出


def set_seed(seed: int) -> None:
    random.seed(seed)
    np.random.seed(seed)
    tf.random.set_seed(seed)


def build_windows(df: pd.DataFrame, timesteps: int, target_col: str):
    df = df.sort_values(["province", "year"]).reset_index(drop=True)
    X_list, y_list = [], []
    for _, g in df.groupby("province", sort=False):
        feats = g[FEATURE_COLS_LOWER].values.astype(np.float32)
        targets = g[target_col].values.astype(np.float32)
        if timesteps == 1:
            for i in range(len(g)):
                X_list.append(feats[i : i + 1])
                y_list.append(targets[i])
        else:
            for t in range(timesteps - 1, len(g)):
                X_list.append(feats[t - timesteps + 1 : t + 1])
                y_list.append(targets[t])
    return np.stack(X_list), np.array(y_list, dtype=np.float32)


def build_model(timesteps: int, n_features: int) -> tf.keras.Model:
    """Attention(feature-gating) → LSTM(64) → LSTM(32) → Dropout → Dense(1)。

    Attention 块：Input (1, F) → Reshape (F,) → Dense(F) → Softmax → ⊙ features → Reshape (1, F)
    Softmax 后的 (F,) 权重以 layer name `feature_attention` 暴露给推理服务。
    """
    inputs = Input(shape=(timesteps, n_features), name="inputs")

    flat = Reshape((n_features,), name="flatten_features")(inputs)
    attn_logits = Dense(n_features, name="attn_logits")(flat)
    attn_weights = Softmax(name=ATTENTION_LAYER_NAME)(attn_logits)
    gated = Multiply(name="apply_attention")([flat, attn_weights])
    back = Reshape((timesteps, n_features), name="restore_sequence")(gated)

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


def train_once(X_all, y_all, seed, verbose=0):
    set_seed(seed)

    X_train_raw, X_test_raw, y_train, y_test = train_test_split(
        X_all, y_all, test_size=0.2, random_state=seed
    )

    B_tr, T, F = X_train_raw.shape
    B_te = X_test_raw.shape[0]
    x_scaler = StandardScaler()
    X_train = x_scaler.fit_transform(X_train_raw.reshape(-1, F)).reshape(B_tr, T, F)
    X_test = x_scaler.transform(X_test_raw.reshape(-1, F)).reshape(B_te, T, F)

    y_scaler = StandardScaler()
    y_train_z = y_scaler.fit_transform(y_train.reshape(-1, 1)).ravel()

    model = build_model(T, F)
    history = model.fit(
        X_train, y_train_z,
        epochs=EPOCHS,
        batch_size=BATCH_SIZE,
        validation_split=0.2,
        callbacks=[EarlyStopping(patience=EARLY_STOP_PATIENCE, restore_best_weights=True)],
        verbose=verbose,
    )

    y_train_pred_z = model.predict(X_train, verbose=0).ravel()
    y_test_pred_z = model.predict(X_test, verbose=0).ravel()
    y_train_pred = y_scaler.inverse_transform(y_train_pred_z.reshape(-1, 1)).ravel()
    y_test_pred = y_scaler.inverse_transform(y_test_pred_z.reshape(-1, 1)).ravel()

    attn_model = Model(model.input, model.get_layer(ATTENTION_LAYER_NAME).output)
    attn_train = attn_model.predict(X_train, verbose=0)
    attn_mean = attn_train.mean(axis=0).tolist()

    metrics = dict(
        tr_r2=float(r2_score(y_train, y_train_pred)),
        tr_rmse_kg_per_ha=float(root_mean_squared_error(y_train, y_train_pred)),
        te_r2=float(r2_score(y_test, y_test_pred)),
        te_rmse_kg_per_ha=float(root_mean_squared_error(y_test, y_test_pred)),
        epochs_run=int(len(history.history["loss"])),
        attn_train_mean=attn_mean,
    )
    return model, x_scaler, y_scaler, history, metrics


print("=" * 72)
print(f"1. 加载真实数据 — target = {TARGET_COL}")
print("=" * 72)
df = pd.read_parquet(DATA_PATH)
data_hash = hashlib.md5(DATA_PATH.read_bytes()).hexdigest()[:12]
print(f"数据：{DATA_PATH}（MD5 前 12 位：{data_hash}）")
print(f"规模：{df.shape[0]} 行 × {N_FEATURES} 维 X + 1 维 y")

print()
print("=" * 72)
print(f"2. 构造窗口（TIMESTEPS={TIMESTEPS}）")
print("=" * 72)
X_all, y_all = build_windows(df, TIMESTEPS, TARGET_COL)
print(f"样本数：{X_all.shape[0]}    输入形状：{X_all.shape}")

print()
print("=" * 72)
print("3. Attention-LSTM 10 种子训练")
print("=" * 72)
print(f"{'seed':>6s}{'tr_R²':>10s}{'te_R²':>10s}{'tr_RMSE':>14s}{'te_RMSE':>14s}{'epochs':>9s}")
print("-" * 63)

trained = []
for seed in SEEDS:
    model, x_scaler, y_scaler, history, m = train_once(X_all, y_all, seed=seed, verbose=0)
    trained.append((seed, model, x_scaler, y_scaler, history, m))
    print(
        f"{seed:>6d}{m['tr_r2']:>10.4f}{m['te_r2']:>10.4f}"
        f"{m['tr_rmse_kg_per_ha']:>14.1f}{m['te_rmse_kg_per_ha']:>14.1f}{m['epochs_run']:>9d}"
    )

te_r2_arr = np.array([m["te_r2"] for _, _, _, _, _, m in trained])
tr_r2_arr = np.array([m["tr_r2"] for _, _, _, _, _, m in trained])
te_rmse_arr = np.array([m["te_rmse_kg_per_ha"] for _, _, _, _, _, m in trained])
tr_rmse_arr = np.array([m["tr_rmse_kg_per_ha"] for _, _, _, _, _, m in trained])

print("-" * 63)
print(
    f"{'mean':>6s}{tr_r2_arr.mean():>10.4f}{te_r2_arr.mean():>10.4f}"
    f"{tr_rmse_arr.mean():>14.1f}{te_rmse_arr.mean():>14.1f}"
)
print(
    f"{'std':>6s}{tr_r2_arr.std():>10.4f}{te_r2_arr.std():>10.4f}"
    f"{tr_rmse_arr.std():>14.1f}{te_rmse_arr.std():>14.1f}"
)

attn_means = np.array([m["attn_train_mean"] for _, _, _, _, _, m in trained])
attn_grand_mean = attn_means.mean(axis=0)
attn_grand_std = attn_means.std(axis=0)

print()
print("=" * 72)
print("4. Attention 权重（10 种子均值，按权重降序）")
print("=" * 72)
order = np.argsort(-attn_grand_mean)
for i, idx in enumerate(order, 1):
    print(
        f"  #{i:>2d} {FEATURE_COLS_TRAINING[idx]:>8s}: "
        f"{attn_grand_mean[idx]:.4f} ± {attn_grand_std[idx]:.4f}"
    )

print()
print("=" * 72)
print("5. 10 种子汇总 vs 申报书硬指标")
print("=" * 72)
mean_r2 = float(te_r2_arr.mean())
mean_rmse = float(te_rmse_arr.mean())
passed = mean_r2 >= R2_TARGET
print(
    f"  test R² mean={mean_r2:.4f} ± {te_r2_arr.std():.4f}  "
    f"[min={te_r2_arr.min():.4f}, max={te_r2_arr.max():.4f}]"
)
print(
    f"  申报书 R² ≥ {R2_TARGET}："
    f"{'✅ 通过' if passed else '❌ 未达'} (mean test R² = {mean_r2:.4f})"
)

median_r2 = float(np.median(te_r2_arr))
representative_idx = int(np.argmin(np.abs(te_r2_arr - median_r2)))
representative_seed = int(trained[representative_idx][0])
_, repr_model, repr_x_scaler, repr_y_scaler, repr_history, repr_m = trained[representative_idx]

print()
print("=" * 72)
print(f"6. 保存代表模型 (seed={representative_seed}) 到 {MODELS_DIR}/")
print("=" * 72)

repr_model.save(MODELS_DIR / "att_lstm_model.h5")
joblib.dump(repr_x_scaler, MODELS_DIR / "att_lstm_x_scaler.pkl")
joblib.dump(repr_y_scaler, MODELS_DIR / "att_lstm_y_scaler.pkl")
(MODELS_DIR / "att_lstm_feature_columns.json").write_text(
    json.dumps(FEATURE_COLS_TRAINING, ensure_ascii=False, indent=2)
)
(MODELS_DIR / "att_lstm_history.json").write_text(
    json.dumps(
        {k: [float(v) for v in vs] for k, vs in repr_history.history.items()},
        ensure_ascii=False,
        indent=2,
    )
)

seeds_dump = dict(
    target=TARGET_COL,
    data_path=str(DATA_PATH),
    data_md5_12=data_hash,
    n_rows=int(len(df)),
    n_features=N_FEATURES,
    feature_cols_lower=FEATURE_COLS_LOWER,
    feature_cols_training=FEATURE_COLS_TRAINING,
    timesteps=TIMESTEPS,
    seeds=SEEDS,
    architecture="Attention(feature-gating) → LSTM(64) → LSTM(32) → Dropout(0.2) → Dense(1)",
    attention_layer=ATTENTION_LAYER_NAME,
    hyper=dict(
        timesteps=TIMESTEPS,
        lstm_units=[LSTM_UNITS_1, LSTM_UNITS_2],
        dropout=DROPOUT,
        batch_size=BATCH_SIZE,
        epochs=EPOCHS,
        lr=LR,
        early_stop_patience=EARLY_STOP_PATIENCE,
    ),
    per_seed=[
        {
            "seed": int(s),
            **{k: v for k, v in m.items() if k != "attn_train_mean"},
            "attn_train_mean": m["attn_train_mean"],
        }
        for s, _, _, _, _, m in trained
    ],
    summary=dict(
        test_r2_mean=float(te_r2_arr.mean()),
        test_r2_std=float(te_r2_arr.std()),
        test_r2_min=float(te_r2_arr.min()),
        test_r2_max=float(te_r2_arr.max()),
        test_rmse_kg_per_ha_mean=float(te_rmse_arr.mean()),
        test_rmse_kg_per_ha_std=float(te_rmse_arr.std()),
        train_r2_mean=float(tr_r2_arr.mean()),
        train_r2_std=float(tr_r2_arr.std()),
        attn_grand_mean={f: float(v) for f, v in zip(FEATURE_COLS_TRAINING, attn_grand_mean)},
        attn_grand_std={f: float(v) for f, v in zip(FEATURE_COLS_TRAINING, attn_grand_std)},
        attn_top3=[FEATURE_COLS_TRAINING[i] for i in order[:3].tolist()],
    ),
    representative_seed=representative_seed,
    declared_r2_target=R2_TARGET,
    passed=bool(passed),
)
(MODELS_DIR / "att_lstm_seeds_results.json").write_text(
    json.dumps(seeds_dump, ensure_ascii=False, indent=2)
)

per_seed_lines = "\n".join(
    [
        f"- seed={s}: te_R²={m['te_r2']:.4f}  te_RMSE={m['te_rmse_kg_per_ha']:.1f} kg/ha  epochs={m['epochs_run']}"
        for s, _, _, _, _, m in trained
    ]
)
attn_lines = "\n".join(
    [
        f"  {i+1}. {FEATURE_COLS_TRAINING[idx]}: {attn_grand_mean[idx]:.4f} ± {attn_grand_std[idx]:.4f}"
        for i, idx in enumerate(order)
    ]
)
xgb_top3_str = "ndvi > temp > prec"
attn_top3_str = " > ".join([FEATURE_COLS_TRAINING[i] for i in order[:3].tolist()])

model_card = f"""# Model Card — Attention-LSTM 基线（v3 真实单产，{N_FEATURES} 维，TIMESTEPS={TIMESTEPS}）

## 训练信息
- 训练日期：{datetime.now().strftime("%Y-%m-%d %H:%M:%S")}
- 训练人：熊鑫
- 数据源：{DATA_PATH}（MD5 前 12 位 `{data_hash}`，由石灵子 PR #7 重算）
- 数据规模：N = {len(df)} 行 → {X_all.shape[0]} 个 ({TIMESTEPS}, {N_FEATURES}) 窗口
- Target：`{TARGET_COL}`（真实单产 kg/ha）
- 协议：10 种子 `{SEEDS}`，8:2 split，超参固定，TIMESTEPS={TIMESTEPS}

## 架构（feature-level attention gating）
Input ({TIMESTEPS}, {N_FEATURES}) → Reshape ({N_FEATURES},)
  → Dense({N_FEATURES}) → Softmax(name=`{ATTENTION_LAYER_NAME}`) → ⊙ features
  → Reshape ({TIMESTEPS}, {N_FEATURES})
→ LSTM({LSTM_UNITS_1}, return_sequences=True) → LSTM({LSTM_UNITS_2}) → Dropout({DROPOUT}) → Dense(1)

为什么 feature-gating 而不是 timestep self-attention：
TIMESTEPS=1（论文设置），时间轴只有 1 个位置，timestep-level attention 无东西可注意。
改在 11 个特征维上学一组输入-相关的软掩码，权重和为 1，可解释、可与 XGB SHAP 对照。

## 超参
```json
{json.dumps({
    "timesteps": TIMESTEPS,
    "lstm_units": [LSTM_UNITS_1, LSTM_UNITS_2],
    "dropout": DROPOUT,
    "batch_size": BATCH_SIZE,
    "epochs": EPOCHS,
    "lr": LR,
    "early_stop_patience": EARLY_STOP_PATIENCE,
}, indent=2)}
```

## 指标（10 种子）

| 指标 | 训练 mean | 训练 std | 测试 mean | 测试 std | 申报书硬指标 | 状态 |
|---|---|---|---|---|---|---|
| R² | {tr_r2_arr.mean():.4f} | {tr_r2_arr.std():.4f} | {te_r2_arr.mean():.4f} | {te_r2_arr.std():.4f} | ≥ 0.62 | {'✅' if passed else '❌'} |
| RMSE (kg/ha) | {tr_rmse_arr.mean():.1f} | {tr_rmse_arr.std():.1f} | {te_rmse_arr.mean():.1f} | {te_rmse_arr.std():.1f} | — | — |

## 各种子明细
{per_seed_lines}

## 10 种子 Attention 权重均值（11 维，按降序）
{attn_lines}

## 与 XGB SHAP 对照（doc 06 §3.2 一致性任务）
- XGB SHAP top-3：`{xgb_top3_str}`
- Attention top-3：`{attn_top3_str}`

## 代表模型
- 保存的 `att_lstm_model.h5` / `att_lstm_x_scaler.pkl` / `att_lstm_y_scaler.pkl` 来自 **seed = {representative_seed}**
  （test R² {repr_m['te_r2']:.4f}，最贴近 10 种子中位数 {median_r2:.4f}）

## 与申报书对照
- 申报书 §3.1 硬指标 R² ≥ 0.62 → **mean test R² = {te_r2_arr.mean():.4f}** {'✅' if passed else '❌'}

## 后端集成
`backend/services/inference.py` 的 `predict_att_lstm_yield()` 加载
`att_lstm_model.h5` / `att_lstm_x_scaler.pkl` / `att_lstm_y_scaler.pkl`，返回
`(yield_kg_per_ha, attention_weights_dict)`，后者 11 维 sum=1。
"""
(MODELS_DIR / "att_lstm_model_card.md").write_text(model_card)

for f in [
    "att_lstm_model.h5",
    "att_lstm_x_scaler.pkl",
    "att_lstm_y_scaler.pkl",
    "att_lstm_feature_columns.json",
    "att_lstm_history.json",
    "att_lstm_seeds_results.json",
    "att_lstm_model_card.md",
]:
    p = MODELS_DIR / f
    print(f"  ✓ {f}  ({p.stat().st_size:,} bytes)")

print()
print("=" * 72)
print(
    f"Attention-LSTM 基线完成。10 种子 test R² "
    f"mean={mean_r2:.4f} ± {te_r2_arr.std():.4f}"
)
print("=" * 72)
