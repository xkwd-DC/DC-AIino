---
theme: seriph
title: 稷韧云图 · CRAIC 2026 答辩
titleTemplate: '%s'
lineNumbers: false
aspectRatio: 16/9
canvasWidth: 1280
transition: fade-out
mdc: true
routerMode: hash
fonts:
  sans: Noto Sans SC
  serif: Noto Serif SC
class: text-left
background: '#0e130e'
---

<div class="cover">

<div class="eyebrow">CRAIC · 2026 · 第二十八届中国机器人及人工智能创新大赛 · 人工智能创新比赛</div>

# 稷韧云图

<div class="subtitle">基于多模态的极端气候下我国粮食生产风险<br>核心因子识别与韧性提升可视化系统</div>

<div class="tagline">AI · 多模态 · 可解释 · 决策支持 —— 让 AI 看见每一粒粮食的气候风险</div>

<div class="meta">
潘妙齐 · 熊鑫 · 常宇璇　|　指导教师：徐苗 / 邱东芳　|　2026.05
</div>

</div>

<!--
[0:00–0:20 · 开场 20s]
各位评委老师好,我们的项目是「稷韧云图」——一个面向极端气候下粮食生产风险的、可解释的智能决策支持系统。
一句话:让 AI 看见每一粒粮食的气候风险。
-->

---
class: problem
---

# 为什么做这件事

<div class="cols2">
  <div class="colbox">
    <div class="col-head amber">现实痛点 · 气候在加剧</div>
    <div class="li"><b>2023 京津冀「23·7」暴雨</b> → 河北 24 万公顷农田受灾,玉米损失 <b>22 万吨</b></div>
    <div class="li"><b>2023 全国均温 10.7℃</b>,创 1961 年来新高,<b>13 省</b>破历史高温纪录</div>
    <div class="li">长江高温干旱、西南「旱涝急转」频发;IPCC AR6 警示农业脆弱性持续加剧</div>
  </div>
  <div class="colbox">
    <div class="col-head">三大研究瓶颈</div>
    <div class="gap"><b>Data Gap</b> · 依赖单一统计数据,缺多模态融合</div>
    <div class="gap"><b>Method Gap</b> · 模型「黑箱化」,缺多模型互补归因</div>
    <div class="gap"><b>Application Gap</b> · 停留在论文层面,缺面向决策者的工具</div>
  </div>
</div>

<div class="band">政策牵引:党的二十大 ·「十四五」规划 · 历年中央一号文件 → 「夯实粮食安全根基」</div>

<!--
[0:20–1:10 · 背景与问题 50s]
气候极端化已经在真实地冲击我国粮食生产——2023 年河北暴雨、全国创纪录高温就是最近的例子。
但现有研究有三大瓶颈:数据单一、模型黑箱、难以落地。我们就从这三层系统性破题。
-->

---
class: answer
---

# 我们的答案：Data × Method × Application 端到端闭环

<div class="dma">
  <div class="dma-card">
    <div class="n">01</div>
    <div class="t">数据 DATA</div>
    <div class="d">融合统计 + MODIS 遥感 + 气象 + GIS 四类异构数据<br><b>31 省 · 2011–2023 · 403 样本 · 27 维</b></div>
  </div>
  <div class="arrow">→</div>
  <div class="dma-card">
    <div class="n">02</div>
    <div class="t">方法 METHOD</div>
    <div class="d">XGBoost-SHAP × Attention-LSTM<br><b>双引擎互补归因</b> · 非线性归因 + 时序响应</div>
  </div>
  <div class="arrow">→</div>
  <div class="dma-card accent">
    <div class="n">03</div>
    <div class="t">应用 APPLICATION</div>
    <div class="d">Vue + Flask 可视化决策系统<br><b>四大模块 · 在线交互 · 单次推理 ≤ 2s</b></div>
  </div>
</div>

<div class="hook">破解传统研究「数据单一 · 黑箱模型 · 难以落地」三大瓶颈 —— 一条贯通「识别 → 归因 → 评估 → 决策」的完整链路</div>

<!--
[1:10–1:55 · 总体思路 45s]
我们的整体思路是一条端到端闭环:从四类异构数据出发,经双引擎方法互补归因,最终落到一个能在线交互、单次推理两秒内的决策系统。
下面分别讲方法和系统。
-->

---
class: route
---

# 总体技术路线

<div class="pipe">
  <div class="stage"><div class="sh">数据采集</div><div class="si">国家统计局 · CMDC 气象<br>MODIS 遥感 · GIS 矢量</div></div>
  <div class="ar">→</div>
  <div class="stage"><div class="sh">数据预处理</div><div class="si">缺失值补齐 · Butterworth<br>时空对齐 · Z-score</div></div>
  <div class="ar">→</div>
  <div class="stage hl"><div class="sh">双引擎建模</div><div class="si">XGBoost + SHAP 非线性归因<br>+ Attention-LSTM 时序验证</div></div>
  <div class="ar">→</div>
  <div class="stage acc"><div class="sh">系统集成</div><div class="si">Flask API + Vue 前端<br>四大模块 · 推理 ≤ 2s</div></div>
</div>

<div class="core">
核心闭环 · 两个<b>原理完全不同</b>的模型独立建模 → 双视角互补识别核心因子 → 系统化输出决策建议
</div>

<div class="ydef">
其中风险量化指标 <b>Y</b>:对粮食单产用 <b>Butterworth 低通滤波</b>分离技术进步趋势,提取气候波动的随机残差 —— 致灾维度 × 韧性维度双逻辑线并行刻画。
</div>

<!--
[1:55–2:35 · 技术路线 40s]
技术路线分四步:采集、预处理、双引擎建模、系统集成。
特别说明风险指标 Y 的构造:我们用 Butterworth 滤波把单产里的技术进步趋势剥离,留下由气候波动驱动的随机残差作为风险刻画对象,这保证了我们建模的是「气候风险」而非「逐年增产趋势」。
-->

---
class: method
---

# 方法 · 双引擎互补归因

<div class="cols2">
  <div class="engine">
    <div class="eh green">引擎 A · XGBoost + SHAP</div>
    <div class="es">数据驱动归因 · 把「黑箱」变「白箱」</div>
    <div class="li">梯度提升树拟合非线性 · 多耦合风险</div>
    <div class="li">SHAP 三维度:<b>全局 / 个体 / 交互</b></div>
    <div class="li">视角:生物量主导</div>
  </div>
  <div class="engine">
    <div class="eh amber">引擎 B · Attention-LSTM</div>
    <div class="es">时序响应归因 · 聚焦极端气候敏感时点</div>
    <div class="li">LSTM 门控 + 注意力 softmax 加权</div>
    <div class="li">对洪涝 / 干旱月权重显著放大</div>
    <div class="li">视角:灾害响应 · policy lever</div>
  </div>
</div>

<div class="xverify">✕ 双视角互补 · 两个原理不同的模型各自独立归因 →「互补而非简单一致」(Top-3 仅 1/3 重合, ρ≈0) → 决策视角更全面</div>

<!--
[2:35–3:35 · 方法核心 60s · 重点]
这是项目的方法核心。我们用了两个原理完全不同的引擎:
引擎 A 是 XGBoost + SHAP,数据驱动,把黑箱变白箱,从全局、个体、交互三个维度做可解释归因;
引擎 B 是 Attention-LSTM,深度时序模型,注意力机制自动聚焦在洪涝、干旱发生的关键月份。
两个模型独立建模、各自归因——结论互补而非简单一致(Top-3 仅 Temp 重合、Spearman ρ≈0),说明两类方法捕捉的是不同维度的信号,而非互相印证。
-->

---
class: result-acc
---

# 实验结果 · 精度 ：10 种子稳健性实验

<div class="rtable">

| 模型 | Test R² (10 seeds 均值 ± std) | RMSE (kg/ha) | 硬指标 |
|---|---|---|---|
| **XGBoost** | **0.907 ± 0.038** | 312.5 | ≥0.62 　远超 ✓ |
| **LSTM** | **0.886 ± 0.022** | 362.0 | ≥0.62 　远超 ✓ |
| **Attention-LSTM** | **0.816 ± 0.050** | 456.4 | ≥0.65 　通过 ✓ |

</div>

<div class="case">
<div class="case-t">单样本实测 · 河南省 2022</div>
<div class="case-row">
  <div class="cc"><div class="cv">4615</div><div class="cl">真实单产 kg/ha</div></div>
  <div class="cc"><div class="cv">4657.6</div><div class="cl">Att-LSTM 预测</div></div>
  <div class="cc green"><div class="cv">+42.6</div><div class="cl">误差 kg/ha</div></div>
</div>
</div>

<div class="kp">三模型 R² 全部 ≥ 0.81,全面超过申报书硬指标;河南 2022 单样本误差仅 +42.6 kg/ha —— 模型已具备落地预测能力。</div>

<!--
[3:35–4:20 · 精度结果 45s]
精度上,我们做了 10 种子稳健性实验:三个模型的 R² 全部超过 0.81,XGBoost 达到 0.907,全面、稳定地超过申报书硬指标。
在河南 2022 的单样本实测中,Attention-LSTM 的预测误差只有 42.6 公斤每公顷,说明模型已经具备真实落地的预测能力。
-->

---
class: result-attr
---

# 实验结果 · 归因:互补而非简单一致

<div class="cols2">
  <div class="topk green">
    <div class="th">引擎 A · XGBoost-SHAP Top-3</div>
    <div class="ti"><b>NDVI</b> 植被指数 · 生物量主导</div>
    <div class="ti"><b>Prec</b> 年累计降水量</div>
    <div class="ti star"><b>Temp</b> 年平均气温 ★</div>
    <div class="tv">数据驱动 · 生物量视角</div>
  </div>
  <div class="topk amber">
    <div class="th">引擎 B · Att-LSTM Attention Top-3</div>
    <div class="ti"><b>Drou_A</b> 干旱面积 · 灾害响应</div>
    <div class="ti"><b>SPEI</b> 标准化降水蒸散指数</div>
    <div class="ti star"><b>Temp</b> 年平均气温 ★</div>
    <div class="tv">灾害响应 · policy lever 视角</div>
  </div>
</div>

<div class="gain">双引擎 Top-3 <b>仅 Temp 重合</b> → 印证「数据生长状态 × 灾害政策响应」双视角　·　多模态融合消融:仅统计 0.498 → 全模态 0.565,带来 <b>4.9–6.7 pp</b> R² 增益　·　SHAP 交互:灌溉减损在高温下被部分抵消 → 需「灌溉 + 控温」综合施策</div>

<!--
[4:20–5:10 · 归因结果 50s]
归因上有个有意思的发现:两个引擎的 Top-3 因子里,只有「气温」重合。
A 看到的是 NDVI、降水这类生长状态因子;B 看到的是干旱面积、SPEI 这类灾害响应因子。
这正说明两个视角互补。消融实验也证明多模态融合带来 4.9 到 6.7 个百分点的 R² 提升;
SHAP 交互还揭示:高温会部分抵消灌溉的减损效果,所以政策上要灌溉和控温综合施策。
下面进入现场系统演示。
-->

---
layout: center
class: demo-intro
---

# 成果落地 · 可视化决策系统

<div class="modules">
  <div class="m"><div class="mc">M1</div><div class="mt">风险时空地图</div><div class="md">ECharts 中国地图 + 时间滑块<br>省域风险分布 · Top10 排行</div></div>
  <div class="m"><div class="mc">M2</div><div class="mt">SHAP 归因看板</div><div class="md">瀑布图 + 蜂群图<br>点击省份看专属归因报告</div></div>
  <div class="m"><div class="mc">M3</div><div class="mt">参数情景模拟</div><div class="md">反事实推理:灌溉+10% / 化肥−20%<br>实时风险变化曲线</div></div>
  <div class="m"><div class="mc">M4</div><div class="mt">韧性路径推荐</div><div class="md">规则引擎 + 三阶段时间线<br>短 / 中 / 长期差异化政策</div></div>
</div>

<div class="stack">Vue 3 + Flask + TensorFlow / XGBoost　·　全国 31 省　·　开放 API　·　单次推理 ≤ 2 秒</div>

<!--
[5:10–5:40 · 系统总览 30s]
这是项目的最终成果——一个可视化决策支持系统,四大模块:风险地图、SHAP 归因看板、参数情景模拟、韧性路径推荐。
后端是 Flask 加 TensorFlow、XGBoost 的真实推理,前端 Vue 3,覆盖全国 31 省,单次推理两秒内。下面现场演示。
-->

---
layout: iframe
url: /overview
class: live
---

<!--
[5:40–7:00 · 现场实机演示 80s · 全场高潮]
现在是在线运行的真实系统(顶部地址栏可见在公网可访问)。
① 概览页:31 省覆盖、403 样本、三模型 R²;
② 进 M1 风险地图,点击河南——立刻看到该省风险等级与因子;
③ 进 M2 SHAP 看板,瀑布图展示这个省的个体归因;
④ 进 M3 情景模拟,把灌溉率 +10%,实时看到风险曲线下降——这就是反事实推理;
⑤ 进 M4 韧性路径,系统按规则引擎给出短中长期差异化政策建议。
全部在线、实时、两秒内响应。
(提示:若现场网络异常,切换到下一页备用截图继续讲。)
-->

---
layout: iframe
url: /scenario
class: live
---

<!--
[备用 / 加演 · 情景模拟特写]
这一页直接定位到 M3 参数情景模拟,作为反事实推理的特写。
现场可调灌溉率、化肥用量,实时观察风险变化曲线;若上一页演示已充分,可快速带过。
-->

---
class: innovation
---

# 创新点 与 应用价值

<div class="inno-grid">
  <div class="inno"><span class="il">数据层</span>多模态异构数据融合的全国尺度风险识别框架(统计+遥感+气象+GIS)</div>
  <div class="inno"><span class="il">方法层 ①</span>可解释 ML × 注意力时序深度学习的双引擎互补归因,破解黑箱</div>
  <div class="inno"><span class="il">方法层 ②</span>SHAP 三维度归因 + 交互效应深度挖掘,揭示复杂耦合机理</div>
  <div class="inno"><span class="il">应用层</span>「多模态识别 + 可解释 AI + 决策支持」三位一体工程化落地</div>
  <div class="inno"><span class="il">贡献层</span>规范化多模态数据集与处理流程,服务后续研究复用</div>
</div>

<div class="value">
服务国家粮食安全战略　·　赋能农业保险与精准农资　·　支撑北方旱区 / 长江洪涝 / 西南旱涝急转 差异化韧性路径　·　推动可解释 AI 在农业落地
</div>

<!--
[7:00–7:40 · 创新与价值 40s]
我们的创新覆盖五个层面:数据层的全国尺度多模态融合框架、方法层的双引擎互补归因与三维 SHAP 归因、应用层的三位一体工程化落地,以及可复用数据集的贡献。
应用价值上,它能服务国家粮食安全战略、赋能农业保险、支撑区域差异化政策,是可解释 AI 在农业落地的一个示范样板。
-->

---
layout: center
class: thanks
---

<div class="end">

# 稷韧云图 · 总结

<div class="sum">
<div class="si"><b>数据</b> 构建覆盖 31 省 13 年的多模态融合数据集 paper_panel_v3</div>
<div class="si"><b>方法</b> XGBoost-SHAP × Attention-LSTM 双引擎互补归因 + 三维归因</div>
<div class="si"><b>落地</b> 端到端可视化决策系统,四大模块、推理 ≤ 2s</div>
</div>

<div class="ty">感谢徐苗老师、邱东芳老师的悉心指导,感谢学院与团队的协作支持</div>

<div class="qa">Thanks · 敬请评委批评指正　|　潘妙齐 · 熊鑫 · 常宇璇</div>

</div>

<!--
[7:40–8:00 · 总结致谢 20s]
总结一下:数据上我们构建了 31 省 13 年的多模态数据集;方法上建立了双引擎互补归因;落地上做出了完整的决策系统。
感谢两位指导老师和团队的支持,以上是我们的汇报,敬请各位评委批评指正,谢谢!
-->


---
layout: center
class: divider
---

# 备用 · 系统实机截图

<div class="eyebrow2">APPENDIX · 现场网络/隧道异常时,切换至以下静态页继续演示</div>

---
class: appx
---

<div class="shotwrap">
<div class="cap">M00 · 系统总览</div>
<img src="/deck-shots/00-overview.png" alt="系统总览" />
</div>

---
class: appx
---

<div class="shotwrap">
<div class="cap">M01 · 风险时空地图 — 31 省风险分布 + Top10 排行</div>
<img src="/deck-shots/01-risk-map.png" alt="风险时空地图" />
</div>

---
class: appx
---

<div class="shotwrap">
<div class="cap">M02 · SHAP 归因看板 — 全局重要性 + 个体带向贡献</div>
<img src="/deck-shots/02-shap.png" alt="SHAP 归因看板" />
</div>

---
class: appx
---

<div class="shotwrap">
<div class="cap">M03 · 参数情景模拟 — 反事实推理,基线 0.040 → 模拟 0.0225(↓43.7%)</div>
<img src="/deck-shots/03-scenario.png" alt="参数情景模拟" />
</div>

---
class: appx
---

<div class="shotwrap">
<div class="cap">M04 · 韧性路径推荐 — 规则引擎 + 短/中/长期政策</div>
<img src="/deck-shots/04-pathway.png" alt="韧性路径推荐" />
</div>

---
class: appx
---

<div class="shotwrap">
<div class="cap">M05 · 推演监控 — 三模型实时协同 trace</div>
<img src="/deck-shots/05-monitor.png" alt="推演监控" />
</div>
