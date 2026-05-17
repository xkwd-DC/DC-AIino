# 天地图行政区划（GS(2024)0650）— 手动下载步骤

> 你（石灵子）本人操作，因为天地图要求实名注册账号。

## 步骤

1. 注册天地图账号：https://map.tianditu.gov.cn/
   - 邮箱 + 手机号双验证
2. 进行政区划下载中心：https://cloudcenter.tianditu.gov.cn/administrativeDivision
3. 选 **2024 三级行政区划数据库**（带审图号 GS(2024)0650）
4. 下载 **省级**（如果有省+市+县的合包就下合包）
5. 解压到本目录（`data/raw/gis_province/tianditu/`），保留原文件名
6. 在群里同步一句"天地图省界下完了，N MB"

## 为什么必须用天地图

- 论文 / 答辩 PPT 公开图件**必须**带审图号底图（自然资源部要求）
- DataV.GeoAtlas 那一份 GCJ-02 坐标偏移，且无审图号，**不能用于发表的成图**
- GADM / Natural Earth 边界争议（藏南、台湾），**直接拒收**

## 关键参数对比（验收时核对）

| 项 | 应当值 |
|---|---|
| 坐标系 | CGCS2000 或 WGS84（不是 GCJ-02 / BD-09） |
| 审图号 | GS(2024)0650 |
| 九段线 | ✅ 包含 |
| 省份数 | 34（含港澳台） |

下完之后跑 `python scripts/data/02_download_province_geojson.py --verify-tianditu` 做一次完整性自检（待实现）。
