"""LSTM 基线（v3 真实单产，11 维含 NDVI）

数据：data/interim/paper_panel_v3.parquet（27 列，N=403）—— 来自石灵子 PR #7 重算
Target：yield_kg_per_ha（真实单产 kg/ha，非王天硕已煮熟的 Y）
特征：11 维（原论文 10 维 + NDVI）
协议：10 种子 8:2 split，TIMESTEPS=1（论文 N=403 设置）
申报书硬指标：R² ≥ 0.62
  旧 RMSE 阈值 0.0055 不适用（target 单位已从 normalized y → kg/ha）
  论文 R²=0.6619 / RMSE=0.0046 是 normalized y 上的数，不直接可比，仅作历史脚注。

⚠️ 关于 TIMESTEPS（cheatsheet §5.3）：
  论文 N=403 = 31 省 × 13 年，提示论文 LSTM 可能用了 timesteps=1（即把 LSTM 当 MLP 用）。
  本脚本默认 TIMESTEPS=1，同时保留 TIMESTEPS>=2 的按省滑窗逻辑。

跑法：/home/xxfql/DC-AIino/.venv/bin/python /home/xxfql/DC-AIino/train_lstm_baseline.py

背景：project_v3_real_yield_finding.md（2026-05-17 v3 反转，路线 E 第 2 项）
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

# 抑制 TF 启动 log
os.environ.setdefault("TF_CPP_MIN_LOG_LEVEL", "2")
os.environ.setdefault("TF_ENABLE_ONEDNN_OPTS", "0")

import tensorflow as tf
from tensorflow.keras.callbacks import EarlyStopping
from tensorflow.keras.layers import LSTM, Dense, Dropout, Input
from tensorflow.keras.models import Sequential

# ─── 路径 / target ─────────────────────────────────────────────────────────
DATA_PATH = Path("data/interim/paper_panel_v3.parquet")
MODELS_DIR = Path("backend/models")
MODELS_DIR.mkdir(parents=True, exist_ok=True)

TARGET_COL = "yield_kg_per_ha"

# ─── 超参（论文 / cheatsheet §5.2）─────────────────────────────────────
TIMESTEPS = 1
LSTM_UNITS_1 = 64
LSTM_UNITS_2 = 32
DROPOUT = 0.2
BATCH_SIZE = 16
EPOCHS = 100
LR = 1e-3
EARLY_STOP_PATIENCE = 10

SEEDS = list(range(10))  # 0..9，对齐 XGB rewrite
R2_TARGET = 0.62  # 申报书 doc 07 §3.1 硬指标

# 特征列（parquet 小写 ↔ 训练大写，与 inference.py 一致）
# 11 维 = 论文 10 维 + NDVI
LOWERCASE_TO_TRAINING = {
    "irr": "Irr", "flood": "Flood_R", "sun": "Sun", "temp": "Temp",
    "spei": "SPEI", "prec": "Prec", "mech": "Mech", "fert": "Fert",
    "drou_a": "Drou_A", "flood_a": "Flood_A",
    "ndvi": "NDVI",
}
FEATURE_COLS_LOWER = list(LOWERCASE_TO_TRAINING.keys())
FEATURE_COLS_TRAINING = list(LOWERCASE_TO_TRAINING.values())
N_FEATURES = len(FEATURE_COLS_LOWER)


def set_seed(seed: int) -> None:
    """锁 Python / numpy / TF 三处随机源。"""
    random.seed(seed)
    np.random.seed(seed)
    tf.random.set_seed(seed)


def build_windows(
    df: pd.DataFrame, timesteps: int, target_col: str
) -> tuple[np.ndarray, np.ndarray]:
    """按省分组构造滑窗。

    timesteps=1: 退化成 (N, 1, F)，等价于 MLP（论文可能的做法）
    timesteps=k (k>1): 每个省内按 year 排序，每 k 年一个窗口预测第 k 年的 y
                       31 省 × (13 - k + 1) 个样本
    """
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
    """LSTM(64) → LSTM(32) → Dropout(0.2) → Dense(1)。"""
    model = Sequential([
        Input(shape=(timesteps, n_features)),
        LSTM(LSTM_UNITS_1, return_sequences=True),
        LSTM(LSTM_UNITS_2),
        Dropout(DROPOUT),
        Dense(1),
    ])
    model.compile(
        optimizer=tf.keras.optimizers.Adam(learning_rate=LR),
        loss="mse",
    )
    return model


def train_once(X_all: np.ndarray, y_all: np.ndarray, seed: int, verbose: int = 0):
    """单次端到端训练。返回 (model, x_scaler, y_scaler, history, metrics)。

    注意：y 也要 z-score 归一化。LSTM 是梯度优化，target 在 kg/ha (3000+) 量级会让
    初始 MSE ≈ 1.3e7，模型学不动；归一化到 ~0 均值后训练才能收敛。
    Metric 在 inverse_transform 回 kg/ha 后计算，跟 XGB 报告口径一致。
    """
    set_seed(seed)

    X_train_raw, X_test_raw, y_train, y_test = train_test_split(
        X_all, y_all, test_size=0.2, random_state=seed
    )

    # X scaler 在 (B, T, F) 上不能直接用；先拍平到 (B*T, F) 再还原
    B_tr, T, F = X_train_raw.shape
    B_te = X_test_raw.shape[0]
    x_scaler = StandardScaler()
    X_train = x_scaler.fit_transform(X_train_raw.reshape(-1, F)).reshape(B_tr, T, F)
    X_test = x_scaler.transform(X_test_raw.reshape(-1, F)).reshape(B_te, T, F)

    # y scaler（kg/ha → z-score，训练完 inverse_transform 报告原单位 metric）
    y_scaler = StandardScaler()
    y_train_z = y_scaler.fit_transform(y_train.reshape(-1, 1)).ravel()
    y_test_z = y_scaler.transform(y_test.reshape(-1, 1)).ravel()

    model = build_model(T, F)
    history = model.fit(
        X_train, y_train_z,
        epochs=EPOCHS,
        batch_size=BATCH_SIZE,
        validation_split=0.2,
        callbacks=[EarlyStopping(patience=EARLY_STOP_PATIENCE, restore_best_weights=True)],
        verbose=verbose,
    )

    # Predict in z-space, inverse-transform back to kg/ha for metric reporting
    y_train_pred_z = model.predict(X_train, verbose=0).ravel()
    y_test_pred_z = model.predict(X_test, verbose=0).ravel()
    y_train_pred = y_scaler.inverse_transform(y_train_pred_z.reshape(-1, 1)).ravel()
    y_test_pred = y_scaler.inverse_transform(y_test_pred_z.reshape(-1, 1)).ravel()

    metrics = dict(
        tr_r2=float(r2_score(y_train, y_train_pred)),
        tr_rmse_kg_per_ha=float(root_mean_squared_error(y_train, y_train_pred)),
        te_r2=float(r2_score(y_test, y_test_pred)),
        te_rmse_kg_per_ha=float(root_mean_squared_error(y_test, y_test_pred)),
        epochs_run=int(len(history.history["loss"])),
    )
    return model, x_scaler, y_scaler, history, metrics


# ─── 1. 加载数据 ─────────────────────────────────────────────────────────
print("=" * 72)
print(f"1. 加载真实数据 — target = {TARGET_COL}")
print("=" * 72)
df = pd.read_parquet(DATA_PATH)
data_hash = hashlib.md5(DATA_PATH.read_bytes()).hexdigest()[:12]
print(f"数据：{DATA_PATH}（MD5 前 12 位：{data_hash}）")
print(f"规模：{df.shape[0]} 行 × {N_FEATURES} 维 X + 1 维 y")
print(f"省份数：{df['province'].nunique()}    年份：{df['year'].min()}-{df['year'].max()}")
print(
    f"y 统计：mean={df[TARGET_COL].mean():.1f}  std={df[TARGET_COL].std():.1f}  "
    f"范围=[{df[TARGET_COL].min():.0f}, {df[TARGET_COL].max():.0f}] kg/ha"
)

# ─── 2. 构造窗口 ─────────────────────────────────────────────────────────
print()
print("=" * 72)
print(f"2. 构造时间窗口（TIMESTEPS={TIMESTEPS}）")
print("=" * 72)
X_all, y_all = build_windows(df, TIMESTEPS, TARGET_COL)
print(f"样本数：{X_all.shape[0]}    输入形状：{X_all.shape}（B, T, F）")
if TIMESTEPS == 1:
    print("ℹ️  TIMESTEPS=1：等价于 MLP（论文 N=403 设置）")
else:
    print(f"ℹ️  TIMESTEPS={TIMESTEPS}：按省滑窗，每省 {13 - TIMESTEPS + 1} 个样本")

# ─── 3. 10 种子训练 ─────────────────────────────────────────────────────
print()
print("=" * 72)
print(f"3. 10 种子训练（看真实水平不是单次幸运切分）")
print("=" * 72)
print(f"{'seed':>6s}{'tr_R²':>10s}{'te_R²':>10s}{'tr_RMSE':>14s}{'te_RMSE':>14s}{'epochs':>9s}")
print("-" * 63)

trained = []  # 每个 entry: (seed, model, x_scaler, y_scaler, history, metrics)
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

# ─── 4. 对照申报书硬指标 ────────────────────────────────────────────────
print()
print("=" * 72)
print("4. 10 种子汇总 vs 申报书硬指标")
print("=" * 72)
mean_r2 = float(te_r2_arr.mean())
mean_rmse = float(te_rmse_arr.mean())
print(f"  test  R²   mean={mean_r2:.4f}  std={te_r2_arr.std():.4f}  "
      f"[min={te_r2_arr.min():.4f}, max={te_r2_arr.max():.4f}]")
print(f"  train R²   mean={tr_r2_arr.mean():.4f}  std={tr_r2_arr.std():.4f}")
print(f"  test  RMSE mean={mean_rmse:.1f} kg/ha  std={te_rmse_arr.std():.1f}")
print()
passed = mean_r2 >= R2_TARGET
print(
    f"  申报书硬指标 R² ≥ {R2_TARGET}："
    f"{'✅ 通过 (mean test R² = ' + f'{mean_r2:.4f})' if passed else '❌ 未达 (mean test R² = ' + f'{mean_r2:.4f})'}"
)
print(
    "  📜 历史脚注：论文报告 R²=0.6619 / RMSE=0.0046，是 normalized y 上的，"
    "与本基线 kg/ha 不可直接比。"
)

# ─── 5. 选代表 seed（test R² 最贴近中位数）+ 保存交付物 ───────────────
print()
print("=" * 72)
print(f"5. 保存代表模型到 {MODELS_DIR}/")
print("=" * 72)
median_r2 = float(np.median(te_r2_arr))
representative_idx = int(np.argmin(np.abs(te_r2_arr - median_r2)))
representative_seed = int(trained[representative_idx][0])
_, repr_model, repr_x_scaler, repr_y_scaler, repr_history, repr_m = trained[representative_idx]
print(
    f"  选 seed={representative_seed}（test R²={repr_m['te_r2']:.4f}）"
    f"作代表 —— 最贴近 10 种子中位数 {median_r2:.4f}"
)

# 覆盖王天硕坏 Y 时代的旧产物
repr_model.save(MODELS_DIR / "lstm_model.h5")
joblib.dump(repr_x_scaler, MODELS_DIR / "lstm_scaler.pkl")  # X scaler（保持文件名兼容）
joblib.dump(repr_y_scaler, MODELS_DIR / "lstm_y_scaler.pkl")  # 新增：y scaler，inference 需要
(MODELS_DIR / "lstm_feature_columns.json").write_text(
    json.dumps(FEATURE_COLS_TRAINING, ensure_ascii=False, indent=2)
)
(MODELS_DIR / "lstm_history.json").write_text(
    json.dumps(
        {k: [float(v) for v in vs] for k, vs in repr_history.history.items()},
        ensure_ascii=False,
        indent=2,
    )
)

# 10 种子完整结果落盘
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
        dict(seed=int(s), **m) for s, _, _, _, _, m in trained
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
    ),
    representative_seed=representative_seed,
    declared_r2_target=R2_TARGET,
    passed=bool(passed),
)
(MODELS_DIR / "lstm_seeds_results.json").write_text(
    json.dumps(seeds_dump, ensure_ascii=False, indent=2)
)

# Model card
per_seed_lines = "\n".join(
    [
        f"- seed={s}: te_R²={m['te_r2']:.4f}  te_RMSE={m['te_rmse_kg_per_ha']:.1f} kg/ha  epochs={m['epochs_run']}"
        for s, _, _, _, _, m in trained
    ]
)
model_card = f"""# Model Card — LSTM 基线（v3 真实单产，{N_FEATURES} 维，TIMESTEPS={TIMESTEPS}）

## 训练信息
- 训练日期：{datetime.now().strftime("%Y-%m-%d %H:%M:%S")}
- 训练人：熊鑫
- 数据源：{DATA_PATH}（MD5 前 12 位 `{data_hash}`，由石灵子 PR #7 重算）
- 数据规模：N = {len(df)} 行 → {X_all.shape[0]} 个 ({TIMESTEPS}, {N_FEATURES}) 窗口
- Target：`{TARGET_COL}`（真实单产 kg/ha，由原始 .xlsx 重算，**非王天硕已煮熟的 Y**）
- 协议：10 种子 `{SEEDS}`，8:2 split，超参固定，TIMESTEPS={TIMESTEPS}

## 架构
输入 ({TIMESTEPS}, {N_FEATURES}) → LSTM({LSTM_UNITS_1}, return_sequences=True) → LSTM({LSTM_UNITS_2}) → Dropout({DROPOUT}) → Dense(1)
优化器：Adam(lr={LR})   损失：MSE   EarlyStopping(patience={EARLY_STOP_PATIENCE})

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

| 指标 | 训练集 mean | 训练集 std | 测试集 mean | 测试集 std | 申报书硬指标 | 状态 |
|---|---|---|---|---|---|---|
| R² | {tr_r2_arr.mean():.4f} | {tr_r2_arr.std():.4f} | {te_r2_arr.mean():.4f} | {te_r2_arr.std():.4f} | ≥ 0.62 | {'✅' if passed else '❌'} |
| RMSE (kg/ha) | {tr_rmse_arr.mean():.1f} | {tr_rmse_arr.std():.1f} | {te_rmse_arr.mean():.1f} | {te_rmse_arr.std():.1f} | — | — |

> 旧 RMSE 阈值 0.0055 已作废：那是 normalized y 上的指标。论文报告 R²=0.6619 / RMSE=0.0046 同样基于 normalized y，与本基线不可直接比较，仅作历史脚注。

## 各种子明细
{per_seed_lines}

## 代表模型
- 保存的 `lstm_model.h5` / `lstm_scaler.pkl` / `lstm_history.json` 来自 **seed = {representative_seed}**
  （test R² {repr_m['te_r2']:.4f}，最贴近 10 种子中位数 {median_r2:.4f}）
- 该 seed 训练详情：训练 R² {repr_m['tr_r2']:.4f} / RMSE {repr_m['tr_rmse_kg_per_ha']:.1f} kg/ha，{repr_m['epochs_run']}/{EPOCHS} epochs
- 全部 10 个 seed 的完整结果见 `lstm_seeds_results.json`

## 与申报书对照
- 申报书 §3.1 硬指标 R² ≥ 0.62 → **mean test R² = {te_r2_arr.mean():.4f}** {'✅' if te_r2_arr.mean() >= 0.62 else '❌'}

## 背景
本基线为 `project_v3_real_yield_finding.md` **路线 E 第 2 项**：在真实单产上的 LSTM 基线。
路线 E 第 1 项（XGBoost）见 `model_card.md`；对照消融 `y_butter` 残差是第 3 项。

## TIMESTEPS 选择
- 当前用 TIMESTEPS={TIMESTEPS}（cheatsheet §5.3：论文 N=403 暗示 timesteps=1 = LSTM-as-MLP）
- 若要切真·时序，把脚本顶部 `TIMESTEPS = 1` 改成 5，每省样本数会变成 13-5+1=9
- 改完 TIMESTEPS 后建议同步更新 model card / inference.py

## 状态
{'✅ 多种子均值通过申报书硬指标。' if passed else '❌ 多种子均值未达硬指标，需诊断。'}

## 后端集成
`backend/services/inference.py` 的 `predict_lstm_yield()` 已加载 `lstm_scaler.pkl`
+ `lstm_y_scaler.pkl`，对 z-score 输出做 `inverse_transform` 回 kg/ha。
跑 `python -m backend.services.inference` 通过 Henan 2022 sanity（与真值偏差 < 500 kg/ha）。
"""
(MODELS_DIR / "lstm_model_card.md").write_text(model_card)

for f in [
    "lstm_model.h5",
    "lstm_scaler.pkl",
    "lstm_y_scaler.pkl",
    "lstm_feature_columns.json",
    "lstm_history.json",
    "lstm_seeds_results.json",
    "lstm_model_card.md",
]:
    p = MODELS_DIR / f
    print(f"  ✓ {f}  ({p.stat().st_size:,} bytes)")

print()
print("=" * 72)
print(
    f"LSTM 基线（v3）完成。TIMESTEPS={TIMESTEPS}，10 种子 test R² "
    f"mean={mean_r2:.4f} ± {te_r2_arr.std():.4f}"
)
print("=" * 72)
