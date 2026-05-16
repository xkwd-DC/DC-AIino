# scripts/data — 数据采集 pipeline

> 数据工程：石灵子 ｜ 任务：docs/08_数据采集任务_石灵子.md ｜ 验收：M1 评审 2026-07-31

## 环境

独立 venv（与 `backend/.venv` 隔离）：

```bash
# 一次性
uv venv --python 3.11 .venv-data
uv pip install --python .venv-data/bin/python -r scripts/data/requirements-pipeline.txt

# 每次跑脚本
.venv-data/bin/python scripts/data/01_download_cropland.py --year 2022
```

## 凭证

需要登录的数据源把账号写进项目根 `.env`（已 gitignored）：

```bash
# .env（本地不入库）
EARTHDATA_USERNAME=your-nasa-earthdata-username
EARTHDATA_PASSWORD=...
GEODATA_CN_TOKEN=...      # geodata.cn 登录态 cookie 或 token
TIANDITU_KEY=...          # 天地图开发者 key（如果走 API 而非网页下载）
```

`.env.example` 是签到模板，可以入库（值用占位符）。

## 脚本执行顺序

| # | 脚本 | 输入 | 输出 | 是否需要账号 |
|---|---|---|---|---|
| 01 | `01_download_cropland.py` | Zenodo public | `data/raw/gis_cropland/CLCD_v01_YYYY_albert.tif` | ❌ |
| 02 | `02_download_province_geojson.py` | DataV public + 天地图手动 | `data/raw/gis_province/{datav,tianditu}/` | 部分（天地图） |
| 03 | `03_download_modis_ndvi.py`（待写） | geodata.cn 月度 NDVI | `data/raw/modis_ndvi/*.tif` | ✅ |
| 04 | `04_download_modis_lst.py`（待写） | NASA AppEEARS API | `data/raw/modis_lst/*.tif` | ✅ |
| 05 | `05_aggregate_to_province.py`（待写） | 上述全部 | `data/interim/modis_province_monthly.parquet` | ❌ |
| 06 | `06_align_panel.py`（待写） | 05 + 论文已有面板 | `data/processed/multimodal_panel_v1.parquet` | ❌ |
| 校验 | `validate_modis_panel.py`（已写） | 05 的输出 | `data/interim/alignment_report.md` | ❌ |

## 储存策略（重要）

当前磁盘剩 ~6 GB，**装不下全 13 年 CLCD（~10 GB）**。三个选项：

### 方案 A：COG 流式（推荐）
CLCD 已确认是 Cloud Optimized GeoTIFF。聚合脚本可以直接：

```python
import rasterio
with rasterio.open("https://zenodo.org/api/records/12779975/files/CLCD_v01_2022_albert.tif/content") as src:
    # rasterio 走 HTTP range request，只读省界 bbox 的像元
    pixels = src.read(1, window=src.window(*henan_bounds))
```

- ✅ 零本地储存
- ✅ 不重复下载（每次只读 bbox 内的像元）
- ❌ 网络抖动需要 retry，速度受 Zenodo CDN 限制

### 方案 B：外置盘
申请阿里云学生 OSS 或买个移动硬盘（500GB 约 200 元，从 0.3 万数据采集费里出）。

- ✅ 网络隔离稳定
- ❌ 多人协作要同步硬盘内容

### 方案 C：用一年代替一年（不推荐）
全部用 2020 年的耕地掩膜套到 2011-2023，**会冲掉东北开荒/南方退耕的趋势信号**——doc 08 §5.1 已经把这种做法定为红线。

**默认走方案 A**，写聚合脚本时直接用 Zenodo COG URL。本地只保留 2022 一份做开发期 sanity check。

## MODIS 储存

NDVI 全国 月度 1km 2011-2023 ≈ 3 GB；LST C3 0.05° ≈ 1 GB。这俩可以全下本地。

## 进度看板

- [x] 环境（uv 3.11 + rasterio/geopandas/earthaccess）
- [x] `01_download_cropland.py` + CLCD 2022 验证
- [x] `02_download_province_geojson.py` + DataV 公开数据
- [ ] 注册 NASA EARTHDATA 账号（人事，由石灵子本人）
- [ ] 注册天地图账号 + 手动下 GS(2024)0650（人事）
- [ ] 注册 geodata.cn 账号（人事）
- [ ] `03_download_modis_ndvi.py`
- [ ] `04_download_modis_lst.py`
- [ ] `05_aggregate_to_province.py`（用 COG 流式策略）
- [ ] `06_align_panel.py`
- [ ] M1 评审（2026-07-31）
