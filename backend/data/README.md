# backend/data/ — 持久层数据资产

> 本目录承载 Phase 4 (5/27-28) 引入的 SQLite 持久层。
> 上游单一数据源: `data/interim/paper_panel_v3.parquet` (石灵子 PR #7 / PR #11)
> 下游消费方: `backend/api/provinces.py` 的 `/api/provinces?year=` 和 `/api/provinces/<name>/history`

## 文件清单

| 文件 | 用途 | 入仓? |
|---|---|---|
| `schema.sql` | 三表 schema + 默认元数据 + 字段口径备注 | ✅ |
| `README.md` | 本文件 | ✅ |
| `provinces_baseline.json` | v0.1 mock baseline(31 省最新年,Phase 1 用) | ✅ |
| `grain.db` | SQLite 数据库 | ❌ `.gitignore`(可从 parquet 重建) |
| `.gitkeep` | 占位 | ✅ |

## ER 简图

```
┌────────────────┐         ┌─────────────────────────────────────┐
│ provinces      │  1───n  │ yearly_panel                        │
│ (31 行)        │         │ (403 行 = 31 省 × 13 年, 2011-2023) │
│                │         │                                     │
│ • name (PK)    │◄────────│ • province (FK)                     │
│ • name_en      │         │ • year                              │
│ • region       │         │ • yield_kg_per_ha (target)          │
└────────────────┘         │ • y_butter, y_linear (去趋势 Y)     │
                           │ • 11 features (ndvi/temp/prec/...)  │
                           │ PK: (province, year)                │
                           └─────────────────────────────────────┘

┌────────────────┐
│ metadata       │
│ (k-v 键值)     │
│                │
│ • key (PK)     │
│ • value        │
└────────────────┘
```

## 生成数据库

```bash
# Phase 4 完整 ETL(待 feat/phase4-etl 落地)
python scripts/load_panel_to_db.py \
    --parquet data/interim/paper_panel_v3.parquet \
    --db backend/data/grain.db \
    --reset

# 验证
sqlite3 backend/data/grain.db "SELECT COUNT(*) FROM yearly_panel"  # 应 = 403
sqlite3 backend/data/grain.db "SELECT DISTINCT year FROM yearly_panel ORDER BY year"  # 2011-2023
sqlite3 backend/data/grain.db "SELECT COUNT(*) FROM provinces"  # 应 = 31
sqlite3 backend/data/grain.db "SELECT * FROM metadata"
```

## 列名约定 vs parquet 实际列名

熊鑫 inference.py 内有 `API_TO_TRAINING` 映射(因为 parquet 列名是大小写 + 部分缩写,如 `flood` 不是 `flood_r`)。本 schema 用统一的**小写下划线**约定;ETL (`scripts/load_panel_to_db.py`) 内部要做 `TRAINING_TO_PARQUET` 反向映射处理:

| schema 列 | parquet 列(熊鑫规则) | 备注 |
|---|---|---|
| `ndvi` | `NDVI` | 大小写 |
| `temp` | `Temp` | |
| `prec` | `Prec` | |
| `sun` | `Sun` | Issue #23 单位待核 |
| `spei` | `SPEI` | |
| `drou_a` | `Drou_A` | |
| `flood_a` | `Flood_A` | Issue #23 单位待核 |
| `flood_r` | `flood`?或 `Flood_R` | PR #21 发现 parquet 实际是 `flood`,需 ETL 校验 |
| `irr` | `Irr` | |
| `fert` | `Fert` | |
| `mech` | `Mech` | |
| `yield_kg_per_ha` | `yield_kg_per_ha` | |
| `y_butter` | `y_butter` | 石灵子 v3 Butterworth |
| `y_linear` | `y_linear` | 石灵子 v3 线性去趋势 |

**ETL Day 1 上午第一步**:`pd.read_parquet().columns` 打印实际列名,补全/修正本表。

## Migration story (v0.1 阶段)

不引入 alembic / sqlx migrate。Schema 变更 = `--reset` 重灌:

```bash
rm backend/data/grain.db
python scripts/load_panel_to_db.py --parquet ... --db backend/data/grain.db --reset
```

理由: parquet 是 single source of truth (石灵子 v3 / v4),13 年历史不可变,SQLite 是衍生 cache。

## 大区映射(provinces.region)

ETL 内硬编码 31 省 → 7 大区,作为 M01 风险地图前端聚合用:

| 大区 | 省份 |
|---|---|
| 华北 | 北京 / 天津 / 河北 / 山西 / 内蒙古 |
| 东北 | 辽宁 / 吉林 / 黑龙江 |
| 华东 | 上海 / 江苏 / 浙江 / 安徽 / 福建 / 江西 / 山东 |
| 华中 | 河南 / 湖北 / 湖南 |
| 华南 | 广东 / 广西 / 海南 |
| 西南 | 重庆 / 四川 / 贵州 / 云南 / 西藏 |
| 西北 | 陕西 / 甘肃 / 青海 / 宁夏 / 新疆 |

注: 7 大区共 31 省。台湾 / 香港 / 澳门不在 paper_panel_v3 范围。

## 字段口径备注

详见 `schema.sql` 底部注释。重点 ⚠️ Issue #23: `sun` / `prec` / `flood_a` 三列 v3 实测与论文期望偏差 30-54%,等石灵子核对后可能出 v3.1 patch。

## 与 docs/11 数据集说明 v1 的关系

`docs/11_数据集说明_v1.md` 是 M1 评审硬交付物,详尽描述 paper_panel_v3 字段;本 schema 是其**机器可读子集** + 持久化结构。任何 schema 变更须同步更新 docs/11。
