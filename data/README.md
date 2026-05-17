# 数据目录

> 大文件不进 git（见 `.gitignore`），各子目录用 README 说明源、用途、文件命名约定。

## 目录结构

```
data/
├── raw/
│   ├── modis_ndvi/     MOD13A3 月度 NDVI HDF / GeoTIFF（石灵子 1.3）
│   ├── modis_lst/      MOD11C3 月度 LST HDF / GeoTIFF（石灵子 1.3）
│   ├── gis_province/   省级行政区划（GS(2024)0650）+ DataV 备份（石灵子 1.4）
│   └── gis_cropland/   CLCD 1985-2023 30m 耕地掩膜（石灵子 1.4）
├── interim/
│   ├── modis_province_monthly.parquet   31 省 × 156 月，石灵子产出
│   ├── paper_panel_clean.parquet        论文已有面板清洗后，王天硕产出
│   └── alignment_report.md              时空对齐准确率报告，石灵子 1.7
└── processed/
    └── multimodal_panel_v1.parquet      M1 评审最终交付（2026-07-31）
```

## 数据来源

| 数据 | 来源 | 责任人 | 截止 |
|---|---|---|---|
| MODIS NDVI 月度 1km | [geodata.cn 中国 1km 逐月 NDVI](https://www.geodata.cn/data/datadetails.html?dataguid=197351408897313&docid=1) | 石灵子 | 2026-06-30 |
| MODIS LST 月度 | [AppEEARS](https://appeears.earthdatacloud.nasa.gov/) 或 [MOD11C3](https://www.earthdata.nasa.gov/data/catalog/lpcloud-mod11c3-061) | 石灵子 | 2026-06-30 |
| 省界（出版用） | [天地图 GS(2024)0650](https://cloudcenter.tianditu.gov.cn/administrativeDivision) | 石灵子 | 2026-06-15 |
| 耕地分布 | [CLCD（Zenodo）](https://zenodo.org/records/12779975) | 石灵子 | 2026-06-15 |
| 论文已有面板 | 王天硕从论文实验数据导入 | 王天硕 | 2026-05-15（已逾期，确认状态） |

详见 [`docs/08_数据采集任务_石灵子.md`](../docs/08_数据采集任务_石灵子.md)。
