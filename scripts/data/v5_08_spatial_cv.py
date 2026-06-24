#!/usr/bin/env python3
"""v5 Step 8：严格空间 CV（leave-province-out）

依赖：
  feature_matrix_v5.parquet（v5_06 输出，含 MODIS/CLCD/NASA 城市级特征）
  data/raw/eps_yield/eps_city_yield_all.csv（EPS 城市产量）

如果 feature_matrix_v5.parquet 不存在，则回退到 v4 省级特征（基准模式）。

运行：
  .venv-data/bin/python scripts/data/v5_08_spatial_cv.py

产出：
  reports/v5_spatial_cv_report.md  — 严格 CV 报告（go/no-go 扳机）
  reports/v5_cv_fold_results.csv   — 各折 R²/RMSE
"""

import sys
from pathlib import Path
import warnings
warnings.filterwarnings("ignore")

import numpy as np
import pandas as pd
from sklearn.metrics import r2_score, mean_squared_error
import xgboost as xgb

PROJ = Path(__file__).resolve().parents[2]
V5_FEAT = PROJ / "data" / "interim" / "feature_matrix_v5.parquet"
V4_FEAT = PROJ / "data" / "interim" / "paper_panel_v4.parquet"
EPS_YIELD = PROJ / "data" / "raw" / "eps_yield" / "eps_city_yield_all.csv"
REPORT_DIR = PROJ / "reports"

# EPS 省份名（全称）→ v5 短名 / v4 全称 映射
PROV_FULL_TO_SHORT = {
    "安徽省": "安徽", "湖北省": "湖北", "河南省": "河南",
    "江苏省": "江苏", "河北省": "河北", "浙江省": "浙江",
}
# v4 使用全称，v5 使用短名
V4_PROV_NAMES = {v: k for k, v in PROV_FULL_TO_SHORT.items()}

# 10 粮食主产省（短名）
TEN_PROVINCES = {"黑龙江", "河南", "山东", "吉林", "安徽",
                 "湖南", "河北", "四川", "江苏", "湖北"}

# XGBoost 超参（参照 v3 训练设定）
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

# v4 省级特征列（去掉标签列）
V4_FEATURE_COLS = [
    "irr", "flood", "sun", "temp", "spei", "prec",
    "mech", "fert", "drou_a", "flood_a",
    "ndvi", "prec_capital", "sun_capital",
    "ndvi_summer_peak", "ndvi_yearly",
    "lst_day_growing_mean_k", "lst_night_growing_mean_k",
    "sown_qian_ha", "cropland_ratio",
]

# v5 城市级特征列（比 v4 多了城市粒度的遥感+气象）
V5_FEATURE_COLS = [
    "ndvi_yearly", "ndvi_summer_peak",
    "lst_day_growing_mean_k", "lst_night_growing_mean_k",
    "cropland_ratio",
    "temp_mean_c", "prec_mm_day",
    "irr", "flood", "mech", "fert", "drou_a", "flood_a",
    "spei",
]


def load_eps_yield() -> pd.DataFrame:
    df = pd.read_csv(EPS_YIELD)
    df["province_short"] = df["province"].map(PROV_FULL_TO_SHORT)
    # 过滤到 10 主产省的交集（去掉浙江）
    df = df[df["province_short"].isin(TEN_PROVINCES)].copy()
    df = df.dropna(subset=["production_wan_ton"])
    df["production_wan_ton"] = pd.to_numeric(df["production_wan_ton"], errors="coerce")
    df = df.dropna(subset=["production_wan_ton"])
    print(f"  EPS 城市产量: {len(df)} 行, {df['province_short'].nunique()} 省, "
          f"{df['city'].nunique()} 市")
    return df


def build_v5_dataset() -> tuple[pd.DataFrame, str, list[str]]:
    """尝试加载 v5 城市级特征矩阵。失败则退回 v4。"""
    if V5_FEAT.exists():
        print(f"\n[模式] v5 城市级特征矩阵 ✅")
        feat = pd.read_parquet(V5_FEAT)
        print(f"  v5 特征: {feat.shape}")

        # 名称对齐：v5 province 已是短名
        eps = load_eps_yield()

        # dropna 检查
        avail_feat = [c for c in V5_FEATURE_COLS if c in feat.columns]
        feat_clean = feat.dropna(subset=avail_feat)
        dropped = len(feat) - len(feat_clean)
        if dropped > 0:
            print(f"  dropna 丢弃: {dropped} 行 ({dropped/len(feat)*100:.1f}%)")

        # 合并：features ∩ yield（内连接）
        # eps 的 production_wan_ton 是城市级真实产量，v5 里的是省级填充值
        # 用不同列名避免冲突，统一用城市级产量作为目标
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
        print(f"\n[模式] v4 省级特征（基准，feature_matrix_v5.parquet 不存在）⚠️")
        print(f"  提示: 需从石灵子机器 scp feature_matrix_v5.parquet 才能跑真正的城市级 CV")
        feat = pd.read_parquet(V4_FEAT)

        # v4 province 是全称，EPS 也是全称 → 直接 merge
        eps = load_eps_yield()
        # eps 中 province 是全称，city 有城市名
        # v4 按 province + year 提供省级特征，城市共享同一行特征

        eps_10 = eps.copy()  # 已经过滤了 10 主产省
        # 将 eps 的 province 全称映射到短名（用于后续 fold key）
        # v4 province 全称
        feat_v4 = feat[feat["province"].isin(
            [V4_PROV_NAMES[s] for s in TEN_PROVINCES if s in V4_PROV_NAMES]
        )].copy()

        avail_feat = [c for c in V4_FEATURE_COLS if c in feat_v4.columns]

        # merge：city 产量 × 省级特征（按 province全称 + year）
        merged = eps_10.merge(
            feat_v4[["province", "year"] + avail_feat],
            left_on=["province", "year"],
            right_on=["province", "year"],
            how="inner",
        )
        # 统一 province 列为短名
        merged["province_short"] = merged["province"].map(PROV_FULL_TO_SHORT)
        print(f"  合并后（v4基准）: {len(merged)} 行 × {merged.shape[1]} 列")
        return merged, "v4_province_features_baseline", avail_feat


def run_leave_province_out_cv(
    df: pd.DataFrame,
    feature_cols: list[str],
    mode: str,
) -> tuple[pd.DataFrame, dict]:
    """Leave-one-province-out 空间 CV，目标 = log(production_wan_ton)。"""
    df = df.copy()
    df["log_production"] = np.log(df["production_wan_ton"])
    pkey = "province_short" if "province_short" in df.columns else "province"
    provinces = sorted(df[pkey].unique())
    print(f"\n[CV] Leave-province-out: {len(provinces)} 折")
    print(f"  特征数: {len(feature_cols)}")
    print(f"  目标: log(production_wan_ton)")

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
        n_train = train_mask.sum()
        n_test = test_mask.sum()

        fold_results.append({
            "fold": held_out,
            "n_train": int(n_train),
            "n_test": int(n_test),
            "n_cities": int(n_cities),
            "r2": round(r2, 4),
            "rmse_log": round(rmse, 4),
        })
        all_preds.extend(y_pred.tolist())
        all_true.extend(y_test.tolist())

        symbol = "✅" if r2 > 0 else "❌"
        print(f"  {symbol} 留出 {held_out}: R²={r2:.4f}, RMSE={rmse:.4f} "
              f"(train={n_train}, test={n_test}, cities={n_cities})")

    folds_df = pd.DataFrame(fold_results)
    overall_r2 = r2_score(all_true, all_preds)
    median_r2 = folds_df["r2"].median()
    mean_r2 = folds_df["r2"].mean()

    summary = {
        "mode": mode,
        "n_provinces": len(provinces),
        "overall_r2": round(overall_r2, 4),
        "median_r2": round(median_r2, 4),
        "mean_r2": round(mean_r2, 4),
        "n_positive_folds": int((folds_df["r2"] > 0).sum()),
        "total_observations": len(all_true),
    }

    print(f"\n  汇总: overall_R²={overall_r2:.4f}, "
          f"median={median_r2:.4f}, mean={mean_r2:.4f}")
    print(f"  正向折数: {summary['n_positive_folds']}/{len(provinces)}")

    return folds_df, summary


def variance_decomposition(df: pd.DataFrame) -> dict:
    """计算城市产量的省间 vs 省内方差分解。"""
    df = df.copy()
    df["log_production"] = np.log(df["production_wan_ton"])
    pkey = "province_short" if "province_short" in df.columns else "province"

    total_var = df["log_production"].var()
    prov_means = df.groupby(pkey)["log_production"].mean()
    between_var = (
        df[pkey].map(prov_means) - df["log_production"].mean()
    ).var()
    within_var = total_var - between_var
    icc = between_var / total_var if total_var > 0 else 0.0

    print(f"\n[方差分解] log(production_wan_ton)")
    print(f"  总方差: {total_var:.4f}")
    print(f"  省间方差: {between_var:.4f} ({between_var/total_var*100:.1f}%)")
    print(f"  省内方差: {within_var:.4f} ({within_var/total_var*100:.1f}%)")
    print(f"  ICC (省间/总): {icc:.4f}")

    return {
        "total_var": round(total_var, 4),
        "between_province_var": round(between_var, 4),
        "within_province_var": round(within_var, 4),
        "icc": round(icc, 4),
        "between_pct": round(between_var / total_var * 100, 1),
    }


def write_report(folds_df: pd.DataFrame, summary: dict, var_decomp: dict,
                 mode: str) -> Path:
    REPORT_DIR.mkdir(exist_ok=True)
    report_path = REPORT_DIR / "v5_spatial_cv_report.md"
    csv_path = REPORT_DIR / "v5_cv_fold_results.csv"

    folds_df.to_csv(csv_path, index=False)

    verdict = (
        "**GO ✅** — 城市级空间 CV 正向，有真实泛化能力"
        if summary["overall_r2"] > 0
        else "**NO-GO ❌** — 空间外推仍然失败，R² 为负"
    )

    if mode == "v4_province_features_baseline":
        mode_note = (
            "⚠️ **基准模式**：使用 v4 省级特征（所有城市共享同省特征）。"
            "这是城市级 CV 的**下界**，不代表真正的城市级信号。\n"
            "真正的 go/no-go 需要 `feature_matrix_v5.parquet`（石灵子机器）。"
        )
    else:
        mode_note = "✅ **v5 城市级特征**（MODIS/CLCD/NASA POWER 城市分辨率）"

    lines = [
        "# v5 严格空间 CV 报告",
        "",
        f"> 生成时间：2026-06-24",
        f"> 特征模式：{mode}",
        "",
        "## 一句话结论",
        "",
        verdict,
        "",
        "---",
        "",
        "## 模式说明",
        "",
        mode_note,
        "",
        "## 方差分解",
        "",
        "| 指标 | 值 |",
        "|------|----|",
        f"| 总方差 (log production) | {var_decomp['total_var']} |",
        f"| 省间方差 | {var_decomp['between_province_var']} ({var_decomp['between_pct']}%) |",
        f"| 省内方差 | {var_decomp['within_province_var']} ({100-var_decomp['between_pct']}%) |",
        f"| ICC (省内相关系数) | {var_decomp['icc']:.3f} |",
        "",
        "## Leave-Province-Out CV 结果",
        "",
        "| 留出省份 | 训练样本 | 测试样本 | 测试城市数 | R² | RMSE(log) |",
        "|---------|----------|----------|-----------|-----|-----------|",
    ]

    for _, row in folds_df.iterrows():
        sym = "✅" if row["r2"] > 0 else "❌"
        lines.append(
            f"| {row['fold']} {sym} | {row['n_train']} | {row['n_test']} | "
            f"{row['n_cities']} | {row['r2']:.4f} | {row['rmse_log']:.4f} |"
        )

    lines += [
        "",
        "## 汇总统计",
        "",
        "| 指标 | 值 |",
        "|------|----|",
        f"| Overall R² (pooled) | **{summary['overall_r2']:.4f}** |",
        f"| Median R² | {summary['median_r2']:.4f} |",
        f"| Mean R² | {summary['mean_r2']:.4f} |",
        f"| 正向折数 | {summary['n_positive_folds']}/{summary['n_provinces']} |",
        f"| 总观测数 | {summary['total_observations']} |",
        "",
        "## 结论与下一步",
        "",
    ]

    if mode == "v4_province_features_baseline":
        if summary["overall_r2"] > 0:
            lines += [
                "省级特征下城市级 CV 为正，说明省间差异可被省级特征解释。",
                "需进一步运行 v5 城市级特征 CV 确认城市粒度的额外增益。",
                "",
                "**下一步**：从石灵子机器传输 `feature_matrix_v5.parquet`，重跑本脚本。",
            ]
        else:
            lines += [
                "省级特征无法解释城市级产量的省间差异（R² < 0）。",
                "这是**下界**结果：真正的城市级特征（MODIS/NASA/CLCD 城市分辨率）可能改善，",
                "但下界已为负，则上界是否足够需要城市级特征实验来验证。",
                "",
                "**下一步**：",
                "```bash",
                "# 从石灵子机器获取 v5 特征矩阵（三个文件，约 10-50 MB）",
                "scp slz@<SLZ_IP>:/home/slz/workspace/DC-AIino/data/interim/feature_matrix_v5.parquet \\",
                "    /home/darcy/DC/DC/data/interim/",
                "# 然后重跑",
                ".venv-data/bin/python scripts/data/v5_08_spatial_cv.py",
                "```",
            ]
    else:
        if summary["overall_r2"] > 0:
            lines += [
                "城市级特征空间 CV 正向 → **GO**。",
                "可以写论文：「城市粒度的气候-产量模型在留出省份上泛化」。",
            ]
        else:
            lines += [
                "城市级特征空间外推仍然失败 → **NO-GO**（正刊路线）。",
                "建议转「方法论/负结果」路线，或 purely-temporal CV + 有限区域论文。",
            ]

    report_path.write_text("\n".join(lines), encoding="utf-8")
    print(f"\n  ✅ 报告写入: {report_path}")
    print(f"  ✅ 各折数据: {csv_path}")
    return report_path


def main() -> int:
    print("=" * 60)
    print("v5 严格空间 CV（Leave-Province-Out）")
    print("=" * 60)

    # 1. 构建数据集
    df, mode, feature_cols = build_v5_dataset()

    if df.empty or len(feature_cols) == 0:
        print("❌ 数据集为空，退出")
        return 1

    provinces = df["province_short"].unique() if "province_short" in df.columns \
        else df["province"].unique()
    print(f"\n  省份: {sorted(provinces)}")
    print(f"  城市: {df['city'].nunique()}")
    print(f"  年份: {sorted(df['year'].unique())}")
    print(f"  总观测: {len(df)}")

    # 2. 方差分解
    var_decomp = variance_decomposition(df)

    # 3. Leave-Province-Out CV
    folds_df, summary = run_leave_province_out_cv(df, feature_cols, mode)

    # 4. 写报告
    report_path = write_report(folds_df, summary, var_decomp, mode)

    # 5. 最终判决
    print("\n" + "=" * 60)
    print("最终判决")
    print("=" * 60)
    verdict = "GO ✅" if summary["overall_r2"] > 0 else "NO-GO ❌"
    print(f"  {verdict}")
    print(f"  Overall R²  = {summary['overall_r2']:.4f}")
    print(f"  Median R²   = {summary['median_r2']:.4f}")
    print(f"  正向折数    = {summary['n_positive_folds']}/{summary['n_provinces']}")

    if mode == "v4_province_features_baseline":
        print(f"\n  ⚠️  这是基准（省级特征）结果，不是最终判决。")
        print(f"  真正的 go/no-go 需要 feature_matrix_v5.parquet（城市级特征）。")

    return 0


if __name__ == "__main__":
    sys.exit(main())
