# STORYBOARD — 稷韧云图 · 20 秒产品片

**Format:** 1920×1080 ／ 30fps ／ 总长 20.00s
**Audio:** Kokoro-82M 中文女声（zf_xiaobei, speed 1.2）＋ 合成环境底噪音床 ＋ 数据 tick 音效
**VO direction:** 冷静、克制、有分量的科技纪录片旁白。句子之间留白是设计的一部分，不抢画面。
**Style basis:** `DESIGN.md`（深墨绿仪表盘、1px 描边、等宽数值、风险色阶）

## Global guardrails

- 全片底色锁死 `#162520`，任何一帧都不得出现白底或满屏线性渐变（H.264 会出色带）。
- 每个 beat ≥ 2 层景深；屏幕上的每一个元素都必须有入场动作，静止的图等于 PPT。
- 数字一律 `JetBrains Mono` + `tabular-nums`，与页面口径一致。
- 场景之间必须有转场，且**只做入场不做退场**（转场本身就是退场）。仅最后一镜允许淡出。
- 色阶语义：绿 `#A0B785` = 安全/提升，琥珀 `#E6B655` = 中风险，赭石 `#B86F4D` = 高风险/下降。

## Voiceover beats（真实时间戳，来自 `narration.wav`）

| Beat | 起止 | 时长 | 旁白 |
| ---- | ---- | ---- | ---- |
| 1 | 0.00 – 5.74 | 5.74s | 极端气候，正在重写中国粮食的风险地图。 |
| 2 | 5.74 – 10.27 | 4.53s | 稷韧云图，四类数据源，三模型互补归因。 |
| 3 | 10.27 – 14.90 | 4.63s | 因子归因到省，情景模拟两秒出结果。 |
| 4 | 14.90 – 20.00 | 5.10s | 让 AI，看见每一粒粮食的气候风险。 |

## Asset Audit

| Asset | Type | Assign to Beat | Role |
| ----- | ---- | -------------- | ---- |
| `assets/map/china-risk.svg` | 数据地图（脚本生成） | Beat 1 | 主视觉：真实省界 + 站点同口径风险配色，省份渐次点亮 |
| `shots/01-risk-map.png` | 应用截图 | Beat 1 | 右下行小图，证明地图来自真实系统 |
| `shots/00-overview.png` | 应用截图 | Beat 2 | 主面板：四源就绪度 + 三项指标 + 三模型标签 |
| `shots/06-chat.png` | 应用截图 | Beat 2 | 右上漂浮小卡，说明还有知识助手 |
| `shots/02-shap.png` | 应用截图 | Beat 3 | 左半屏：SHAP 归因看板（化肥施用量 89.6%） |
| `shots/03-scenario.png` | 应用截图 | Beat 3 | 右半屏：基线 0.0400 → 模拟 0.0225 仪表盘 |
| `shots/04-pathway.png` | 应用截图 | Beat 4 | 三段式韧性路径，纵向滚动露出 |
| `assets/map/risk-baseline.json` | 数据 | Beat 1 | Top10 榜与色阶取值的唯一来源（与页面逐项核对过） |
| `narration.wav` | 音频 | — | 母带 20.00s |
| `underscore.wav` | 音频 | — | 合成 pad，音量 0.16 |
| `sfx-tick.wav` | 音频 | Beat 1/2/3 | 数据落位音效 |
| `sfx-whoosh.wav` | 音频 | 转场点 | 转场气声 |

品牌徽标（`粮` 方形渐变块）在 **Beat 1 左上角**与 **Beat 4 正中间**各出现一次；站点标志性视觉（中国风险地图）出现在 Beat 1。

---

## BEAT 1 — 风险地图（0.00 – 5.74）

**VO:** 极端气候，正在重写中国粮食的风险地图。

### Concept

画面一开始就已经在一个运行中的仪器台前。深墨绿底上，中国地图从暗处一块块被"点亮"——先是西北的赭石色压下来，然后是东部转成琥珀。这不是一张静态地图，是一台正在读数的设备：扫描线横掠而过，右侧 Top10 榜单的条形一根根顶出来。观众在旁白说完之前就已经读懂了"哪里最危险"。

### Visual

- **BG**：`#162520` 实底 ＋ 两处极淡径向光（左上绿 4%、右下琥珀 3%）＋ 64px 点阵网格（`#2A3D38`，透明度 0.35）。
- **MG（主视觉）**：`assets/map/china-risk.svg`，约 980×780，略偏左。省份按"危险程度从高到低"依次淡入并带上描边亮起；高风险的西藏/青海/新疆/内蒙古最先烧起来。
- **扫描线**：一条 2px 的 `#C5D4AF` 竖线从左到右扫过地图，扫过之处省份短暂提亮（用一层叠加的绿色 mask 达成，不用滤镜）。
- **FG（标注）**：三枚 leader 标注贴在地图上——`青海 0.0400`、`西藏 0.0380`、`新疆 0.0360`，等宽字体，带 1px 引线。
- **右栏榜单**：`Top 10 高风险省份`，10 行等宽数字 + 横向条形，条形按风险值宽度从 0 拉出，逐行错位 60ms。
- **左下读数**：`YEAR 2023` 大字 + `2011 — 2023 · 13 年` 等宽小字，年份数字从 2011 快速滚到 2023。
- **左上角落**：品牌徽标 + `M01 · SPATIO-TEMPORAL RISK MAP` 等宽小标。

### Camera

极慢推近：容器 `scale 1.0 → 1.055`，同时向左上漂移 26px，ease 全程 `none`。让地图"读得越来越近"。

### Animation choreography

| 元素 | 动词 |
| ---- | ---- |
| 地图 | LIGHTS UP：省份按风险降序 stagger 0.045s 淡入 |
| 扫描线 | SWEEPS：0.8s 横掠一次，`ease power2.inOut` |
| 标注 | DRAWS：引线先画（scaleX 0→1），文字再浮出 |
| 榜单条 | FILLS：宽度 0 → 目标值，逐行 60ms 级联 |
| 年份 | TICKS：2011 → 2023 计数器 |
| 点阵网格 | DRIFTS：整片缓慢平移 12px（在本场景时间线上，不在 timeline 外） |

### Transition OUT

**Zoom through**（CSS）：整场 `scale 1 → 1.18` + `blur 0 → 22px` + `opacity → 0`，0.45s，`power3.in`；下一场从 `scale 0.86 / blur 22px` 淡入。

### Depth layers

BG 实底 + 径向光 + 点阵 ／ MG 地图 ／ FG 标注 + 榜单 + 年份读数。

### SFX

0.30s 处一次极轻的 tick（旁白入声）；地图点亮完成时 2.6s 一次 tick；转场点一次 whoosh。

---

## BEAT 2 — 云图是什么（5.74 – 10.27）

**VO:** 稷韧云图，四类数据源，三模型互补归因。

### Concept

镜头退开，地图缩成整个系统的一块面板。真实界面从左下斜着推上来，四张数据源卡依次"盖章"落位，三个模型标签在右侧组成一个三角形。信息密度陡增——这是全片的"规模感"时刻。

### Visual

- **主面板**：`shots/00-overview.png` 以 `rotationY -7°` 的透视角度占据中央偏左，外层加 1px `#44615A` 描边与极深投影。
- **四源芯片**：`省级统计`／`MODIS 遥感`／`气象逐日观测`／`GIS 矢量` 四枚芯片从左下角依次飞出，落到主面板左边缘排成一列，每枚右侧带一条 100% 就绪进度线（宽度 0→100%）。
- **三模型标签**：`XGB-SHAP`／`LSTM`／`Attention-LSTM` 三枚标签在右上方落位，之间用细线连接成三角，中心写 `三模型互补归因`。
- **右上漂浮卡**：`shots/06-chat.png` 缩成 460px 宽的小卡，缓慢上下浮动（±6px，`sine.inOut`，有限次重复）。
- **品牌落版（左上）**：`粮` 徽标 + `稷韧云图` + `FOOD-RISK INTELLIGENCE PLATFORM` 等宽副标。
- **底部数据线**：`31 省 · 13 年 · 403 样本 · 11 维` 等宽滚动 ticker（有限次循环，位移连续）。

### Camera

从右上向左下缓移 40px，`scale 0.94 → 1.0`，与上一场的推近形成方向上的反差。

### Animation choreography

| 元素 | 动词 |
| ---- | ---- |
| 主面板 | SLIDES UP：`y 90 → 0`、`opacity 0 → 1`、`rotationY -14 → -7`，0.7s `expo.out` |
| 四源芯片 | STAMP：`scale 1.25 → 1` + `opacity`，逐枚 0.12s 级联 |
| 就绪线 | FILLS：`scaleX 0 → 1`，`power2.out` |
| 三模型标签 | LOCK IN：从三角外沿飞入，末位落定时其余两枚轻微回弹 1.03× |
| 漂浮卡 | FLOATS：`y ±6`，`sine.inOut`，计算好次数 |
| ticker | CRAWLS：`x` 连续位移，`ease none` |

### Transition OUT

**竖直数据擦除**（CSS）：整场 `clip-path inset(0 0 0 0) → inset(50% 0 50% 0)` 收成一条线，0.4s `power3.in`；下一场从中心线展开。

### Depth layers

BG 点阵 ／ MG 主面板 ／ FG 芯片 + 标签 + 漂浮卡 + ticker。

### SFX

四源芯片每落一枚一次 tick（0.10s 间隔感）；转场 whoosh。

---

## BEAT 3 — 证据（10.27 – 14.90）

**VO:** 因子归因到省，情景模拟两秒出结果。

### Concept

屏幕被一条硬边从中线劈开：左半是"为什么"，右半是"如果"。左边 SHAP 的条形图一根根长出来，右边仪表盘的指针从基线甩到模拟值——`0.0400` 掉到 `0.0225`，中间那个 `−43.7%` 是全片最有说服力的一帧。

### Visual

- **左半屏**：`shots/02-shap.png` 裁切到 `化肥施用量 89.6% / 灌溉率 4.9% / 洪涝占比 4.9%` 的条形区域，放大到 1.25 倍，缓慢左移 18px。顶部叠加等宽小标 `M02 · SHAP ATTRIBUTION`。
- **右半屏**：`shots/03-scenario.png` 裁切到两个仪表盘区域，与左侧同一水平线。
- **中央竖分割线**：1px `#44615A`，从中心向上下展开（`scaleY 0 → 1`）。
- **大数字读数**：左半下方 `Δ 化肥施用量 89.6%`，右半下方 `0.0400 → 0.0225`，中间一枚绿色 chip `−43.7% 风险下降`，等宽字体 64px。
- **角标**：右上 `INFERENCE < 2s`，`#C5D4AF`。

### Camera

两半以相反方向轻微对推：左半 `x 0 → -18`，右半 `x 0 → 18`，`ease none`，制造"两边都在朝你说话"的张力。

### Animation choreography

| 元素 | 动词 |
| ---- | ---- |
| 左半面板 | WIPES IN：从中心线向左展开 |
| 右半面板 | WIPES IN：从中心线向右展开，延后 0.08s |
| 分割线 | GROWS：`scaleY 0 → 1`，0.3s `power2.out` |
| 89.6% | COUNTS：0 → 89.6，一位小数 |
| 0.0400 / 0.0225 | COUNTS：两个数字各自数到位 |
| −43.7% chip | SLAMS：`scale 1.3 → 1` + `opacity`，`power3.out` |
| 角标 | TYPES ON：从左往右显现 |

### Transition OUT

**速度匹配上移**（CSS）：整场 `y → -160` + `blur 0 → 28px`，0.4s `power2.in`；下一场从 `y +160 / blur 28px` 升上来，0.7s `power2.out`。

### Depth layers

BG 实底 ／ MG 两块截图面板 ／ FG 大数字、chip、角标、分割线。

### SFX

面板展开时一次 whoosh；`−43.7%` 落位时一次偏亮的 tick。

---

## BEAT 4 — 落版（14.90 – 20.00）

**VO:** 让 AI，看见每一粒粮食的气候风险。

### Concept

从"系统"回到"人"。韧性路径的三段式时间轴像卷宗一样向上滚过，短、中、长三枚阶段 chip 依次亮起，最后所有面板向后退进暗处，只剩徽标、产品名和那句 tagline。全片唯一的情绪释放点。

### Visual

- **纵向卷轴**：`shots/04-pathway.png` 放在一个 1000×760 的窗口里，`y` 从 0 连续滚到 −320，露出"短期应急 → 中期建设"的两段。
- **三枚阶段 chip**：`短期应急 PERIOD 0–1`／`中期建设 PERIOD 1–3`／`长期布局`，右对齐排在卷轴右侧，依次点亮，已亮起的保持 `#C5D4AF` 描边。
- **落版（15.4s 起）**：徽标放大居中偏左，右侧 `稷韧云图` 48px 衬线，下方 `极端气候下粮食生产风险智能分析` 与 `FOOD-RISK INTELLIGENCE PLATFORM`，再下方一行 tagline。
- **底部细线**：`31 省 · 2011–2023 · 三模型互补归因` 等宽小字，随落版一起淡入。

### Camera

卷轴阶段：垂直方向上移。落版阶段：整体 `scale 1.06 → 1.0` 收拢，像镜头最后坐定。

### Animation choreography

| 元素 | 动词 |
| ---- | ---- |
| 卷轴 | SCROLLS：`y 0 → -320`，`ease none` |
| 阶段 chip | LIGHT UP：逐枚点亮，间隔 0.45s |
| 卷轴 | RECEDES：`opacity → 0.18`、`scale → 0.96`（15.4s） |
| 徽标 | LANDS：`scale 0.7 → 1` + `opacity`，`expo.out` |
| 文字 | RISES：`y 26 → 0` 分段浮现 |
| tagline | GLOWS：落定后非常轻微的一次亮度脉冲 |

### Transition

最后一镜，允许整体淡出至 `#162520`（`opacity → 0`，0.5s）。

### Depth layers

BG 实底 + 单点径向光（品牌绿，居中偏左，6%）／ MG 卷轴 ／ FG 落版文字。

### SFX

卷轴滚动时低频 whoosh；徽标落定时一次干净的 tick，之后底噪渐弱收尾。

---

## Production Architecture

```
promo-video/
├── index.html                    root — 旁白 + 音床 + SFX + 四个 beat 的编排
├── DESIGN.md                     brand reference
├── SCRIPT.md                     旁白文本
├── STORYBOARD.md                 THIS FILE
├── narration.wav / narration.txt / transcript.json / beat-timing.json
├── underscore.wav / sfx-tick.wav / sfx-whoosh.wav
├── capture/                      站点抓取产物
├── shots/                        7 个路由的 2x 截图
├── assets/
│   ├── map/china-risk.svg        beat 1 的地图（脚本生成）
│   ├── map/risk-baseline.json    与页面逐项核对过的风险值
│   ├── fonts/*-subset.woff2      子集化后的三套字体（本地，不依赖外网）
│   └── vendor/gsap.min.js        本地 GSAP
├── compositions/
│   ├── beat-1-risk-map.html      0.00 – 6.14
│   ├── beat-2-product.html       5.74 – 10.62
│   ├── beat-3-proof.html        10.27 – 15.25
│   └── beat-4-outro.html        14.90 – 20.00
└── tools/                        截图、建图、拼音频、字体本地化的脚本
```

---

## Post-build Notes（成片时的实际口径）

### 转场怎么实现的

四个 beat 是四个子组合，挂在 index.html 的 `scene-1..4` 上，**相邻 beat 交叠 0.40s**：

| 场景 | host 区间 | 本地时长 | 退场动作 |
| ---- | --------- | -------- | -------- |
| beat-1 | 0.00 – 6.14 | 6.14 | zoom through（scale→1.18 + blur 22px） |
| beat-2 | 5.74 – 10.62 | 4.88 | 竖直数据擦除（clip-path 收成中线） |
| beat-3 | 10.27 – 15.25 | 4.98 | 速度匹配上移（y→−160 + blur 28px） |
| beat-4 | 14.90 – 20.00 | 5.10 | 全片唯一允许的整体淡出 |

交叠的两个 beat 必须落在不同 `data-track-index`（1/2 交替），层级由 inline `z-index` 决定。
每个 beat 的 `.backdrop` 入场淡入、退场淡出，否则交叠区会出现硬边。

### 数字口径

地图与 Top10 用的是 `frontend/src/data/mockProvinces.ts` 的 `PROVINCES_BASE`。
原因：`/api/provinces` 的 grain.db 行不含 `y` 字段，store 的 `normalizeRow()` 会回落到 baseline，
所以页面（含 2023 年）实际显示的就是这组值。已用 headless 浏览器抓 `/risk-map` 的真实 DOM 逐项核对：
青海 0.0400 / 西藏 0.0380 / 新疆 0.0360 / 甘肃 0.0340 / 内蒙古 0.0330 / 宁夏 0.0320 /
陕西 0.0290 / 山西 0.0280 / 云南 0.0270 / 广西 0.0270，与画面完全一致。
**没有自造年度数据**——站点地图不随年份变色，视频也不变。

### 字体与动画库本地化（必须保留）

`validate` 期间出现过 `net::ERR_CONNECTION_CLOSED` 导致 `gsap is not defined`、字体回退。
现在 GSAP 走 `assets/vendor/gsap.min.js`；字体是 `tools/build-fonts-local.py` 子集化的三个 woff2
（Noto Sans SC / Noto Serif SC / JetBrains Mono，共 0.54MB），`@font-face` 内联在每个 composition 里。
改字体后需要重跑：`python tools/build-fonts-local.py` → `node tools/apply-fonts.mjs`。

> 走过的弯路：一开始把 Google Fonts 的 208 个 unicode-range 分片（970KB CSS）内联进每个 composition，
> 渲染器直接报 `Invalid array length` 并导航超时。子集化只保留片子里出现的 771 个字符才是正解。

### 渲染环境（这台机器上的三个坑）

`npx hyperframes render` 裸跑会连挂三次。别记命令，直接用 `tools/render-20s.ps1`：

| 坑 | 现象 | 绕法 |
| --- | ---- | ---- |
| 自带的 chrome-headless-shell | 下载/解压失败 → `Chrome not found` | `HYPERFRAMES_BROWSER_PATH` 指向系统 Chrome |
| PATH 上的 ffmpeg | hermes-agent venv 那个旧版缺 `adelay`，混音直接失败；`D:\DC\tools\ffmpeg\ffmpeg.exe`（顶层那个）缺 libx264，编码报 `Unrecognized option 'crf'`，它的 ffprobe 也是残的，最后一步 `audioPadTrim` 照样失败 | `HYPERFRAMES_FFMPEG_PATH` 指向 `D:\DC\tools\ffmpeg\bin\ffmpeg.exe`（完整版，adelay + libx264 + ffprobe 都在） |
| C 盘只剩 0.15GB | `Low disk space` 拒绝渲染 | `TEMP`／`TMP` 改到 D 盘 |

成片：`renders/DC-promo-20s.mp4` — 1920×1080 / 30fps / 20.00s / H.264 High（7.9 Mbps）+ AAC 48kHz。
实测音频 mean −18.8 dB、max −1.5 dB，未削顶。

### 验收结果

- `npx hyperframes check` → Layout 0 error / 0 warning（5 条 info 均为设计内的溢出与交叠）
- Motion 0 error ／ Contrast **137/137 项全部通过 WCAG AA**
- 视觉抽查：`snapshots/` 下 1.2 / 3.0 / 5.2 / 7.0 / 9.2 / 11.2 / 13.2 / 16.0 / 18.6 / 19.4s 十帧逐帧看过

### 已知取舍

- beat 1 的地图用站点自己的省界 GeoJSON 渲染成 SVG（自西向东扫开），**不是**逐省点亮——
  逐省点亮需要把 200KB 路径内联进 composition，得不偿失。
- beat 2 的右栏（三模型三角）在 6.5–7.5s 之间有一小段留白，等三角落位后才填满。
- `INFERENCE < 2s` 取自站点 M03 快速入口卡上写明的「反事实预测推理 < 2s」，不是实测值。
