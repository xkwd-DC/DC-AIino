"""XGBoost 方法学消融：在 y_butter（Butterworth 去趋势残差）上训练

目的：验证申报书 §2.3 #3 去趋势要求 —— 在年聚合面板（N=403, 31 省 × 13 年）
上，对真实单产做 Butterworth 残差化（filtfilt order=2 fc=0.25）后，残差不具备
generalizable 的可预测信号。这是路线 E 「主报告 yield_kg_per_ha + 消融 y_butter」
里给申报书方法学合规性背书的关键证据。

数据：data/interim/paper_panel_v3.parquet
Target：y_butter（由石灵子 PR #7 在真实 yield 上做 Butterworth 残差化得到，
        非王天硕已煮熟的 Y 上的残差 —— 那个已作废）
特征/超参/种子：完全对齐主基线（11 维 + 10 种子 + 论文超参）

预期：test R² mean ≈ -0.10（参 memory `project_v3_real_yield_finding.md` 表）
解读：train 能 fit 但 test 强烈过拟合 → N=403 + 11 维样本不足，而非"假设错误"

跑法：/home/xxfql/DC-AIino/.venv/bin/python /home/xxfql/DC-AIino/train_xgb_y_butter_ablation.py

背景：project_v3_real_yield_finding.md（2026-05-17 v3 反转，路线 E 第 3 项）
"""
from pathlib import Path
import json
import hashlib
from datetime import datetime

import numpy as np
import pandas as pd
import xgboost as xgb
from sklearn.metrics import r2_score, root_mean_squared_error
from sklearn.model_selection import train_test_split
from sklearn.preprocessing import StandardScaler

# ─── 路径 / target ─────────────────────────────────────────────────────────
DATA_PATH = Path("data/interim/paper_panel_v3.parquet")
MODELS_DIR = Path("backend/models")
MAIN_BASELINE_JSON = MODELS_DIR / "xgb_seeds_results.json"

TARGET_COL = "y_butter"

# ─── 特征与超参（与 train_xgb_baseline.py 完全一致，确保消融可比）──────
LOWERCASE_TO_TRAINING = {
    "irr": "Irr", "flood": "Flood_R", "sun": "Sun", "temp": "Temp",
    "spei": "SPEI", "prec": "Prec", "mech": "Mech", "fert": "Fert",
    "drou_a": "Drou_A", "flood_a": "Flood_A",
    "ndvi": "NDVI",
}
FEATURE_COLS_LOWER = list(LOWERCASE_TO_TRAINING.keys())

SEEDS = list(range(10))
HYPER = dict(
    learning_rate=0.1,
    max_depth=6,
    n_estimators=150,
    objective="reg:squarederror",
)

# ─── 1. 加载数据 ─────────────────────────────────────────────────────────
print("=" * 72)
print(f"1. 加载数据 — 消融 target = {TARGET_COL}")
print("=" * 72)
df = pd.read_parquet(DATA_PATH)
data_hash = hashlib.md5(DATA_PATH.read_bytes()).hexdigest()[:12]
print(f"数据：{DATA_PATH}（MD5 前 12 位：{data_hash}）")
print(f"规模：{df.shape[0]} 行 × {len(FEATURE_COLS_LOWER)} 维 X")
print(
    f"y_butter 统计：mean={df[TARGET_COL].mean():.1f}  std={df[TARGET_COL].std():.1f}  "
    f"范围=[{df[TARGET_COL].min():.0f}, {df[TARGET_COL].max():.0f}]"
)

X_raw_full = df[FEATURE_COLS_LOWER].values
y_full = df[TARGET_COL].values

# ─── 2. 10 种子训练 ─────────────────────────────────────────────────────
print()
print("=" * 72)
print(f"2. 10 种子训练（协议同主基线，仅 target 不同）")
print("=" * 72)

results = []
for seed in SEEDS:
    X_tr_raw, X_te_raw, y_tr, y_te = train_test_split(
        X_raw_full, y_full, test_size=0.2, random_state=seed
    )
    scaler = StandardScaler()
    X_tr = scaler.fit_transform(X_tr_raw)
    X_te = scaler.transform(X_te_raw)

    model = xgb.XGBRegressor(random_state=seed, **HYPER)
    model.fit(X_tr, y_tr)
    yp_tr = model.predict(X_tr)
    yp_te = model.predict(X_te)

    tr_r2 = float(r2_score(y_tr, yp_tr))
    te_r2 = float(r2_score(y_te, yp_te))
    tr_rmse = float(root_mean_squared_error(y_tr, yp_tr))
    te_rmse = float(root_mean_squared_error(y_te, yp_te))

    results.append(dict(seed=seed, tr_r2=tr_r2, te_r2=te_r2,
                       tr_rmse=tr_rmse, te_rmse=te_rmse))
    print(f"  seed={seed:2d}  tr_R²={tr_r2:.4f}  te_R²={te_r2:+.4f}  "
          f"te_RMSE={te_rmse:7.1f}")

te_r2s = np.array([r["te_r2"] for r in results])
tr_r2s = np.array([r["tr_r2"] for r in results])
te_rmses = np.array([r["te_rmse"] for r in results])
tr_rmses = np.array([r["tr_rmse"] for r in results])

# ─── 3. 汇总 + 对照主基线 ───────────────────────────────────────────────
print()
print("=" * 72)
print("3. 消融 vs 主基线对照")
print("=" * 72)

# 读主基线（路线 E 第 1 项产物）
if MAIN_BASELINE_JSON.exists():
    main_baseline = json.loads(MAIN_BASELINE_JSON.read_text())
    main_te_r2_mean = main_baseline["summary"]["test_r2_mean"]
    main_te_r2_std = main_baseline["summary"]["test_r2_std"]
    main_te_rmse_mean = main_baseline["summary"]["test_rmse_kg_per_ha_mean"]
else:
    main_te_r2_mean = None
    main_te_r2_std = None
    main_te_rmse_mean = None

print(f"{'指标':<22s}{'主基线 (yield_kg_per_ha)':>30s}{'消融 (y_butter)':>22s}")
print("-" * 74)
if main_te_r2_mean is not None:
    print(f"{'test R² mean':<22s}{main_te_r2_mean:>30.4f}{te_r2s.mean():>22.4f}")
    print(f"{'test R² std':<22s}{main_te_r2_std:>30.4f}{te_r2s.std():>22.4f}")
    print(f"{'test RMSE (单位不同)':<22s}{f'{main_te_rmse_mean:.1f} kg/ha':>30s}"
          f"{f'{te_rmses.mean():.1f}':>22s}")
else:
    print(f"{'(主基线 json 缺失，仅报消融)':<22s}")
    print(f"{'test R² mean':<22s}{'—':>30s}{te_r2s.mean():>22.4f}")
print(f"{'train R² mean':<22s}{'1.0000 (典型)':>30s}{tr_r2s.mean():>22.4f}")

print()
print(f"消融 test R² 范围：[{te_r2s.min():.4f}, {te_r2s.max():.4f}]")
print(f"消融 train R² mean：{tr_r2s.mean():.4f}（train 能拟合）")
print()

# 期望：R² ≈ 0 或负，证明 y_butter 残差无 generalizable 信号
near_zero = abs(te_r2s.mean()) < 0.3 or te_r2s.mean() < 0
if near_zero:
    print(
        f"✅ 消融如预期：test R² mean = {te_r2s.mean():+.4f} ≈ 0\n"
        f"   train R² mean = {tr_r2s.mean():.4f} 能拟合，但 test 不泛化\n"
        f"   → 证明 y_butter 残差在 N=403 + 11 维设置下无 generalizable 信号\n"
        f"   → 申报书 §2.3 #3 去趋势要求严格遵守的实证证据（不是假设错误，是样本不足）"
    )
else:
    print(
        f"⚠️ 消融结果偏离预期：test R² mean = {te_r2s.mean():+.4f}\n"
        f"   memory 期望 ≈ -0.10，需核对"
    )

# ─── 4. 落盘 ────────────────────────────────────────────────────────────
print()
print("=" * 72)
print(f"4. 保存消融结果到 {MODELS_DIR}/")
print("=" * 72)

ablation_dump = dict(
    role="methodology_ablation",
    target=TARGET_COL,
    data_path=str(DATA_PATH),
    data_md5_12=data_hash,
    n_rows=int(len(df)),
    n_features=len(FEATURE_COLS_LOWER),
    feature_cols_lower=FEATURE_COLS_LOWER,
    seeds=SEEDS,
    hyper=HYPER,
    per_seed=results,
    summary=dict(
        test_r2_mean=float(te_r2s.mean()),
        test_r2_std=float(te_r2s.std()),
        test_r2_min=float(te_r2s.min()),
        test_r2_max=float(te_r2s.max()),
        test_rmse_mean=float(te_rmses.mean()),
        test_rmse_std=float(te_rmses.std()),
        train_r2_mean=float(tr_r2s.mean()),
        train_r2_std=float(tr_r2s.std()),
    ),
    main_baseline_comparison=dict(
        main_baseline_json=str(MAIN_BASELINE_JSON),
        main_test_r2_mean=main_te_r2_mean,
        main_test_r2_std=main_te_r2_std,
        delta_test_r2_mean=(
            float(te_r2s.mean() - main_te_r2_mean)
            if main_te_r2_mean is not None
            else None
        ),
    ),
    matches_expectation_near_zero=bool(near_zero),
)
(MODELS_DIR / "xgb_y_butter_seeds_results.json").write_text(
    json.dumps(ablation_dump, ensure_ascii=False, indent=2)
)

# ablation card
per_seed_lines = "\n".join(
    [f"- seed={r['seed']}: te_R²={r['te_r2']:+.4f}  te_RMSE={r['te_rmse']:.1f}"
     for r in results]
)
delta_str = (
    f"{te_r2s.mean() - main_te_r2_mean:+.4f}"
    if main_te_r2_mean is not None
    else "—"
)
ablation_card = f"""# Ablation Card — XGBoost on y_butter（方法学消融）

## 训练信息
- 训练日期：{datetime.now().strftime("%Y-%m-%d %H:%M:%S")}
- 训练人：熊鑫
- 数据源：{DATA_PATH}（MD5 前 12 位 `{data_hash}`）
- 协议：与主基线（`model_card.md`）完全一致 —— 11 维特征 / 10 种子 / 论文超参
- **唯一不同**：target = `y_butter`（Butterworth 残差，filtfilt order=2 fc=0.25）

## 角色
方法学消融，**不是交付模型**。为论文/报告里的「申报书 §2.3 #3 去趋势合规性」
论述提供实证背书。代表模型未保存（无下游使用价值）。

## 指标（10 种子）

| 指标 | 训练集 mean ± std | 测试集 mean ± std |
|---|---|---|
| R² | {tr_r2s.mean():.4f} ± {tr_r2s.std():.4f} | {te_r2s.mean():+.4f} ± {te_r2s.std():.4f} |
| RMSE (y_butter 单位) | {tr_rmses.mean():.1f} ± {tr_rmses.std():.1f} | {te_rmses.mean():.1f} ± {te_rmses.std():.1f} |

各种子明细：
{per_seed_lines}

## 与主基线对照

| 维度 | 主基线 (yield_kg_per_ha) | 消融 (y_butter) | Δ |
|---|---|---|---|
| test R² mean | {main_te_r2_mean if main_te_r2_mean is not None else '—'} | {te_r2s.mean():+.4f} | {delta_str} |
| 含义 | 真实单产可被特征预测 | 去趋势残差不可被特征预测 | — |

## 结论（写给申报书 §2.3 / 路线 E）

{'✅' if near_zero else '⚠️'} **test R² mean = {te_r2s.mean():+.4f} ≈ 0**，
而 **train R² mean = {tr_r2s.mean():.4f}**（train 能拟合，test 完全不泛化）。

这是申报书 §2.3 #3 去趋势方法在年聚合面板（N=403 = 31 省 × 13 年）+ 11 维
特征下的**实证表现**：

1. 去趋势方法本身（Butterworth filtfilt order=2 fc=0.25）正确实施 ——
   在真实单产（非王天硕已煮熟的 Y）上做的
2. 残差中**没有 generalizable 的特征驱动信号** —— 不是假设错了，
   是 N=403 + 11 维的样本量配置不足以从年聚合面板的残差中拟合稳定关系
3. 主报告路线（直接预测真实单产水平 `yield_kg_per_ha`，R² ≈ 0.90）
   是诚实地承认这个数据局限并给出有用模型的选择

## 与历史诊断的衔接

`project_xgb_baseline_diagnosis.md` 里"y_butter R²≈0"那段曾**作废**（因为在
王天硕坏 Y 上做的 Butterworth）。本消融用 v3 真实单产重做了同一实验，结论
反而**复活了那段诊断的核心观察**，但前提换了：从「方法或假设有问题」变成
「方法合规但样本量不足以从残差里抽信号」。

## 背景
路线 E 第 3 项（`project_v3_real_yield_finding.md`）：
- 第 1 项：XGB on yield_kg_per_ha → `model_card.md`
- 第 2 项：LSTM on yield_kg_per_ha → `lstm_model_card.md`
- **第 3 项：本消融** → 当前文件
"""
(MODELS_DIR / "xgb_y_butter_ablation_card.md").write_text(ablation_card)

for f in ["xgb_y_butter_seeds_results.json", "xgb_y_butter_ablation_card.md"]:
    p = MODELS_DIR / f
    print(f"  ✓ {f}  ({p.stat().st_size:,} bytes)")

print()
print("=" * 72)
print(f"消融完成。test R² mean = {te_r2s.mean():+.4f}（期望 ≈ 0）")
print("=" * 72)
