# frontend/public/maps/ — 静态地图资产

> 本目录承载 M01 风险时空地图(RiskMap.vue)用的 China GeoJSON 等静态资源。
> Vite 构建时 `public/` 内容直接复制到 `dist/`,运行时通过 `/maps/china.json` URL 访问。

## 文件清单

| 文件 | 来源 | 用途 | 大小 |
|---|---|---|---|
| `china.json` | [Apache ECharts 4.6 map JSON](https://cdn.jsdelivr.net/gh/apache/echarts@4.6.0/map/json/china.json) | M01 风险地图 `echarts.registerMap('china', ...)` | 61 KB |
| `README.md` | 本文件 | — | — |

## china.json — 中国行政区划 GeoJSON

### 来源 / 版本

- **上游**: [`apache/echarts@4.6.0/map/json/china.json`](https://github.com/apache/echarts/blob/4.6.0/map/json/china.json)
- **协议**: Apache License 2.0(随 ECharts 4.6 一并)
- **下载时间**: 2026-05-22(协调中心整夜 loop [G])
- **下载方式**: `curl -fsSL https://cdn.jsdelivr.net/gh/apache/echarts@4.6.0/map/json/china.json`

### 完整性校验

```
SHA-256: 9b84506a23732efd019d644f8f48254a6501005a2fb236bbbaec3fd89b4efd5b
Bytes:   61008
Format:  GeoJSON FeatureCollection
Features: 34 (31 大陆省 + 台湾 + 香港 + 澳门)
```

任何更新本文件时必须同步更新 SHA-256(防止替换为不受信任版本)。

### 31 省 vs 34 features

`paper_panel_v3.parquet` 数据资产是 **31 省**(不含台湾 / 香港 / 澳门),与本 GeoJSON 的 34 features 不完全对齐:

| 集合 | 数量 | 备注 |
|---|---|---|
| paper_panel_v3 | 31 | 大陆 31 省级行政区 |
| china.json features | 34 | + 台湾 / 香港 / 澳门 |
| 渲染交集 | 31 | 港澳台显示"无数据"灰色,RiskMap 已有处理 |

## 为什么自托管(不走 CDN)

**Issue PR #20 review HIGH#3 + Issue #26 MEDIUM#5**(协调中心 2026-05-22 5 agent 评审产出):

| 风险 | CDN 模式 | 自托管 |
|---|---|---|
| 现场演示断网 | 8s timeout 后地图空白 | ✅ 不依赖外网 |
| CDN 被劫持 / 替换 | 客户端拿到恶意 GeoJSON 风险 | ✅ 仓库内,git 历史可审计 |
| SRI 缺失 | 无完整性校验 | ✅ 本 README SHA-256 |
| 评审场所网络限制 | 国内/国际 CDN 不可控 | ✅ 同源 same-origin |

## 引用方式

**当前 (PR #20 上的 RiskMap.vue:18)**:
```ts
const resp = await fetch('https://cdn.jsdelivr.net/gh/apache/echarts@4.6.0/map/json/china.json', { ... })
```

**目标(潘 followup PR / fix/pr20-followup 分支)**:
```ts
const resp = await fetch('/maps/china.json', { ... })
// 同源,无 CORS,无 8s timeout 风险,SRI 由 git commit hash 保证
```

### 切换步骤 (留给潘)

1. Edit `frontend/src/views/RiskMap.vue:18`:
   ```diff
   - const resp = await fetch('https://cdn.jsdelivr.net/gh/apache/echarts@4.6.0/map/json/china.json', ...)
   + const resp = await fetch('/maps/china.json', ...)
   ```
2. 可同时移除 8000 ms AbortController 或缩到 2000 ms(同源 fetch 不需要那么长)
3. dev 服 `npm run dev` 时 vite 会自动从 `public/maps/china.json` serve
4. build `vite build` 时 `public/maps/china.json` 复制到 `dist/maps/china.json`
5. nginx (`deploy/nginx.conf` PR #33) 直服 `/maps/*`

## 后续考虑

### 港澳台显示

当前 34 features 中港澳台无 paper_panel_v3 数据 → ECharts visualMap 默认会以 `outOfRange` 颜色 (灰色) 渲染。这是预期行为。

如果将来扩数据到包含港澳台,直接在 ETL `scripts/load_panel_to_db.py` 内的 `PROVINCE_TO_REGION` / `PROVINCE_TO_SLUG` dict 加 3 项即可,GeoJSON 无需改动。

### ECharts 5 升级

当前 GeoJSON 来自 ECharts 4.6 系列,ECharts 5 仍兼容此格式。若将来 ECharts 升级到 6,需重新评估 GeoJSON 兼容性(GADM / Natural Earth 是更广泛维护的替代源)。

### Map 边界政治性问题

ECharts 官方 GeoJSON 采用中华人民共和国官方界线(含九段线表示)。这是国内学术答辩 + 国际期刊投稿都需要的版本。**勿替换为 Natural Earth / GADM**(可能不含九段线)。

—— 协调中心整夜 loop · [G] · 2026-05-22
