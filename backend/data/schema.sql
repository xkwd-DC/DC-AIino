-- backend/data/schema.sql
-- 粮食风险预测系统 v0.1 · Phase 4 持久层
--
-- 用途: 把 data/interim/paper_panel_v3.parquet (403 行 = 31 省 × 13 年) 灌入 SQLite,
--       供 /api/provinces?year= 和 /api/provinces/<name>/history 查询。
--
-- 三表:
--   provinces       — 31 省静态属性(中英文名 + 大区)
--   yearly_panel    — 31×13 = 403 行面板数据(target + 11 features + 去趋势 Y)
--   metadata        — k-v 键值,记 data_version / loaded_at / parquet_md5 等
--
-- 列名约定: ML feature 用小写下划线(对齐熊鑫 inference.py 的 API_TO_TRAINING 映射,
--           parquet 实际列名以 paper_panel_v3 为准,ETL 内做 column map 处理大小写差异)
--
-- 生成方式: python scripts/load_panel_to_db.py \
--     --parquet data/interim/paper_panel_v3.parquet \
--     --db backend/data/grain.db \
--     --reset
--
-- 见: docs/12 §Phase 4 / docs/11 数据集说明 v1

PRAGMA foreign_keys = ON;
PRAGMA journal_mode = WAL;

-- =====================================================================
-- 1. provinces — 31 省静态属性
-- =====================================================================

CREATE TABLE IF NOT EXISTS provinces (
    name        TEXT    PRIMARY KEY,           -- 中文省名(权威键),如 "河南"
    name_en     TEXT    NOT NULL UNIQUE,       -- 英文 slug,URL 用,如 "henan"
    region      TEXT    NOT NULL               -- 7 大区: 华北/东北/华东/华南/华中/西北/西南
);

-- =====================================================================
-- 2. yearly_panel — 31×13 面板数据(403 行)
-- =====================================================================

CREATE TABLE IF NOT EXISTS yearly_panel (
    province            TEXT    NOT NULL REFERENCES provinces(name) ON DELETE CASCADE,
    year                INTEGER NOT NULL CHECK(year BETWEEN 2011 AND 2023),

    -- 目标(target)
    yield_kg_per_ha     REAL    NOT NULL,      -- 单产(kg/ha),论文 §3.2

    -- 去趋势 Y(method ablation)
    y_butter            REAL,                  -- Butterworth lowpass 双向滤波残差
    y_linear            REAL,                  -- 线性去趋势残差(对照基线)

    -- 11 features(对齐熊鑫 inference.py FEATS,小写下划线)
    ndvi                REAL,                  -- MODIS NDVI 植被指数(2011+)
    temp                REAL,                  -- 气温(°C 或 K,以 parquet 为准)
    prec                REAL,                  -- 降水(mm/年)
    sun                 REAL,                  -- 日照(h/年 或 MJ/m²,见 Issue #23)
    spei                REAL,                  -- 干旱指数 SPEI
    drou_a              REAL,                  -- 旱灾面积(khm²)
    flood_a             REAL,                  -- 洪灾面积(khm²,见 Issue #23)
    flood_r             REAL,                  -- 洪涝相关(单位以 parquet 为准)
    irr                 REAL,                  -- 灌溉率
    fert                REAL,                  -- 化肥使用
    mech                REAL,                  -- 机械化程度

    PRIMARY KEY (province, year)
);

-- =====================================================================
-- 3. metadata — k-v 键值
-- =====================================================================

CREATE TABLE IF NOT EXISTS metadata (
    key     TEXT    PRIMARY KEY,
    value   TEXT    NOT NULL
);

-- 默认元数据(ETL 时 INSERT OR REPLACE 覆盖)
INSERT OR IGNORE INTO metadata (key, value) VALUES
    ('schema_version', '1'),
    ('data_version', 'v3'),
    ('source_parquet', 'data/interim/paper_panel_v3.parquet'),
    ('rows_expected', '403'),
    ('feature_count', '11');

-- =====================================================================
-- Indices — 仅 yearly_panel 需要(provinces / metadata 行数 <= 32)
-- =====================================================================

CREATE INDEX IF NOT EXISTS idx_panel_year ON yearly_panel(year);
CREATE INDEX IF NOT EXISTS idx_panel_province ON yearly_panel(province);

-- =====================================================================
-- 字段口径备注
-- =====================================================================
--
-- yield_kg_per_ha:
--   - 原始单产,target 列,论文 §3.2,真实值非去趋势
--   - 三模型 R²(10 种子均值): XGB 0.9072 / LSTM 0.8856 / Att-LSTM 0.8160
--
-- y_butter:
--   - Butterworth lowpass(order=2) + filtfilt 双向滤波 → 去趋势残差
--   - 按省分组计算,2011/2023 端点用镜像 padding 减边界伪影
--   - 消融基线:模型在该列上 R²≈-0.10(年际波动随机),证明 80% 预测力来自省份签名
--
-- y_linear:
--   - 简单线性去趋势,对照 y_butter 的更激进滤波
--
-- ndvi:
--   - MODIS MOD13A2 月度合成 → 年度均值
--   - 2011 起可用(MODIS Terra 2000-,Aqua 2002-)
--   - 论文 11 维新增列,XGB SHAP #1 ~30% 占比(NDVI 是生物量代理,与 yield 物理接近循环引用)
--
-- sun / prec / flood_a:
--   - ⚠️ Issue #23: v3 实测均值与论文 §3.3 表 3-2 期望值偏差 30-54%
--   - sun: v3 ~3161 h/年 vs 论文 2086 h/年(×1.52)
--   - flood_a: v3 ~527 khm² vs 论文 185 khm²(×2.85)
--   - 等石灵子核对 raw .xlsx 字段定义后可能出 v3.1 patch
--
-- =====================================================================
