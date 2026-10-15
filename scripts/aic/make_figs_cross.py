"""Figures for the 学科交叉 (AI+x) submission: anonymised architecture diagram
and the three-protocol result chart.

Usage:
    python scripts/aic/make_figs_cross.py <out_dir>
"""

from __future__ import annotations

import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch, FancyArrow

INK = "#1F3864"
FILL = "#E8EEF8"
FILL2 = "#F6F8FC"
EDGE = "#9FB4D6"
TEXT = "#26364E"

plt.rcParams["font.sans-serif"] = ["Microsoft YaHei", "SimHei", "SimSun"]
plt.rcParams["axes.unicode_minus"] = False


def box(ax, x, y, w, h, title, body="", fill=FILL, tsize=13.5, bsize=10.5,
        title_at=0.70, body_at=0.30):
    ax.add_patch(FancyBboxPatch((x, y), w, h, boxstyle="round,pad=0.004,rounding_size=0.012",
                                linewidth=1.2, edgecolor=EDGE, facecolor=fill, zorder=2))
    if body:
        ax.text(x + w / 2, y + h * title_at, title, ha="center", va="center",
                fontsize=tsize, color=INK, fontweight="bold", zorder=3)
        ax.text(x + w / 2, y + h * body_at, body, ha="center", va="center",
                fontsize=bsize, color=TEXT, linespacing=1.6, zorder=3)
    else:
        ax.text(x + w / 2, y + h / 2, title, ha="center", va="center",
                fontsize=tsize, color=INK, fontweight="bold", zorder=3)


def band(ax, top, label, boxes, height=0.125, gap=0.018, tag_w=0.072,
         tsize=13.5, bsize=10.5):
    """boxes: list of (title, body) tuples laid out in one row."""
    y = top - height
    ax.add_patch(FancyBboxPatch((0.02, y), 0.96, height, boxstyle="round,pad=0.004,rounding_size=0.014",
                                linewidth=1.3, edgecolor=EDGE, facecolor="#FFFFFF",
                                linestyle=(0, (6, 4)), zorder=1))
    ax.add_patch(FancyBboxPatch((0.032, y + height * 0.18), tag_w, height * 0.64,
                                boxstyle="round,pad=0.003,rounding_size=0.012",
                                linewidth=0, facecolor=INK, zorder=2))
    ax.text(0.032 + tag_w / 2, y + height / 2, label, ha="center", va="center",
            fontsize=13, color="#FFFFFF", fontweight="bold", zorder=3)
    left = 0.032 + tag_w + gap
    total = 0.98 - 0.02 - gap - left
    n = len(boxes)
    bw = (total - gap * (n - 1)) / n
    for i, (title, body) in enumerate(boxes):
        box(ax, left + i * (bw + gap), y + height * 0.09, bw, height * 0.82, title, body,
            tsize=tsize, bsize=bsize)
    return y


def arrow(ax, y_center, text):
    ax.add_patch(FancyArrow(0.5, y_center - 0.014, 0, 0.028, width=0.004,
                            head_width=0.016, head_length=0.013,
                            length_includes_head=True, facecolor=INK, edgecolor=INK, zorder=3))
    ax.text(0.53, y_center, text, ha="left", va="center", fontsize=11, color=INK)


def architecture(path: Path) -> None:
    fig, ax = plt.subplots(figsize=(13.6, 9.2), dpi=200)
    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1)
    ax.axis("off")

    ax.text(0.5, 0.972, "粮食生产气候风险归因决策系统 · 整体架构",
            ha="center", va="center", fontsize=19, color=INK, fontweight="bold")
    ax.text(0.5, 0.936, "数据层 — 算法层 — 应用层三层架构：四模态资料先对齐为省级面板，"
                        "再由原理不同的三类模型做互补归因与校核，最终交付为可交互的决策支持界面",
            ha="center", va="center", fontsize=10.5, color="#5A6B85")

    top = 0.912
    y_app = band(ax, top, "应用层", [
        ("M00 总览", "指标总览\n模型卡入口"),
        ("M01 风险地图", "31 省 × 13 年\n风险等级"),
        ("M02 归因看板", "全局重要性\n单省贡献分解"),
        ("M03 情景模拟", "灌溉 / 化肥 / 降水\n反事实推演"),
        ("M04 韧性路径", "白箱规则\n三阶段对策"),
        ("M05 推演监控", "推理链路\n过程留痕"),
        ("M06 知识助手", "方法论文档\n检索问答"),
    ], tsize=11.5, bsize=9.0)
    arrow(ax, y_app - 0.031, "REST API（JSON）：推理结果与归因结果")

    y_alg = band(ax, y_app - 0.062, "算法层", [
        ("XGBoost-SHAP", "横截面边际贡献\n非线性与交互效应"),
        ("LSTM 基线", "时序拟合参照\n剥离结构调整差异"),
        ("Attention-LSTM", "特征级门控权重\n独立于 SHAP 的第二视角"),
        ("多协议校核", "随机 8:2 · 留一年 · 留一省\n消融与方差分解校核"),
    ], tsize=13, bsize=10)
    arrow(ax, y_alg - 0.031, "特征矩阵：403 样本 × 11 维入模特征")

    y_data = band(ax, y_alg - 0.062, "数据层", [
        ("农业统计", "粮食单产 · 灌溉率\n化肥投入 · 机械化率"),
        ("气象观测", "平均气温 · 降水 · 日照\nSPEI 干旱指数"),
        ("卫星遥感", "MODIS NDVI 与地表温度\n按耕地像元加权聚合"),
        ("致灾与空间", "旱灾 / 水灾受灾面积\n省域行政边界矢量"),
    ], tsize=13, bsize=10)

    # 对齐流程
    fy = y_data - 0.105
    ax.add_patch(FancyBboxPatch((0.02, fy), 0.96, 0.072, boxstyle="round,pad=0.004,rounding_size=0.014",
                                linewidth=1.3, edgecolor=EDGE, facecolor=FILL2, zorder=1))
    steps = [("数据清洗", "缺失值线性插值"), ("时空对齐", "省份 × 年度口径"),
             ("耕地加权", "栅格按耕地像元聚合"), ("标准化", "全列 Z-score"),
             ("四模态融合", "口径台账逐字段留痕")]
    left, gap = 0.038, 0.028
    total = 0.98 - left
    cw = (total - gap * (len(steps) - 1)) / len(steps)
    cursor = left
    for i, (t, b) in enumerate(steps):
        box(ax, cursor, fy + 0.010, cw, 0.052, t, b, fill="#FFFFFF", tsize=11.5, bsize=9.5)
        cursor += cw
        if i < len(steps) - 1:
            ax.text(cursor + 0.014, fy + 0.036, ">", ha="center", va="center",
                    fontsize=14, color=INK, fontweight="bold")
            cursor += 0.028

    # 产出面板
    oy = fy - 0.072
    ax.text(0.038, oy + 0.026, "产出面板", ha="left", va="center", fontsize=12,
            color=INK, fontweight="bold")
    ax.add_patch(FancyBboxPatch((0.155, oy + 0.004), 0.825, 0.044,
                                boxstyle="round,pad=0.004,rounding_size=0.012",
                                linewidth=1.2, edgecolor=EDGE, facecolor="#DCE6F5", zorder=2))
    ax.text(0.567, oy + 0.026, "31 省 × 13 年（2011—2023）= 403 条样本 × 27 字段，"
                               "其中 11 维入模特征 + 1 维目标（粮食单产 kg/ha），无缺失",
            ha="center", va="center", fontsize=10.5, color=INK, zorder=3)

    # 技术栈
    stack_y = oy - 0.046
    ax.add_patch(FancyBboxPatch((0.02, stack_y), 0.96, 0.036, boxstyle="round,pad=0.004,rounding_size=0.010",
                                linewidth=1.1, edgecolor=EDGE, facecolor="#FBFCFE", zorder=2))
    ax.text(0.5, stack_y + 0.018, "技术栈：Python　|　XGBoost　|　SHAP　|　TensorFlow-CPU / Keras　|　"
                                  "Flask + gunicorn　|　Vue 3 + ECharts　|　BGE-M3 混合检索（知识助手）",
            ha="center", va="center", fontsize=10, color=TEXT, zorder=3)
    ax.set_ylim(stack_y - 0.022, 1.0)

    fig.savefig(path, bbox_inches="tight", facecolor="white", pad_inches=0.12)
    plt.close(fig)


def protocols(path: Path) -> None:
    fig, ax = plt.subplots(figsize=(9.2, 4.6), dpi=200)
    labels = ["随机 8:2\n（已见省份相邻样本）", "留一年\n（已见省份的未来年份）",
              "留一省 中位\n（未见省份）"]
    values = [0.907, 0.894, -16.83]
    errs = [0.038, 0.104, 0.0]
    colors = ["#1F3864", "#3C6BA8", "#C0504D"]
    bars = ax.bar(labels, values, width=0.52, color=colors, yerr=errs,
                  error_kw=dict(ecolor="#5A6B85", capsize=6, elinewidth=1.2))
    for bar, v in zip(bars, values):
        inside = v < 0
        ax.text(bar.get_x() + bar.get_width() / 2, (v * 0.5) if inside else (v + 1.1),
                f"{v:+.3f}".rstrip("0").rstrip("."),
                ha="center", va="center" if inside else "bottom", fontsize=12,
                color="#FFFFFF" if inside else INK, fontweight="bold")
    ax.axhline(0, color="#8894A8", linewidth=1)
    ax.set_ylim(-19.5, 3.2)
    ax.set_ylabel("XGBoost R²", fontsize=11.5)
    ax.set_title("三套验证协议下的 XGBoost 表现：先看能用在哪，再看精度多高",
                 fontsize=13, color=INK, pad=12)
    ax.tick_params(axis="x", labelsize=10.5, length=0)
    ax.tick_params(axis="y", labelsize=10)
    for spine in ("top", "right"):
        ax.spines[spine].set_visible(False)
    for spine in ("left", "bottom"):
        ax.spines[spine].set_color("#B7C6DE")
    ax.text(0.5, 0.035, "误差棒为 10 组随机种子的标准差；留一省为 31 折的中位值，31 省中仅 1 省 R² > 0",
            transform=ax.transAxes, ha="center", fontsize=9.5, color="#5A6B85")
    fig.tight_layout()
    fig.savefig(path, facecolor="white")
    plt.close(fig)


def main() -> None:
    out = Path(sys.argv[1])
    out.mkdir(parents=True, exist_ok=True)
    architecture(out / "arch.png")
    protocols(out / "fig_protocols.png")
    for name in ("arch.png", "fig_protocols.png"):
        p = out / name
        print(f"{p}: {p.stat().st_size / 1024:.0f} KB")


if __name__ == "__main__":
    main()
