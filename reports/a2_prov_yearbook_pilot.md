# A2 省级年鉴县级播种面积 / 粮食产量 —— 探路与定价

日期：2026-10-15　　范围：10 主产省（山西已验证，其余 9 省为探路）

---

## 一句话

**A2 本质是 OCR 工程，不是解析工程。**

2018 年后，各省在线年鉴普遍把表格发布成 **JPG 图片**（河南、黑龙江都已确认为纯图片，同名 `.htm` 返回 404）。
山西保留 `.xls` 直链属于**例外**，不是通例。所以 9 省的成本不能按「找表 + 写 parser」估，
而应按「下 N 张图 + 跑 OCR + 校对」估。好消息是这条管线山西已经跑通过一次
（`scripts/sx_data/ocr_sx_sown.py` 补 2014–2017），可以直接复用。

---

## 1. 山西：已经是完成态，不是待办

原清单把山西列为「已验证路径」，实际比这更强——**数据已经在本地**：

| 资产 | 内容 |
|---|---|
| `data/interim/sx_sown/2005.csv` … `2023.csv` | 19 年，每年 115–121 县 |
| `data/interim/sx_sown_ocr/2014.csv` … `2017.csv` | 4 年 OCR 补录，115–120 县 |
| `data/interim/sx_county_sown_filled.csv` | 合并结果，2,183 行 × 4 列（`adcode, year, grain_sown_kha, grain_sown_ha`） |
| `scripts/sx_data/fetch_sx_sown.py` | 取数脚本，2005–2023 全部写在 `PLAN` 里 |
| `scripts/sx_data/ocr_sx_sown.py` | OCR 脚本 |

口径：**粮食作物播种面积**（不是「农作物总播种面积」），单位公顷。年份连续 2005–2023，
2014–2017 是官网只有 `nj2015..2018_20-1x.jpg` 扫描图时用 OCR 补的。

**两个直接影响**：

1. 原清单 B6（「山西冬小麦 2014–2017 年鉴 OCR，2–3 天」）**已经做完了**，
   钱已经在 `sx_sown_ocr/` 里花掉。B6 剩下的只有「把 10 年面板重跑显著性」那一步，
   不再有取数成本。
2. 山西的取数配方是可复用的**模板**，见下节。

山西的 URL 形态（`fetch_sx_sown.py::PLAN`）：

- 2005–2013：`http://tjj.shanxi.gov.cn/tjsj/tjnj/nj{卷年}/book/{表号}.htm`（表号逐年变：18-8 / 19-9 / 20-11）
- 2018–2023：`http://tjj.shanxi.gov.cn/tjsj/tjnj/nj{卷年}/zk/html/20-07.xls`（表号 20-10 → 20-07）
- 2014–2017：官网只有 `.jpg`，走 OCR

---

## 2. 其余 9 省的实测结果（2026-10-15）

新脚本 `scripts/data/13_probe_prov_yearbook.py`（`--province XXX` / `--list`）自动走
「索引页 → 卷次 → frameset 目录页」三层，抽出候选县级表。实测：

| 省 | 年鉴入口 | 目录可读 | 县级表形态 | 判定 |
|---|---|---|---|---|
| 河南 | `oss.henan.gov.cn/.../tjnj/{年}/zk/indexch.htm`，2014–2025 共 12 卷 | ✅ `zk/left.htm` 460 链接 | **纯 JPG**：`26-5各县(市)主要农作物播种面积` / `26-6各县(市)主要农作物产量` | 可做，需 OCR |
| 黑龙江 | `tjj.hlj.gov.cn/tjjnianjian/{年}/zk/indexch.htm`，2020–2025 | ✅ `zk/left.htm` 358 链接 | **纯 JPG**：`fu-01.jpg` 附录各县(市、区)主要指标；`11-06.jpg` 播种面积 | 可做，需 OCR；县级表在**附录**章 |
| 湖北 | `tjj.hubei.gov.cn/tjsj/sjkscx/tjnj/` | ❌ 返回 71 B | — | 年鉴页是 JS 渲染，需站内检索或换入口 |
| 河北 | `tjj.hebei.gov.cn/hbstjj/sj/sjcx/tjnj` | 37 链接，无卷次 | — | 落地页是栏目页，卷次在下一层 |
| 山东 | `http://tjj.shandong.gov.cn/`（**HTTP 可，HTTPS 403**） | 首页 231 链接，无卷次 | — | 需进「数据/统计年鉴」栏目 |
| 江苏 | `https://tj.jiangsu.gov.cn/`（**`tjj.jiangsu.gov.cn` 不存在**） | 首页 182 链接，无卷次 | — | 需站内检索 |
| 安徽 | `https://tjj.ah.gov.cn/` | 首页 73 链接，无卷次 | — | 需站内检索 |
| 吉林 | `https://tjj.jl.gov.cn/` | 首页 130 链接，无卷次 | — | 需站内检索 |
| 四川 | `https://tjj.sc.gov.cn/` | 首页 171 链接，无卷次 | — | 需站内检索 |
| 湖南 | `https://tjj.hunan.gov.cn/` | 卷页指向 `home.hunan.gov.cn/login_new/...` | — | **登录墙**：年鉴需登录，最贵的一省 |

### 四个入口坑（都实测过，别再按常识猜）

| 坑 | 症状 | 真相 |
|---|---|---|
| 湖南 TLS | Python urllib 抛 `[SSL: BAD_ECPOINT]` | 站点本身正常，**curl 取得到 200/111 KB**。脚本已内建 curl 回退 |
| 山东协议 | HTTPS 403 | **只有 HTTP 通**（http → 200/96 KB，https → 403）。且 IPv6 超时，须强制 IPv4 |
| 江苏域名 | `tjj.jiangsu.gov.cn` DNS 不存在 | 江苏统计局是 **`tj.jiangsu.gov.cn`**。按「tjj.省.gov.cn」猜会扑空 |
| 卷次误判 | 锚文本含年份的**新闻稿**被当成年鉴卷 | 判据要加 URL 形态（`tjnj` / `indexch.htm`）+ 排除「编印/出版/发行」字样 |

---

## 3. 修正后的成本模型

原清单估「先花半天拿河北或河南试一本，全铺 10 省约 5–10 天」。按实测修正：

**每省的成本 = 找表（低）+ 下图（低）+ OCR 建管线（中，一次性）+ 识别校对（高，与表数成正比）**

| 环节 | 成本 | 依据 |
|---|---|---|
| 定位县级表 | 0.5–1 小时/省 | 河南、黑龙江在 3 分钟内完成三层定位；湖北/河北/山东/江苏/安徽/吉林/四川 需站内检索，多花 1–2 小时 |
| 逐卷下图 | 数分钟/卷 | 每张表 0.6–0.8 MB，12 卷 × 2 张 ≈ 15 MB |
| OCR 管线适配 | 1 天（一次性，跨省共用） | 复用 `ocr_sx_sown.py`，山西已摊薄 |
| **识别校对** | **0.5–1 天/省** | 这是真正的大头：图片要按行切、县名要对齐、数字要人工抽检 |

**结论**：10 省 5–10 天的总量估计**站得住**，但成本结构要从「解析」改成「OCR + 校对」，
且**山西这一省的成本已经是零**（数据在本地）。湖南若登录墙破不了，要从 10 省里摘出去
或者另找来源（见下）。

---

## 4. 一条比逐省找年鉴便宜得多的路：EPS

`docs/v5_yield_collection_guide.md` 记了山西农大 EPS 数据平台（校内网 `http://www.epsnet.com.cn/`，
中国区域经济数据库），v5 的地级市产量就是从那里导的。EPS 的**县级**库同样收录
「粮食产量」「农作物播种面积」这类字段，且是机读的——如果能进校内网，**比逐省 OCR 省一个量级**。

这条没在本次实测（需要校内网环境），但优先级应当高于继续 OCR：

- 若 EPS 县级库覆盖这 10 省 → 一次性导出，A2 从「10 天 OCR」变成「1 天导出 + 对账」
- 若只覆盖部分省 → 缺口再走 OCR，能把 OCR 的省数压下来

建议在动 OCR 之前先花半天确认 EPS 的县级覆盖面。

---

## 5. 交付物

| 文件 | 内容 |
|---|---|
| `scripts/data/13_probe_prov_yearbook.py` | 三层定位器；`--province` / `--depth` / `--verbose` / `--list`；内建 curl 回退与 IPv4 强制 |
| 本报告 | 9 省实测表 + 四个入口坑 + 修正成本模型 |

复现：

```powershell
$env:PYTHONIOENCODING='utf-8'; [Console]::OutputEncoding=[System.Text.Encoding]::UTF8
cd D:\DC\DC-AIino
./.venv/Scripts/python.exe scripts/data/13_probe_prov_yearbook.py --list
./.venv/Scripts/python.exe scripts/data/13_probe_prov_yearbook.py --province henan
./.venv/Scripts/python.exe scripts/data/13_probe_prov_yearbook.py --province heilongjiang --verbose
```

---

## 6. 待确认

1. **EPS 县级库覆盖面**（见 §4）——这条决定 A2 是 10 天还是 2 天。
2. **湖南登录墙**能否用校内账号或其它镜像绕开；不行则湖南省另找来源。
3. **2023 县级粮食产量**：河南 `26-6各县(市)主要农作物产量`、黑龙江 `fu-01` 都能出 2024 卷口径，
   即 2023 数据年——这条与 A1 的诉求重合，OCR 跑通即同时解决。
