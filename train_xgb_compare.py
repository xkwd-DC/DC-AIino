"""三种配置对比实验：找到正确的 panel 训练方式

A. 基线：随机 8:2 切分（已知严重过拟合）
B. 按时间切分：2011-2020 训练，2021-2023 测试
C. B + L2 正则（reg_lambda=10）

期望：B/C 测试集 R² 向论文 0.6293 靠近。
"""
from pathlib import Path

import numpy as np
import pandas as pd
import xgboost as xgb
from sklearn.metrics import r2_score, root_mean_squared_error
from sklearn.model_selection import train_test_split
from sklearn.preprocessing import StandardScaler

DATA_PATH = Path("data/interim/paper_panel_raw.parquet")
FEATURE_COLS = ["irr", "flood", "sun", "temp", "spei", "prec",
                "mech", "fert", "drou_a", "flood_a"]

df = pd.read_parquet(DATA_PATH)
X_all = df[FEATURE_COLS].values
y_all = df["y"].values


def run_one(name, X_tr, X_te, y_tr, y_te, hyper):
    """跑一种配置，返回训练集和测试集指标。"""
    scaler = StandardScaler()
    X_tr_s = scaler.fit_transform(X_tr)
    X_te_s = scaler.transform(X_te)
    model = xgb.XGBRegressor(**hyper)
    model.fit(X_tr_s, y_tr)
    return {
        "name":     name,
        "n_train":  len(X_tr),
        "n_test":   len(X_te),
        "train_r2": r2_score(y_tr, model.predict(X_tr_s)),
        "test_r2":  r2_score(y_te, model.predict(X_te_s)),
        "test_rmse": root_mean_squared_error(y_te, model.predict(X_te_s)),
        "gap":      r2_score(y_tr, model.predict(X_tr_s)) - r2_score(y_te, model.predict(X_te_s)),
    }


BASE = dict(
    learning_rate=0.1, max_depth=6, n_estimators=150,
    objective="reg:squarederror", random_state=42,
)

# ─── A. 随机切分（论文基线） ────────────────────────────────────────────
Xa_tr, Xa_te, ya_tr, ya_te = train_test_split(X_all, y_all, test_size=0.2, random_state=42)
ra = run_one("A. 随机 8:2", Xa_tr, Xa_te, ya_tr, ya_te, BASE)

# ─── B. 按时间切分 ──────────────────────────────────────────────────────
tr_mask = df["year"] <= 2020
te_mask = df["year"] >= 2021
rb = run_one(
    "B. 按时间切分（2011-2020 / 2021-2023）",
    X_all[tr_mask], X_all[te_mask], y_all[tr_mask], y_all[te_mask], BASE,
)

# ─── C. B + L2 正则 ─────────────────────────────────────────────────────
rc = run_one(
    "C. B + reg_lambda=10（L2 正则）",
    X_all[tr_mask], X_all[te_mask], y_all[tr_mask], y_all[te_mask],
    {**BASE, "reg_lambda": 10},
)

# ─── 打印对比表 ─────────────────────────────────────────────────────────
print()
print("=" * 92)
print("XGBoost 三种切分/正则方式对比")
print("=" * 92)
header = f"{'配置':<42s}{'N_tr':>6s}{'N_te':>6s}{'训练 R²':>10s}{'测试 R²':>10s}{'gap':>8s}{'测试 RMSE':>12s}"
print(header)
print("-" * 92)
for r in [ra, rb, rc]:
    print(f"{r['name']:<42s}{r['n_train']:>6d}{r['n_test']:>6d}"
          f"{r['train_r2']:>10.4f}{r['test_r2']:>10.4f}{r['gap']:>8.4f}{r['test_rmse']:>12.4f}")

print()
print("解读：")
print("  - 训练 R² 接近 1 + 测试 R² 很低 + gap 大 = 过拟合")
print("  - gap 越小越好；测试 R² 越高越好")
print()
print("论文期望：测试 R² = 0.6293, RMSE = 0.0051")
print("doc 07 硬指标：测试 R² ≥ 0.62, RMSE ≤ 0.0055")
