"""XGBoost 异常预测 — 省份去基准实验（leave-province-out 泛化验证）

核心诊断（2026-07-05）：
  原始 target = yield_kg_per_ha（绝对产量水平）不是"异常值"。
  特征 irr/mech/fert 等数值强烈绑定省份身份 —— 模型学到的是"识别省份 → 输出
  该省历史产量水平"，而非"气候异常 → 产量异常"的可迁移规律。

  证据：随机 8:2 → R^2=0.907；leave-province-out → R^2=-16.83。

修复思路（非叙事包装，真实改进泛化）：
  1. 目标去省份基准: yield - province_mean 或 yield - province_linear_trend
  2. 特征去省份基准: 每个省自己的 z-score（这一年偏离该省正常年份多少）

三组对比：
  A. 现状复现 — 原始 yield + 原始特征 + leave-province-out → 预期 ≈ -16.83
  B. 异常值(yield - 省均值) + 省内 z-score 特征 → 预期 R^2 翻正
  C. 异常值(yield - 省线性趋势) + 省内 z-score 特征 → 更严格测试

用法：
  .venv\Scripts\python train_xgb_anomaly.py

与 train_xgb_baseline.py 同级放置，复用 paper_panel_v3.parquet 结构。
"""

from pathlib import Path
import json
import hashlib
from datetime import datetime

import numpy as np
import pandas as pd
import xgboost as xgb
from sklearn.linear_model import LinearRegression
from sklearn.metrics import r2_score, root_mean_squared_error

# ═══════════════════════════════════════════════════════════════════════════════
# 可配置项 —— 如果 parquet 列名不同，改这里
# ═══════════════════════════════════════════════════════════════════════════════
DATA_PATH = Path("data/interim/paper_panel_v3.parquet")
PROVINCE_COL = "province"   # 省份列名
YEAR_COL = "year"           # 年份列名
TARGET_COL = "yield_kg_per_ha"  # 原始目标（绝对单产 kg/ha）

# 11 维特征（与 train_xgb_baseline.py 完全一致）
FEATURE_COLS = [
    "irr", "flood", "sun", "temp", "spei", "prec",
    "mech", "fert", "drou_a", "flood_a", "ndvi",
]

# XGBoost 超参（与基线一致，保证可比）
HYPER = dict(
    learning_rate=0.1,
    max_depth=6,
    n_estimators=150,
    objective="reg:squarederror",
)

OUTPUT_DIR = Path("backend/models")
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

# ═══════════════════════════════════════════════════════════════════════════════
# 1. 加载数据
# ═══════════════════════════════════════════════════════════════════════════════
print("=" * 78)
print("XGBoost 异常预测 — leave-province-out 三组对比")
print("=" * 78)

df = pd.read_parquet(DATA_PATH)
data_hash = hashlib.md5(DATA_PATH.read_bytes()).hexdigest()[:12]
n_provinces = df[PROVINCE_COL].nunique()
n_years = df[YEAR_COL].nunique()
print(f"数据: {DATA_PATH}  (MD5 前12位: {data_hash})")
print(f"规模: N={len(df)}  ({n_provinces} 省 × {n_years} 年, {df[YEAR_COL].min()}-{df[YEAR_COL].max()})")
print(f"特征: {len(FEATURE_COLS)} 维 — {FEATURE_COLS}")
print(f"原始 target: {TARGET_COL}")
print(f"  mean={df[TARGET_COL].mean():.1f}  std={df[TARGET_COL].std():.1f}  "
      f"范围=[{df[TARGET_COL].min():.0f}, {df[TARGET_COL].max():.0f}] kg/ha")

provinces = sorted(df[PROVINCE_COL].unique())

# ═══════════════════════════════════════════════════════════════════════════════
# 2. 构建三组配置的 X, y
# ═══════════════════════════════════════════════════════════════════════════════

# --- 2a. 省内统计（每省独立计算，不跨省泄露） ---
print()
print("=" * 78)
print("2. 计算省内统计量（每省独立）")
print("=" * 78)

# 省均值 (target)
province_mean_yield = df.groupby(PROVINCE_COL)[TARGET_COL].transform("mean")

# 省线性趋势 (target) —— 对每个省拟合 year → yield 的 OLS
province_linear_pred = pd.Series(np.nan, index=df.index, dtype=np.float64)
for prov in provinces:
    mask = df[PROVINCE_COL] == prov
    prov_df = df.loc[mask]
    X_year = prov_df[[YEAR_COL]].values  # (n_years, 1)
    y_yield = prov_df[TARGET_COL].values
    lr = LinearRegression().fit(X_year, y_yield)
    province_linear_pred.loc[mask] = lr.predict(X_year)

# 省内特征 z-score（每省自己的均值和标准差）
feature_zscore_within = pd.DataFrame(np.nan, index=df.index, columns=FEATURE_COLS, dtype=np.float64)
eps = 1e-8
for prov in provinces:
    mask = df[PROVINCE_COL] == prov
    prov_features = df.loc[mask, FEATURE_COLS]
    mean = prov_features.mean()
    std = prov_features.std().clip(lower=eps)  # 防止除零（常数特征）
    feature_zscore_within.loc[mask] = (prov_features - mean) / std

# --- 2b. 三组 X, y ---
# A: 原始特征 + 原始 target
X_raw = df[FEATURE_COLS].values.astype(np.float64)
y_raw = df[TARGET_COL].values.astype(np.float64)

# B: 省内 z-score 特征 + 异常值 target (yield - 省均值)
X_zscore = feature_zscore_within[FEATURE_COLS].values.astype(np.float64)
y_anomaly_mean = (df[TARGET_COL] - province_mean_yield).values.astype(np.float64)

# C: 省内 z-score 特征 + 异常值 target (yield - 省线性趋势)
y_anomaly_trend = (df[TARGET_COL] - province_linear_pred).values.astype(np.float64)

# 打印三组 target 的统计摘要
configs = [
    ("A. 现状复现",    X_raw,    y_raw,            "yield_kg_per_ha (绝对产量)"),
    ("B. 异常值-省均值", X_zscore, y_anomaly_mean,   "yield - province_mean"),
    ("C. 异常值-省线性趋势", X_zscore, y_anomaly_trend, "yield - province_linear_trend"),
]

for label, _, y, y_desc in configs:
    print(f"  {label:<22s} target: {y_desc:<45s}  "
          f"μ={np.mean(y):+.1f}  σ={np.std(y):.1f}  "
          f"范围=[{np.min(y):.0f}, {np.max(y):.0f}]")

# ═══════════════════════════════════════════════════════════════════════════════
# 3. Leave-province-out 交叉验证
# ═══════════════════════════════════════════════════════════════════════════════
print()
print("=" * 78)
print(f"3. Leave-province-out CV ({n_provinces} 折，每折留一省作测试)")
print("=" * 78)

all_results = {}

for cfg_label, X, y, y_desc in configs:
    print(f"\n{'─' * 78}")
    print(f"  配置: {cfg_label}")
    print(f"  Target: {y_desc}")
    print(f"{'─' * 78}")

    y_true_all = []
    y_pred_all = []
    fold_results = []

    for test_prov in provinces:
        test_mask = (df[PROVINCE_COL] == test_prov).values
        train_mask = ~test_mask

        X_tr, X_te = X[train_mask], X[test_mask]
        y_tr, y_te = y[train_mask], y[test_mask]

        # 对原始特征 (Config A) 做全局 StandardScaler（fit on train）
        # 对省内 z-score 特征 (Config B/C) 不做额外缩放（已经标准化过）
        if cfg_label.startswith("A"):
            tr_mean = X_tr.mean(axis=0)
            tr_std = X_tr.std(axis=0)
            tr_std[tr_std == 0] = 1.0
            X_tr_s = (X_tr - tr_mean) / tr_std
            X_te_s = (X_te - tr_mean) / tr_std
        else:
            X_tr_s, X_te_s = X_tr, X_te

        model = xgb.XGBRegressor(random_state=42, **HYPER)
        model.fit(X_tr_s, y_tr)

        yp_te = model.predict(X_te_s)

        y_true_all.append(y_te)
        y_pred_all.append(yp_te)

        fold_r2 = r2_score(y_te, yp_te)
        fold_rmse = root_mean_squared_error(y_te, yp_te)
        n_test = len(y_te)
        fold_results.append({
            "province": test_prov,
            "n_test": n_test,
            "r2": float(fold_r2),
            "rmse": float(fold_rmse),
        })

    # 汇总（concatenate 所有折的预测 → 全局 R^2）
    y_true_cat = np.concatenate(y_true_all)
    y_pred_cat = np.concatenate(y_pred_all)
    global_r2 = r2_score(y_true_cat, y_pred_cat)
    global_rmse = root_mean_squared_error(y_true_cat, y_pred_cat)

    # 每折 R^2 的分布统计
    fold_r2s = np.array([fr["r2"] for fr in fold_results])

    print(f"\n  Leave-province-out 汇总 ({n_provinces} 折):")
    print(f"    全局 R^2  (pooled):   {global_r2:+.4f}")
    print(f"    全局 RMSE (pooled):   {global_rmse:.1f}")
    print(f"    单折 R^2  median:      {np.median(fold_r2s):+.4f}")
    print(f"    单折 R^2  mean ± std:  {fold_r2s.mean():+.4f} ± {fold_r2s.std():.4f}")
    print(f"    单折 R^2  min / max:   {fold_r2s.min():+.4f} / {fold_r2s.max():+.4f}")

    # 列出 R^2 最差的 5 个省（诊断哪些省最难外推）
    worst5 = sorted(fold_results, key=lambda x: x["r2"])[:5]
    print(f"\n  R^2 最低的 5 个留出省份:")
    for fr in worst5:
        print(f"    {fr['province']:<12s} n={fr['n_test']:2d}  R^2={fr['r2']:+.4f}  RMSE={fr['rmse']:.1f}")

    all_results[cfg_label] = {
        "label": cfg_label,
        "target_desc": y_desc,
        "global_r2": float(global_r2),
        "global_rmse": float(global_rmse),
        "fold_r2_median": float(np.median(fold_r2s)),
        "fold_r2_mean": float(fold_r2s.mean()),
        "fold_r2_std": float(fold_r2s.std()),
        "fold_r2_min": float(fold_r2s.min()),
        "fold_r2_max": float(fold_r2s.max()),
        "fold_details": fold_results,
    }

# ═══════════════════════════════════════════════════════════════════════════════
# 4. 三组对比汇总
# ═══════════════════════════════════════════════════════════════════════════════
print()
print("=" * 78)
print("4. 三组对比汇总")
print("=" * 78)

header = f"{'配置':<26s}{'Pooled R^2':>12s}{'Median R^2':>12s}{'Mean R^2':>12s}{'Std R^2':>10s}{'Min R^2':>10s}"
print(header)
print("-" * 78)
for cfg_label, _, _, _ in configs:
    r = all_results[cfg_label]
    print(f"{cfg_label:<26s}"
          f"{r['global_r2']:>+12.4f}"
          f"{r['fold_r2_median']:>+12.4f}"
          f"{r['fold_r2_mean']:>+12.4f}"
          f"{r['fold_r2_std']:>10.4f}"
          f"{r['fold_r2_min']:>+10.4f}")

# 解读
print()
print("解读：")
rA = all_results["A. 现状复现"]["global_r2"]
rB = all_results["B. 异常值-省均值"]["global_r2"]
rC = all_results["C. 异常值-省线性趋势"]["global_r2"]

print(f"  A (现状复现)   pooled R^2 = {rA:+.4f}  — 预期 ≈ -16.83，确认省份记忆问题")
if rB > 0:
    print(f"  B (异常值-省均值) pooled R^2 = {rB:+.4f}  ✅ 翻正！"
          f"去省份基准后模型获得了跨省泛化能力 (Δ = {rB - rA:+.2f})")
else:
    print(f"  B (异常值-省均值) pooled R^2 = {rB:+.4f}  — 仍在零以下，"
          f"N=403 可能不足以支撑跨省外推")
if rC > 0:
    print(f"  C (异常值-省线性趋势) pooled R^2 = {rC:+.4f}  ✅ 更严格测试也翻正，"
          f"信号稳健性得到验证")
else:
    print(f"  C (异常值-省线性趋势) pooled R^2 = {rC:+.4f}  — "
          f"线性去趋势后信号更弱，符合预期（更严格）")

print()
if rB > 0 or rC > 0:
    print("  → 结论：去省份基准是真实的泛化能力提升，非叙事包装。")
    print("    可写入论文 §4 作为方法论创新点，替代「诚实披露局限」的止损叙事。")
else:
    print("  → 结论：即使去省份基准，403 样本仍不足以在 11 维特征空间里")
    print("    学到跨省可迁移的气候→产量异常规律。下一步是县级数据下沉。")

# ═══════════════════════════════════════════════════════════════════════════════
# 5. 落盘
# ═══════════════════════════════════════════════════════════════════════════════
print()
print("=" * 78)
print(f"5. 保存结果到 {OUTPUT_DIR}/")
print("=" * 78)

output = dict(
    experiment="leave_province_out_anomaly",
    timestamp=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    data_path=str(DATA_PATH),
    data_md5_12=data_hash,
    n_rows=int(len(df)),
    n_provinces=n_provinces,
    n_years=n_years,
    year_range=[int(df[YEAR_COL].min()), int(df[YEAR_COL].max())],
    province_col=PROVINCE_COL,
    year_col=YEAR_COL,
    target_col=TARGET_COL,
    feature_cols=FEATURE_COLS,
    hyper=HYPER,
    results={k: {
        "label": v["label"],
        "target_desc": v["target_desc"],
        "global_r2": v["global_r2"],
        "global_rmse": v["global_rmse"],
        "fold_r2_median": v["fold_r2_median"],
        "fold_r2_mean": v["fold_r2_mean"],
        "fold_r2_std": v["fold_r2_std"],
        "fold_r2_min": v["fold_r2_min"],
        "fold_r2_max": v["fold_r2_max"],
    } for k, v in all_results.items()},
    interpretation={
        "delta_B_vs_A": float(rB - rA),
        "delta_C_vs_A": float(rC - rA),
        "either_positive": bool(rB > 0 or rC > 0),
    },
)

out_path = OUTPUT_DIR / "xgb_anomaly_lpo_results.json"
out_path.write_text(json.dumps(output, ensure_ascii=False, indent=2))
print(f"  ✓ {out_path.name}  ({out_path.stat().st_size:,} bytes)")

# 生成实验卡片
card_lines = [
    f"# Experiment Card — XGBoost 异常预测 leave-province-out",
    f"",
    f"## 实验信息",
    f"- 日期: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
    f"- 数据: {DATA_PATH} (N={len(df)}, {n_provinces}省×{n_years}年)",
    f"- 特征: {len(FEATURE_COLS)}维 — {', '.join(FEATURE_COLS)}",
    f"- 超参: `{json.dumps(HYPER)}`",
    f"- 验证: leave-province-out ({n_provinces}折)",
    f"",
    f"## 诊断背景",
    f"",
    f"原始模型 (train_xgb_baseline.py) 在随机 8:2 切分下 R^2=0.907，",
    f"但 leave-province-out 预期 R^2≈-16.83。根因：",
    f"",
    f"1. Target = yield_kg_per_ha (绝对产量) → 模型学省份产量基准",
    f"2. 特征 irr/mech/fert 等 = 省份身份代理变量 → 识别省份即可高分",
    f"3. 随机切分时同省样本泄漏到训练集 → 过拟合被 R^2 掩盖",
    f"",
    f"## 三组对比",
    f"",
    f"| 配置 | Target | 特征 | Pooled R^2 | Median R^2 | Mean R^2 ± Std |",
    f"|---|---|---|---|---|---|",
]
for cfg_label, _, _, _ in configs:
    r = all_results[cfg_label]
    card_lines.append(
        f"| {cfg_label} | {r['target_desc']} | "
        f"{'原始 (全局标准化)' if '现状' in cfg_label else '省内 z-score'} | "
        f"{r['global_r2']:+.4f} | {r['fold_r2_median']:+.4f} | "
        f"{r['fold_r2_mean']:+.4f} ± {r['fold_r2_std']:.4f} |"
    )

card_lines += [
    f"",
    f"## 结论",
    f"",
]
if rB > 0 or rC > 0:
    card_lines.append(f"去省份基准后 leave-province-out R^2 翻正 (B: {rB:+.4f}, C: {rC:+.4f})。")
    card_lines.append(f"这是真实的泛化能力提升，可直接写入论文 §4 作为方法论创新点。")
else:
    card_lines.append(f"去省份基准后 R^2 仍为负 (B: {rB:+.4f}, C: {rC:+.4f})。")
    card_lines.append(f"说明 N=403 + 11 维特征确实不足以支撑跨省外推，需县级数据下沉。")

card_lines.append(f"")
card_lines.append(f"## 详细结果")
card_lines.append(f"见 `xgb_anomaly_lpo_results.json`")

card_path = OUTPUT_DIR / "xgb_anomaly_lpo_card.md"
card_path.write_text("\n".join(card_lines))
print(f"  ✓ {card_path.name}  ({card_path.stat().st_size:,} bytes)")

print()
print("=" * 78)
print("异常预测 leave-province-out 实验完成。")
print(f"  A (现状复现):        pooled R^2 = {rA:+.4f}")
print(f"  B (异常值-省均值):    pooled R^2 = {rB:+.4f}  (Δ = {rB - rA:+.2f})")
print(f"  C (异常值-省线性趋势): pooled R^2 = {rC:+.4f}  (Δ = {rC - rA:+.2f})")
print("=" * 78)
