# 论文已有面板（1.2 任务）

> 任务 1.2「复用论文已有数据接入仓库」，原王天硕 → 2026-05-16 起归石灵子。
> 截止：原 2026-05-15（已逾期），新目标 **2026-05-23**。

## 期望文件

把从王天硕/邱老师/潘妙齐手上拿到的原始数据丢这里。**不限格式**：

| 期望 | 文件名建议 |
|---|---|
| 原始合并面板（论文版） | `paper_panel_raw.csv` 或 `paper_panel_raw.xlsx` |
| 拆分多个变量的文件 | `yield.csv`、`weather.csv`、`disaster.csv`、`stats.csv`…… |
| 邱老师/王天硕给的原始包 | 保留原文件名 + 后缀 `_orig` |

## 期望 schema（最终合并后）

每行 = 一个 (province, year) 二元组：

```
province     str  中文全称，例如 "河南省"
year         int  2011..2023
yield        float 粮食单产（论文 Y 列原始值，去趋势前）
irr          float 灌溉率 %
flood        float 洪涝占比 %
sun          float 日照时数 小时/年
temp         float 年均温 °C
spei         float SPEI 指数（无量纲）
prec         float 年降水量 mm
mech         float 农业机械总动力 万 kW
fert         float 化肥施用量 万吨
drou_a       float 旱灾面积比 %
flood_a      float 涝灾面积比 %
```

NDVI 不进这份文件（由 MODIS pipeline 后续合并）。

## 行数

31 省 × 13 年 = **403 行**。若有缺失，登记原因到 `data/interim/paper_panel_missing.md`。

## 转换脚本

拿到原始数据后跑：

```bash
.venv-data/bin/python scripts/data/00_ingest_paper_panel.py --src data/raw/paper_panel/原始文件.xlsx
```

输出 `data/interim/paper_panel_raw.parquet`，schema 由 `scripts/data/validate_paper_panel.py` 校验（待写）。
