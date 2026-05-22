"""诊断 Y 的趋势结构，决定 Butterworth 去趋势怎么做。

回答两个问题：
  Q1: Y 的下降是「全国统一下降」还是「每个省自己有不同趋势」？
      → 决定按省独立去趋势 vs 全局去趋势
  Q2: 13 年这么短的序列，Butterworth 截止频率怎么选？
      → 先看趋势是单调还是有周期
"""
import numpy as np
import pandas as pd

df = pd.read_parquet("data/interim/paper_panel_v2.parquet").sort_values(["province", "year"])

# ─── Q1: 全国 vs 各省 Y 趋势 ─────────────────────────────────────────────
print("=" * 72)
print("Q1. Y 趋势：全国统一 vs 各省独立？")
print("=" * 72)
print("\n全国年均 Y：")
nationwide = df.groupby("year")["y"].mean()
for y, v in nationwide.items():
    bar = "█" * int(v * 1000)
    print(f"  {y}  {v:.4f}  {bar}")

print(f"\n2011→2023 全国均值跌幅：{(nationwide.iloc[-1] - nationwide.iloc[0]) / nationwide.iloc[0] * 100:+.1f}%")

# 各省线性回归斜率（年→y）
print("\n各省 Y vs year 的斜率（负=下降，正=上升）：")
slopes = []
for prov, g in df.groupby("province"):
    slope = np.polyfit(g["year"], g["y"], 1)[0]
    slopes.append((prov, slope))
slopes.sort(key=lambda x: x[1])
print(f"{'最下降 5 省':<14s}", end="")
for p, s in slopes[:5]:
    print(f"{p}({s*1000:+.2f}/yr) ", end="")
print()
print(f"{'最上升 5 省':<14s}", end="")
for p, s in slopes[-5:]:
    print(f"{p}({s*1000:+.2f}/yr) ", end="")
print()

slopes_arr = np.array([s for _, s in slopes])
print(f"\n31 省斜率统计：mean={slopes_arr.mean()*1000:.3f}/yr  std={slopes_arr.std()*1000:.3f}/yr")
n_neg = (slopes_arr < 0).sum()
print(f"下降省份数：{n_neg}/31    上升省份数：{31 - n_neg}/31")

# ─── Q2: 趋势是单调还是有周期 ────────────────────────────────────────────
print()
print("=" * 72)
print("Q2. 趋势形态：单调下降 vs 有周期？")
print("=" * 72)
print("\n看几个有代表性的省（前/中/后）：")
sample_provs = ["北京市", "河南省", "黑龙江省", "新疆维吾尔自治区", "四川省"]
for p in sample_provs:
    g = df[df["province"] == p].sort_values("year")
    line = " ".join(f"{v:.3f}" for v in g["y"].values)
    print(f"  {p:<14s} {line}")

print("\n→ 如果是「单调下降+小波动」：Butterworth 低通滤波器频率截 0.2~0.3（保留高频波动）")
print("→ 如果有 4~6 年周期：要把截止频率放更高，否则把信号当趋势滤掉")

# ─── Q3: 各省非平稳程度 ─────────────────────────────────────────────────
print()
print("=" * 72)
print("Q3. 各省 Y 的 std 对 trend 的比例（去趋势空间有多大）")
print("=" * 72)
total_var = df["y"].var()
within_prov_var = df.groupby("province")["y"].var().mean()
print(f"总方差（across all 403 obs）：{total_var:.6f}")
print(f"省内方差（mean across 31 prov）：{within_prov_var:.6f}")
print(f"省内方差占比：{within_prov_var/total_var*100:.1f}%")
print("\n→ 省内方差占比越低，说明 Y 的差异主要来自「省间均值不同」（漂移）")
print("→ 去趋势后省内方差占比应该接近 100%")
