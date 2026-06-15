#!/usr/bin/env python3
"""v5 Step 7：从 EPS 导出的地级市产量 CSV → 合并到 feature_matrix_v5.parquet

使用方法
--------
1. 登录 EPS 平台 http://www.epsnet.com.cn/
2. 进入 → 中国区域经济数据库
3. 搜索指标「粮食产量(万吨)」，选 10 省 148 地级市 + 2011-2025
4. 导出为 CSV（分省或一次性），放到 data/raw/eps_yield/
5. 在本脚本中修改 FILE_MAP 匹配实际导出的文件名

6. 运行:
   .venv-data/bin/python scripts/data/v5_07_import_city_yield.py

7. 脚本产出:
   - data/interim/city_yield_v5.parquet（清洗后的地级市产量数据）
   - 并合并更新到 feature_matrix_v5.parquet（替换省级 yield 为地级市级别）
"""

import sys
from pathlib import Path
import re

import pandas as pd
import numpy as np

PROJ = Path(__file__).resolve().parents[2]
RAW_DIR = PROJ / "data" / "raw" / "eps_yield"
OUT_YIELD = PROJ / "data" / "interim" / "city_yield_v5.parquet"
V5_PATH = PROJ / "data" / "interim" / "feature_matrix_v5.parquet"
OUT_BACKUP = PROJ / "data" / "interim" / "feature_matrix_v5_before_yield.parquet"

# ============================================================
# 配置区：修改这里匹配你实际的 EPS 导出文件
# ============================================================
#
# EPS 导出 CSV 的格式通常是：
#   省,地级市,年份,粮食产量(万吨)
#
# 如果你一次性导出所有省，自动检测即可。
# 如果按省分多次导出，把文件路径写在下面：

# 【方案 A】一次性导出（推荐）：脚本自动检测 RAW_DIR 中所有 csv/xlsx
# 【方案 B】分省导出：手动填写映射

FILE_MAP = {
    # 如果文件名为 "黑龙江_粮食产量.csv" 格式，自动匹配 province 列
    # 无需手动填写，所有 CSV 都会被扫描
}

# EPS 常见的列名格式映射
COLUMN_ALIASES = {
    "粮食产量(万吨)": "production_wan_ton",
    "粮食产量（万吨）": "production_wan_ton",
    "粮食产量": "production_wan_ton",
    "粮食产量(吨)": "production_ton",
    "粮食产量（吨）": "production_ton",
    "地区": "city",
    "地级市": "city",
    "城市": "city",
    "市": "city",
    "时间": "year",
    "年份": "year",
    "年": "year",
    "省份": "province",
    "省": "province",
    "地区名称": "city",
    "指标名称": "indicator",
}

# 10 个粮食主产省
TEN_PROVINCES = {"黑龙江", "河南", "山东", "吉林", "安徽",
                 "湖南", "河北", "四川", "江苏", "湖北"}

# V5 中的 148 个地级市名称 → 用于校验匹配
V5_CITIES_PATH = None  # 自动从 v5 读取


def normalize_cols(df: pd.DataFrame) -> pd.DataFrame:
    """统一列名"""
    rename = {}
    for c in df.columns:
        c_stripped = c.strip()
        if c_stripped in COLUMN_ALIASES:
            rename[c] = COLUMN_ALIASES[c_stripped]
        else:
            # 模糊匹配
            for alias, std in COLUMN_ALIASES.items():
                if alias in c_stripped or c_stripped in alias:
                    rename[c] = std
                    break
    df = df.rename(columns=rename)

    # 如果还有多余的列，丢弃
    keep = {"province", "city", "year", "production_wan_ton"}
    existing = [c for c in keep if c in df.columns]
    return df[existing].copy()


def clean_city_name(name: str) -> str:
    """标准化地级市名称：去除重复后缀"""
    name = str(name).strip()
    # 处理 "吉林市市" → "吉林市" 这类重复后缀
    while name.endswith("市市"):
        name = name[:-1]
    # 处理 "吉林市" → 用 v5 名称直接匹配，不需要去掉市
    return name


def detect_province_from_filename(fpath: Path) -> str | None:
    """从文件名猜测省份"""
    stem = fpath.stem
    for prov in TEN_PROVINCES:
        if prov in stem:
            return prov
    return None


def read_eps_file(fpath: Path, inferred_province: str | None = None) -> pd.DataFrame | None:
    """读取单个 EPS 导出文件"""
    try:
        if fpath.suffix.lower() == ".csv":
            # 尝试不同编码
            for enc in ["utf-8", "gbk", "gb2312", "gb18030", "latin-1"]:
                try:
                    df = pd.read_csv(fpath, encoding=enc, skipinitialspace=True)
                    break
                except (UnicodeDecodeError, pd.errors.ParserError):
                    continue
            else:
                print(f"  ⚠️  无法解码: {fpath.name}")
                return None
        elif fpath.suffix.lower() in [".xls", ".xlsx"]:
            df = pd.read_excel(fpath)
        else:
            print(f"  ⚠️  不支持的文件格式: {fpath.suffix}")
            return None

        if df.empty:
            return None

        # 统一列名
        df = normalize_cols(df)

        # 检查关键列
        if "production_wan_ton" not in df.columns:
            print(f"  ⚠️  未找到产量列（支持的列: {list(df.columns)}）")
            return None

        if "year" not in df.columns:
            print(f"  ⚠️  未找到年份列")
            return None

        if "city" not in df.columns:
            # 尝试从地区名称中推断
            for c in df.columns:
                if any(kw in c for kw in ["地区", "城市", "市", "city"]):
                    df = df.rename(columns={c: "city"})
                    break
            if "city" not in df.columns:
                print(f"  ⚠️  未找到地级市列")
                return None

        # 添加省份（如果文件名可推断且文件中没有）
        if "province" not in df.columns and inferred_province:
            df["province"] = inferred_province

        # 确保年份是整数
        df["year"] = pd.to_numeric(df["year"], errors="coerce")
        df = df.dropna(subset=["year", "production_wan_ton"])
        df["year"] = df["year"].astype(int)

        # 确保产量是数值
        df["production_wan_ton"] = pd.to_numeric(
            df["production_wan_ton"], errors="coerce"
        )
        df = df.dropna(subset=["production_wan_ton"])

        print(f"  ✅ {fpath.name}: {len(df)} rows (含 {df['year'].nunique()} 年, "
              f"{df['city'].nunique() if 'city' in df.columns else '?'} 地级市)")
        return df

    except Exception as e:
        print(f"  ❌ 读取失败 {fpath.name}: {e}")
        return None


def match_city_to_v5(df: pd.DataFrame, v5_cities: set) -> pd.DataFrame:
    """尝试将 EPS 中的地级市名与 v5 的 city 列匹配"""
    v5_city_names = {c for c in v5_cities}

    # 先清洗城市名
    df["city"] = df["city"].apply(clean_city_name)

    # 尝试直接匹配和模糊匹配
    matched = 0
    unmatched = set()

    for c in df["city"].unique():
        c_str = str(c).strip()
        if c_str in v5_city_names:
            matched += 1
        elif c_str + "市" in v5_city_names:
            df.loc[df["city"] == c, "city"] = c_str + "市"
            matched += 1
        elif c_str.rstrip("市") in v5_city_names:
            new_name = c_str.rstrip("市")
            df.loc[df["city"] == c, "city"] = new_name
            matched += 1
        else:
            unmatched.add(c_str)

    if unmatched:
        print(f"  ⚠️  以下地级市未匹配到 v5:")
        for c in sorted(unmatched):
            print(f"    - {c}")

    print(f"  📊 地级市匹配: {matched}/{matched + len(unmatched)}")
    return df


def main() -> int:
    print("=" * 60)
    print("v5 地级市产量数据导入")
    print("=" * 60)

    # 加载 v5 特征矩阵获取城市列表
    if not V5_PATH.exists():
        print(f"❌ v5 特征矩阵不存在: {V5_PATH}")
        print("   请先运行 v5_06_merge_feature_matrix.py")
        return 1

    v5 = pd.read_parquet(V5_PATH)
    v5_cities = set(v5["city"].unique())
    print(f"\n[0] v5 特征矩阵: {len(v5)} rows × {v5.shape[1]} cols")
    print(f"    地级市: {len(v5_cities)} 个")

    # 读取 EPS 导出文件
    if not RAW_DIR.exists():
        print(f"\n[1] 创建目录: {RAW_DIR}")
        RAW_DIR.mkdir(parents=True, exist_ok=True)
        print(f"    📁 请将 EPS 导出的 CSV 文件放入: {RAW_DIR}")
        print(f"    然后重新运行本脚本。")
        return 0

    files = sorted(RAW_DIR.glob("*"))
    if not files:
        print(f"\n[1] 目录为空: {RAW_DIR}")
        print(f"    📁 请将 EPS 导出的 CSV 文件放入: {RAW_DIR}")
        print(f"    然后重新运行本脚本。")
        return 0

    print(f"\n[1] 读取 EPS 导出文件（{len(files)} 个）...")
    all_dfs = []
    for fpath in files:
        prov_guess = detect_province_from_filename(fpath)
        df = read_eps_file(fpath, prov_guess)
        if df is not None and not df.empty:
            all_dfs.append(df)

    if not all_dfs:
        print("❌ 没有成功读取任何产量数据！")
        print("   支持的格式: CSV (utf-8/gbk) / Excel")
        print("   需要的列: 年份, 地级市/城市, 粮食产量(万吨)")
        return 1

    # 合并
    yield_df = pd.concat(all_dfs, ignore_index=True)
    print(f"\n[2] 合并产量数据: {len(yield_df)} rows")

    # 去重
    dup_before = len(yield_df)
    yield_df = yield_df.drop_duplicates(subset=["province", "city", "year"])
    if len(yield_df) < dup_before:
        print(f"    去重: {dup_before} → {len(yield_df)} rows")

    # 过滤：只留 10 省份
    if "province" in yield_df.columns:
        yield_df = yield_df[yield_df["province"].isin(TEN_PROVINCES)]
        print(f"    10 省过滤后: {len(yield_df)} rows")
    else:
        # 尝试从 city 名称推断省份
        print("  ⚠️  无省份列，尝试从 city_id 匹配省份...")
        city_to_prov = dict(zip(v5["city_id"], v5["province"]))
        # city_id = province_city
        yield_df["province"] = yield_df["city"].map(city_to_prov)
        yield_df = yield_df.dropna(subset=["province"])

    # 匹配地级市名称到 v5
    yield_df = match_city_to_v5(yield_df, v5_cities)

    # 过滤未匹配的
    before = len(yield_df)
    yield_df = yield_df[yield_df["city"].isin(v5_cities)]
    if len(yield_df) < before:
        print(f"    过滤未匹配地级市: {before} → {len(yield_df)} rows")

    # 统计
    print(f"\n[3] 清洗后统计:")
    print(f"    总行数: {len(yield_df)}")
    print(f"    年份范围: {yield_df['year'].min()}-{yield_df['year'].max()}")
    print(f"    地级市数: {yield_df['city'].nunique()}")
    provinces = yield_df.groupby("province")["city"].nunique()
    for prov, cnt in provinces.items():
        print(f"    {prov}: {cnt} 地级市")
    print(f"    产量范围: {yield_df['production_wan_ton'].min():.2f} - "
          f"{yield_df['production_wan_ton'].max():.2f} 万吨")

    # 抽样
    print(f"\n[4] 抽样（河南 郑州市）:")
    sample = yield_df[(yield_df["province"] == "河南") & (yield_df["city"] == "郑州市")]
    if not sample.empty:
        print(sample.sort_values("year").to_string(index=False))

    # 保存
    OUT_YIELD.parent.mkdir(parents=True, exist_ok=True)
    yield_df = yield_df.sort_values(["province", "city", "year"]).reset_index(drop=True)
    yield_df.to_parquet(OUT_YIELD, index=False)
    print(f"\n[5] ✅ 保存清洗后产量: {OUT_YIELD} ({len(yield_df)} rows × {yield_df.shape[1]} cols)")

    # ============================================================
    # 合并到 v5 特征矩阵
    # ============================================================
    print(f"\n{'='*60}")
    print("合并到 feature_matrix_v5.parquet")
    print("=" * 60)

    # 备份
    print(f"\n[6] 备份 v5 → {OUT_BACKUP.name}...")
    v5.to_parquet(OUT_BACKUP, index=False)
    print(f"    ✅ 已备份")

    # 合并：将地级市产量替换掉 v5 中的省级统一值
    print(f"\n[7] 合并地级市产量到 v5...")
    print(f"    策略:")
    print(f"      - 地级市级别 production_wan_ton 替换省级统一值")
    print(f"      - yield_kg_per_ha 替换为地级市级别：单产 = 产量 / 播种面积")
    print(f"      - 缺失地级市回退到省级值")

    # 先看 v5 中有没有播种面积数据（如果有地级市级别的更好）
    has_sown = "sown_qian_ha" in v5.columns  # 省级值

    # 合并地级市产量
    v5_before = v5.copy()

    # 重命名以免冲突
    yield_merge = yield_df[["province", "city", "year", "production_wan_ton"]].copy()
    yield_merge = yield_merge.rename(columns={"production_wan_ton": "production_city"})

    v5_new = v5.merge(
        yield_merge,
        on=["province", "city", "year"],
        how="left"
    )

    # 用地级市产量替换省级产量
    matched = v5_new["production_city"].notna().sum()
    print(f"    地级市产量匹配: {matched}/{len(v5_new)} ({matched/len(v5_new)*100:.1f}%)")

    # 替换省级 production_wan_ton
    mask = v5_new["production_city"].notna()
    v5_new.loc[mask, "production_wan_ton"] = v5_new.loc[mask, "production_city"]
    v5_new = v5_new.drop(columns=["production_city"])

    # 重新计算 yield_kg_per_ha（如果有播种面积）
    if has_sown:
        # 播种面积是省级统一值，但产量现在是地级市级别
        # 所以 yield_kg_per_ha 变成：地级市产量 / 省级播种面积 × 1000
        # = (production_wan_ton * 10000) / (sown_qian_ha * 1000)
        # = production_wan_ton * 10 / sown_qian_ha
        # 产量 万吨 → 万公斤，播种面积 千公顷 → 公顷
        # yield_kg_per_ha = production_wan_ton * 10000 * 1000 / (sown_qian_ha * 1000)
        #                    = production_wan_ton * 10000 / sown_qian_ha
        # 即：单产(kg/公顷) = 产量(万吨) × 10000 / 播种面积(千公顷)
        v5_new["yield_kg_per_ha"] = (
            v5_new["production_wan_ton"] * 10000 / v5_new["sown_qian_ha"]
        )

    # 统计变化
    changed = (v5_new["production_wan_ton"] != v5_before["production_wan_ton"]).sum()
    print(f"    产量值变更: {changed}/{len(v5_new)} ({changed/len(v5_new)*100:.1f}%)")

    if changed > 0:
        print(f"\n    变更示例:")
        diff = v5_new[v5_new["production_wan_ton"] != v5_before["production_wan_ton"]].head(5)
        for _, r in diff.iterrows():
            old_val = v5_before.loc[
                (v5_before["province"] == r["province"]) &
                (v5_before["city"] == r["city"]) &
                (v5_before["year"] == r["year"]),
                "production_wan_ton"
            ].values[0]
            print(f"      {r['province']} {r['city']} {r['year']}: "
                  f"{old_val:.2f} → {r['production_wan_ton']:.2f} 万吨")

    # 保存
    v5_new.to_parquet(V5_PATH, index=False)
    print(f"\n[8] ✅ 最终保存: {V5_PATH}")
    print(f"    Shape: {v5_new.shape}")
    print(f"    NaN total: {v5_new.isna().sum().sum()}")
    print(f"    产量范围: {v5_new['production_wan_ton'].min():.2f} - "
          f"{v5_new['production_wan_ton'].max():.2f} 万吨")

    if has_sown:
        print(f"    单产范围: {v5_new['yield_kg_per_ha'].min():.2f} - "
              f"{v5_new['yield_kg_per_ha'].max():.2f} kg/ha")

    print(f"\n{'='*60}")
    print("完成！")
    print(f"{'='*60}")
    print(f"\n📁 备份: {OUT_BACKUP}")
    print(f"📁 地级市产量: {OUT_YIELD}")
    print(f"📁 v5 更新版: {V5_PATH}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
