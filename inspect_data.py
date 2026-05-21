"""第一次读真实数据——看看潘交给你的 panel 长什么样。

跑法：/home/xxfql/DC-AIino/.venv/bin/python /home/xxfql/DC-AIino/inspect_data.py
"""
import pandas as pd

PATH = "data/interim/paper_panel_raw.parquet"
df = pd.read_parquet(PATH)

print("=" * 70)
print("数据基本情况")
print("=" * 70)
print(f"文件：{PATH}")
print(f"形状：{df.shape[0]} 行 × {df.shape[1]} 列")
print(f"列名：{list(df.columns)}")
print(f"内存占用：{df.memory_usage(deep=True).sum() / 1024:.1f} KB")

print()
print("=" * 70)
print("前 5 行（让你眼睛见一下真数据）")
print("=" * 70)
print(df.head().to_string())

print()
print("=" * 70)
print("每列数据类型 + 缺失值数量")
print("=" * 70)
info = pd.DataFrame({
    "dtype": df.dtypes.astype(str),
    "缺失值数": df.isna().sum(),
    "缺失%": (df.isna().sum() / len(df) * 100).round(2),
})
print(info.to_string())

print()
print("=" * 70)
print("Y（粮食单产风险）的统计")
print("=" * 70)
print(df["y"].describe())

print()
print("=" * 70)
print("覆盖年份 / 省份")
print("=" * 70)
print(f"年份范围：{df['year'].min()} ~ {df['year'].max()}")
print(f"省份数：{df['province'].nunique()}")
print(f"省份样本：{df['province'].unique()[:10]} ...")

print()
print("=" * 70)
print("河南 2022（对比 doc 07 §3.3 的验收测试样例）")
print("=" * 70)
henan_2022 = df[(df["province"] == "河南") & (df["year"] == 2022)]
if len(henan_2022) > 0:
    for col in henan_2022.columns:
        val = henan_2022.iloc[0][col]
        print(f"  {col:18s} {val}")
else:
    print("⚠️ 找不到河南 2022——检查省份名/年份格式")

print()
print("=" * 70)
print("结论")
print("=" * 70)
print("如果上面 10 个特征 + y 都有值（NDVI 那一列暂时缺正常，潘 MODIS 还在跑），")
print("说明数据加载完全 OK，你下一步可以用这 10 维数据训练 XGBoost 基线。")
