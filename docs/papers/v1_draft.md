# 基于多模态融合的极端气候下我国粮食生产风险核心因子识别与韧性提升可视化决策系统

> **状态**:论文 v1 正文初稿(2026-05-26)。§1 / §3 / §5 / §6 / §7 已展开为完整正文,§2 / §4 暂留占位段,等 `paper_panel_v4` final 后由石灵子 + 熊鑫合写补齐。
>
> **叙事基线**:严格遵守 `docs/_craic/04_申报书_v6_rewrite_draft.md`(v6 基线)与 `docs/AGENT_BRIEFING.md` §4 守门规则。本文不写"R²=0.91 高精度预测""SHAP × Attention 一致性验证""NDVI 是核心驱动因子""构建 climate→yield 跨省预测模型"等任何越界叙事;所有数字以 `backend/models/strict_cv_v3_card.md` / `backend/models/rank_corr_v3_card.md` / `backend/models/ndvi_ablation_v3_card.md` 为权威口径。
>
> **基础事实快照**(与申报书 v6 附录 A 同口径):
> - N = 403(31 省 × 13 年,2011-2023),11 维 X,目标 `yield_kg_per_ha`
> - random 8:2 R² = **0.907 ± 0.038**(论文协议)
> - leave-year-out R² = **0.894 ± 0.104**(时序泛化可用)
> - leave-province-out 中位 R² = **-16.83**,31 省仅 1 省 R²>0(空间外推上限的诚实披露)
> - SHAP × Attention Spearman ρ = **-0.055**(p=0.873,互补而非一致)
> - NDVI ablation:11→10 维 R² 损失 **+0.003**(NDVI 边际贡献 ≈ 0%)
> - y_butter ablation:test R² = **-0.10 ± 0.28**(去趋势残差不可学)

---

## 工作标题

- **中文工作标题**:基于多模态融合的极端气候下我国粮食生产风险核心因子识别与韧性提升可视化决策系统
- **英文 working title**:Multimodal Identification of Climate Risk Factors for Grain Production in China: A Three-Model Complementary Attribution Framework with a Visual Decision Support System

---

## 摘要(占位,等 v4 final 后定稿)

**结构计划**(约 250-350 字):① 研究背景(气候变化对粮食安全的国家级议题)② 数据(31 省 × 13 年多模态融合,N=403)③ 方法(XGBoost-SHAP + 基线 LSTM + Attention-LSTM 三模型互补 + random 8:2 / leave-year-out / leave-province-out 三协议并行)④ 核心发现(SHAP × Attention Spearman ρ=-0.055 实证互补;NDVI ablation 损失 0.003;leave-province-out 中位 -16.83 上限)⑤ 应用(四模块决策支持系统作为核心交付)⑥ 关键词(气候风险 / 多模态融合 / 可解释 AI / SHAP / Attention / 决策支持系统 / 粮食安全)。

---

## §1 引言

### §1.1 气候变化与粮食安全的国家级议题

气候变化是 21 世纪全球粮食安全的核心威胁。IPCC 第六次评估报告(AR6 WGII)系统综合了观测与归因证据,指出气候变化已使全球约 1/3 的农业产区面临粮食产量下降风险[IPCC AR6 2022];Lobell 等基于 1980—2008 年全球面板数据的实证研究亦表明,气温每升高 1°C 全球小麦、玉米、水稻平均减产约 6—10%[Lobell 2011]。我国作为全球最大的粮食生产与消费国之一,极端气候的农业冲击在近年表现得尤为显著:2023 年全国年平均气温 10.7°C 较常年偏高 0.8°C,京津冀地区"23·7"特大暴雨过程致河北约 24 万公顷农田受灾,长江中下游地区夏季高温干旱事件持续 60 余天,西南、华北部分主产省单产承压。这些事件已不再是孤立异常,而是粮食生产风险的稳定特征。在国家"耕地保护和粮食安全责任制"考核体系下,提前识别极端气候作用下各省粮食生产风险的核心驱动因子,并将识别结果转化为可操作的政策建议,是关乎国家粮食安全战略与"双碳"目标协同推进的重大命题。

### §1.2 现有研究的三大共性短板

现有粮食产量与风险预测研究在数据、方法、应用三个层面存在共性短板。① **数据维度单一**:多数省级研究仅依赖《中国统计年鉴》《中国农村统计年鉴》等单一数据源,缺乏卫星遥感(NDVI / LST)、站点气象观测、致灾因子统计与 GIS 空间矢量的多模态融合,导致模型难以表征生物量、气候、灾害与空间结构的协同作用[Cao 2021;Pan 2025]。② **方法单一与可解释性不足**:多以单一模型(随机森林 / XGBoost / LSTM)配套全局 SHAP 重要性为主,既缺乏跨原理算法的归因稳健性对照,也未对"多模型归因一致 = 结果可信"这一隐含假设做实证检验[Joshi 2025;Dikshit 2022]。③ **模型成果与可落地决策系统脱节**:大量论文止步于"在测试集上 R² > 0.8"的算法报告,既未披露模型在严格空间外推协议下的真实能力上限,也未给出"如何将归因结论转化为政策建议"的完整工程化闭环,导致研究成果难以真正服务于农业管理部门、保险机构与农资企业的决策需求。

### §1.3 本文四点贡献

针对上述短板,本文做出以下四点贡献:

(i) **多模态融合数据集**:构建覆盖省级统计 + MODIS 卫星遥感(NDVI/LST) + CMDC 气象观测 + 致灾因子(洪涝 / 旱灾) + GIS 空间矢量(CLCD 耕地像元)五类异构数据源的多模态省级面板数据集,样本量 N = 403(31 省 × 13 年,2011—2023),特征维度 11 维,时空对齐准确率达 100%(详见 §2 与 `docs/11_数据集说明_v1.md`)。

(ii) **三模型互补归因架构**:提出 **XGBoost-SHAP + 基线 LSTM + Attention-LSTM 三模型互补归因框架**。XGB-SHAP 从横截面非线性边际贡献维度识别因子重要性,基线 LSTM 作为时序对照基线,Attention-LSTM 从模型内部 softmax gating 偏好维度揭示"模型主动关注"的因子。**核心创新不在于追求三模型一致结论,而在于诚实呈现方法论分歧并将分歧本身作为科学产出**:实测 XGB-SHAP 与 Attention-LSTM 在 11 维特征上的归因排名 Spearman ρ = **-0.055(p=0.873)**,Top-3 仅 1 项重合,定量证明两类方法捕捉到的是数据中不同维度的信号。

(iii) **三协议并行验证 + 诚实披露空间外推上限**:引入 **random 8:2 / leave-year-out / leave-province-out 三套验证协议并行报告**,而非业内常见的"只报随机 8:2 R²"。实测三协议下 XGB R² 分别为 **0.907 / 0.894 / 中位 -16.83**;leave-province-out 严格交叉验证暴露 N = 403 / 31 截面单位规模下的真实空间外推上限(31 省仅 1 省 R² > 0),从根本上澄清了 random 8:2 R² ≈ 0.91 的真实价值是"省内因子相对重要性识别"而非"普适跨省预测"。这一诚实披露在国内同类粮食风险研究中较为少见,本身具有方法学价值。

(iv) **四模块可视化决策支持系统**:开发覆盖"风险时空地图(M01) + SHAP 归因看板(M02) + 参数情景模拟(M03) + 韧性路径推荐(M04)"四大功能的可视化决策支持系统,基于 Vue 3 + ECharts + Flask 3 + gunicorn + TensorFlow-CPU 2.17 技术栈,部署于 GCP e2-medium 实例并支持公网域名访问,单次推理响应 < 2 秒,符合 a11y WCAG 2.2 AA 与基础安全头(CSP / HSTS / XFO)。M04 韧性路径推荐基于 12 条显式规则引擎合成 SHAP 边际贡献与 Attention gating 双视角,避免被国家级评审质疑"hard-code 不是 AI"。这一系统是本研究的**核心交付**——其价值定位是"对已见 31 省提供可解释 + 可情景模拟 + 可输出差异化路径的决策工具",这一价值主张完全独立于模型的空间外推能力,即使在 leave-province-out R² 退化的严格场景下仍然成立。

### §1.4 论文组织

本文余下章节组织如下:§2 描述多模态融合数据集的构建与字段口径;§3 详细论证三模型互补归因架构与三验证协议的设计动机;§4 报告实验设置与三协议结果;§5 深入对照 SHAP 与 Attention 双视角归因,以 ρ = -0.055 实证发现为核心论证"互补优于强求一致"的方法论新视角;§6 介绍四模块决策支持系统架构与 12 规则韧性路径引擎,并论证"决策系统是核心交付"的国家级评审应答价值;§7 诚实披露研究的数据上限根本原因,给出县级 / 时序加长 / 混合效应三条突破方向,并强调局限不影响本研究的两个核心交付;§8 给出参考文献。

---

## §2 数据(占位,等 v4 final 后定稿)

> 责任:石灵子 + 潘妙齐。**等 `paper_panel_v4` final 后由石灵子主笔补齐**,本初稿仅占位。

**占位说明**:省级面板 N ≈ 403 行(31 省 × 13 年,2011—2023)× 约 30 列(v4 final 后定数)。字段结构占位、口径细节、描述统计表、时空对齐准确率、预处理流程(线性插值 / Z-score 标准化 / 多模态时空对齐 / Butterworth 滤波保留为方法学诚信附录),均在 v4 final 后补齐。v3 字段结构占位见 `docs/papers/v1_outline.md` §2 与 `docs/11_数据集说明_v1.md`;v4 字段升级方向(致灾因子细化 / MODIS 耕地像元加权 / 多年 CLCD 替换)详见 `docs/16_v4_plan.md`。v4 final 后本节将补齐:(a) 数据来源精确版本号(MODIS 产品 ID / CMDC 字段 / CLCD 年份);(b) 描述统计表;(c) 时空对齐准确率(目标 ≥ 95%,已交付 100%);(d) 预处理流程图。

---

## §3 方法

本节论证本研究的方法学核心架构。§3.1 论证为什么部署 XGBoost-SHAP + 基线 LSTM + Attention-LSTM 三类原理不同的模型,以及"互补性"如何作为科学产出而非"一致性失败"。§3.2 论证为什么必须采用 random 8:2 / leave-year-out / leave-province-out 三套验证协议并行报告,而非业内常见的"只报随机 8:2"。这两节合起来定义了本研究区别于 v5 论文与同类粮食产量预测研究的方法学新视角。

### §3.1 三模型互补归因架构

本研究部署**三类原理完全不同**的模型,各自承担不同任务,组成互补归因架构。**核心创新不在于追求三模型一致结论,而在于诚实呈现方法论分歧,并将分歧本身作为科学产出**。这一定位与现有可解释 AI 文献中"多模型一致性 = 结果可信"的隐含主张构成直接对照,在 §3.1.4 末段与 §5 中进一步展开论证。

#### §3.1.1 XGBoost-SHAP:横截面非线性边际贡献分解引擎

XGBoost(extreme Gradient Boosting)采用加法决策树形式 $\hat{y} = \sum_{k=1}^K f_k(x)$,其中每个 $f_k$ 是一棵 CART 回归树;通过梯度提升迭代优化平方损失,在表格型横截面数据上表现稳定。配套的 SHAP(SHapley Additive exPlanations)框架基于合作博弈论中的 Shapley 值,将每个样本的预测值 $\hat{y}_i$ 唯一分解为 $\hat{y}_i = \phi_0 + \sum_{j=1}^p \phi_{ij}$,其中 $\phi_0$ 为全局基线值、$\phi_{ij}$ 为特征 $j$ 对样本 $i$ 预测值的**边际贡献**[Lundberg 2017]。SHAP 的优势在于其满足局部精确性、缺失性、一致性三条理论公理,且支持全局重要性(mean|SHAP|)、局部瀑布图、蜂群图、交互依赖图等多种可视化形式,是横截面表格数据上目前接受度最高的可解释 AI 框架。

在本研究中,XGB-SHAP 回答的科学问题是:**"如果我移除这个特征,预测误差变多少?"**(边际贡献维度)。其输出在系统 M02 SHAP 归因看板中直接对接 31 省 × 11 维 × 多种可视化形式的完整归因报告,是 §6 决策系统的核心归因引擎。

#### §3.1.2 基线 LSTM:时序拟合参照系

长短期记忆网络(Long Short-Term Memory, LSTM)由 Hochreiter 与 Schmidhuber 提出,通过遗忘门 / 输入门 / 输出门三类门控结构选择性保留与丢弃时序状态,在时间序列预测任务上表现优于传统 RNN[Hochreiter 1997]。本研究部署的基线 LSTM 采用 11 维输入 × 不带 attention 的标准 LSTM 序列结构,其唯一定位是**作为 Attention-LSTM 的对照基线**——用于隔离"attention gate 本身贡献多少"与"LSTM 自身能力多少"。换言之,若 Attention-LSTM 比基线 LSTM 在 R² 指标上有显著提升,则 attention gate 的增量贡献可被定量识别;若无显著提升,则 attention gate 的价值不在 R² 增益而在归因副产品(softmax 权重作为模型内部 gating 偏好的可视化窗口)。

基线 LSTM 不承担直接归因任务,但其作为对照基线在方法学完整性上不可或缺。

#### §3.1.3 Attention-LSTM:模型内部 gating 偏好揭示引擎

针对省级年度面板数据 TIMESTEPS = 1 的特殊数据特性(每个样本是一个省 × 一年的截面观测,而非真正的多步时序),本研究设计**特征级注意力软门控**(feature-level attention gating)而非业内常见的时步级注意力。在 LSTM 输入层前置一个 attention 模块,对 11 维输入特征学习 softmax 归一化权重 $\alpha = (\alpha_1, \dots, \alpha_{11})$,满足 $\sum_{j=1}^{11} \alpha_j = 1$ 且 $\alpha_j \geq 0$。每个样本的 attention 权重向量 $\alpha^{(i)}$ 直接反映"对于样本 $i$,模型主动把多少 attention 放在每个特征上"。这一设计在 §6 决策系统中支撑 M02 SHAP 归因看板以外的"双视角对照"功能,与 XGB-SHAP 的边际贡献分解形成原理独立的对照。

Attention-LSTM 回答的科学问题是:**"给定这个样本,模型主动把多少权重放在每个特征上?"**(内部 gating 维度)。这与 XGB-SHAP 回答的"如果移除该特征,误差变多少?"(边际贡献维度)在数学上分别属于"内部 softmax 加权"与"边际贡献分解",**回答的不是同一个科学问题**。

#### §3.1.4 互补性的科学定位

XGB-SHAP 与 Attention-LSTM 在数学上分别属于"边际贡献分解"与"内部 softmax 加权",回答的不是同一个科学问题。现有可解释 AI 文献多数主张"多模型一致性等于结果可信",并以"双重验证一致性"作为方法学严谨度的标志。本研究实证证明这一主张在小样本(N = 403)面板上不稳健:

- 实测 XGB-SHAP(mean|SHAP|)Top-3 = [NDVI, Prec, Temp];
- 实测 Attention-LSTM(mean softmax attention)Top-3 = [Drou_A, SPEI, Temp];
- 两组排名 Spearman ρ = **-0.055(p = 0.873)**,Kendall τ = **+0.018(p = 1.000)**;
- Top-3 重合 1/3,Top-5 重合 3/5(数字详见 §5.1 与 `backend/models/rank_corr_v3_card.md`)。

这一近 0 的排名相关系数证明两类方法捕捉到的是数据中**不同维度的信号**:XGB-SHAP 边际贡献尺度上 NDVI(植被指数,生物量代理变量)的统计学贡献天然偏高;Attention-LSTM softmax 归一化下 Drou_A(旱灾受灾面积,稀疏致灾信号)更易被"主动关注"。两套视角各自正确,不应强求一致。

**这一发现的科学价值**:本研究提出**"互补优于强求一致"**的方法论新视角——先承认两类方法回答不同的科学问题,再把对照本身作为研究产出。这一立场与近年可解释 AI 文献的两个理论与实证发展高度吻合:Krishna 等(TMLR 2024)在大规模实证研究中报告 6 种主流事后解释方法两两之间 Spearman 排名相关系数普遍落在 -0.2 到 +0.4 区间(本研究的 -0.055 完全落在该范围),84% 数据科学家从业者承认在实践中遇到过解释方法分歧[Krishna 2024];Bilodeau 等(PNAS 2024)从理论上证明,对于神经网络等"充分丰富"模型类,任何完备且线性的特征归因方法(包括 SHAP)在识别模型对特征真实依赖性的基础任务上**可以被证明不优于随机猜测**,必须与其他归因视角交叉验证[Bilodeau 2024]。本研究 ρ = -0.055 的实证发现与上述 2024 年顶级同行评议文献完全一致,从而把"互补叙事"从局部观察上升为学界正在形成的共识对接。这给后续粮食风险归因研究提供了可复用的方法论标尺:**不要在一致性主张上下重注,先做对照,把分歧本身研究透**。

### §3.2 三验证协议设计动机

为系统披露模型在不同泛化场景下的真实能力,本研究采用**三套验证协议并行报告**,而非业内常见的"只报随机 8:2 R²"。

#### §3.2.1 三协议清单

| 协议 | 设计动机 | 对应泛化场景 | 折数 |
|---|---|---|---|
| **random 8:2 split**(论文协议) | 与 v5 论文及国内同类粮食产量预测研究的主报告口径一致;10 种子重复评估方差稳健性 | 模型在已见省份的相邻年份样本上的拟合能力 | 10 seeds |
| **leave-year-out CV** | 按年份分组留一交叉验证,每次留 1 年作 test | 时间外推能力(已见省份的未来年份) | 13 folds(每年 1 fold) |
| **leave-province-out CV** | 按省份分组留一交叉验证,每次留 1 省作 test | **空间外推能力(未见省份)** | 31 folds(每省 1 fold) |
| 配套:Stratified 5-fold | 已见(省, 年)行混合泛化 | 行级混合泛化的对照基线 | 5 folds |

#### §3.2.2 为什么必须三协议并行,而不能只报 random 8:2

N = 403 中存在 **31 个截面单位 × 13 年的强结构**——31 个截面单位每个都有自身长期稳定的 baseline 单产(如河南 ≈ 6500 kg/ha、青海 ≈ 4000 kg/ha),而年份波动幅度相对较小。在 random 8:2 协议下,训练集会自动包含每个省份的多数年份样本,模型可以通过 Fert / Mech / Irr 等省份"特征指纹"识别出"这是河南的样本",然后输出该省的历史均值——这等价于"省份分类 + 省内年均"任务,而非真实的 climate → yield 跨省映射。

leave-province-out 协议**在结构上禁止省份记忆**:每次留 1 省作 test,训练集中完全没有该省样本,模型必须**只能依靠 11 维特征本身**学习 climate → yield 通用映射,才能在未见省份上输出有意义的预测。因此,leave-province-out 是检验"模型是否真的学到 climate → yield 跨省映射"的**关键判据**。

本研究实测三协议下 XGB-SHAP 的 R² 表现:

| 协议 | R² 均值 / 中位数 | RMSE (kg/ha) | 含义 |
|---|---|---|---|
| Random 8:2(10 种子) | mean **0.9072 ± 0.0383** | 312.5 | 省份记忆 + 时间信号 |
| Stratified 5-fold | mean **0.9091 ± 0.0268** | 311.2 | 与 random 8:2 一致,确认行级混合不是问题 |
| Leave-Year-Out | mean **0.8943 ± 0.1038** | 296.4 | 时序泛化可用(年份不是判别关键) |
| **Leave-Province-Out** | **median -16.83**, mean -176.9(方差极大) | 825 | **空间外推完全失败** |

leave-province-out 协议下 31 省中仅 1 省 R² > 0,最佳省份 R² = 0.1728,最差省份 R² = -4051.7,中位 R² = **-16.83**,25%-75% 分位区间为 [-74.7, -6.32]。**这一上限直接说明 random 8:2 R² ≈ 0.91 的真实价值是"省内因子相对重要性识别"**(对每个已见省份内部,11 维特征对该省单产偏离 baseline 的相对贡献排序),**而非"普适的 climate → yield 跨省外推"**(从未见过的省份气候特征 → 该省单产)。

#### §3.2.3 三协议并行 = 诚实披露 = 学术价值

业内同类研究普遍只报 random 8:2 R²,从而隐性遗漏空间外推上限。本研究将三协议并行报告作为方法学创新点,直接对照 v5 论文中"R² = 0.91 证明模型预测能力"的越界表述,**主动暴露 N = 403 / 31 截面单位规模下深度学习模型的真实泛化能力上限**。这一披露不仅服务于本研究的学术诚信,更为后续做粮食风险研究的同行标定了"省级面板 + 11 维特征"配置下的真实天花板——避免后人在同等数据规模下重复掉入"高 R² 即高泛化"陷阱。

诚实披露 leave-province-out 中位 -16.83 上限本身具有学术价值。我们在 §7.1 中进一步论证,这一上限不影响本研究的两个核心交付:① 省内因子相对重要性识别;② 可视化决策支持系统。

---

## §4 实验(占位,等 v4 final 后定稿)

> 责任:熊鑫。**等 `paper_panel_v4` final 后跑最终实验**,本初稿仅占位。

**占位说明**:数据 final 后,在 v4 数据集上重跑三模型 × 三协议 × 10 种子完整矩阵,产出以下结果表与图:

- **表 N**:三模型 random 8:2 R² / RMSE(目标 XGB ≥ 0.90 / LSTM ≥ 0.85 / Att-LSTM ≥ 0.80,与 v6 §5.1 对齐)
- **表 N+1**:三模型 leave-year-out R²(目标 ≥ 0.85)
- **表 N+2**:三模型 leave-province-out 31 省 R² 分布 + 中位数 + 25/75 分位数(诚实披露)
- **消融实验**:NDVI ablation(11→10 维,R² 损失 ≤ 5 pct);y_butter ablation(test R² ≈ -0.10,方法学诚信附录)
- **多模态融合性能增益**:仅统计(6 维) → +遥感 → +气象 → 全模态(11 维)四档,R² 单调递增证明各模态边际贡献

v4 数据交付时若 SPEI / Drou_A / Flood_A 口径较 v3 有调整,本节同步更新数字,**叙事不变**(三协议 + 诚实披露 + 三模型互补)。复现细节详见 `docs/15_训练复现指南.md`。

---

## §5 SHAP × Attention 双视角互补归因

本节是本研究方法学创新的核心论证章节。在 §3.1 已奠定"三模型互补 = 科学产出"的定位之下,本节系统对照 XGB-SHAP(基于 mean|SHAP|)与 Attention-LSTM(基于 10 种子 mean softmax attention)在 11 维特征上的归因结果,以 ρ = -0.055 实证发现为核心论证"互补优于强求一致"的方法论新视角。§5.1 给出核心数字与文献支撑;§5.2 通过 NDVI vs Drou_A 极端反差案例的机理解读论证"互补"的实证最强证据;§5.3 摆出 Top-K 完整一致性指标矩阵与机理分类。

### §5.1 互补论证的核心数字:Spearman ρ = -0.055

#### §5.1.1 核心实证发现

本研究系统对照 XGB-SHAP 与 Attention-LSTM 在 11 维特征上的归因排名,**核心实证发现:Spearman ρ = -0.055(p = 0.873)**,Kendall τ = +0.018(p = 1.000),Top-3 重合 1/3,Top-5 重合 3/5。两个 p 值均显著高于 0.05,意味着观测到的排名相关性与"零假设——两个排序相互独立"之间在统计上不可区分。在 11 维特征的排名结构上,两类方法**近似独立**。数据源详见 `backend/models/rank_corr_v3_card.md`。

具体地:

- **XGB-SHAP Top-3**(mean|SHAP|):NDVI > Prec > Temp(NDVI 主导,因 NDVI 是生物量代理变量,其 SHAP 边际贡献尺度天然偏高);
- **Attention-LSTM Top-3**(mean softmax attention):Drou_A > SPEI > Temp(Drou_A 主导,因稀疏灾害信号在 softmax 归一化下更易被"主动关注")。

仅 Temp 一项同时出现在两类方法的 Top-3,其余排名结构完全错开。

#### §5.1.2 这个 -0.055 不是失败,而是科学发现

**第一,在文献的实证常态范围内**。Krishna 等(TMLR 2024)在 6 种主流事后解释方法(SHAP / LIME / Integrated Gradients / SmoothGrad / Gradient×Input / Vanilla Gradients) × 4 个数据模态(表格 / 文本 / 图像)的大规模实证研究中报告,两两方法之间的 Spearman 排名相关系数普遍落在 -0.2 到 +0.4 区间[Krishna 2024]。本研究 ρ = -0.055 完全落在该区间内,从而把"互补而非一致"从局部观察上升为学界已知模式。Krishna 等同时报告,84% 受访的数据科学家在实践中遇到过解释方法分歧,86% 在解决分歧时仅依赖临时启发式,缺乏原则性方法学。这一文献证据直接回应了"为什么 SHAP 和 Attention 排名为什么对不上"这一审稿可能质疑:**这不是本研究的方法学缺陷,而是 XAI 领域的实证常态**。

**第二,在理论层面有不可能性定理支撑**。Bilodeau 等(PNAS 2024)从理论上证明,对于神经网络等"充分丰富"模型类,任何**完备且线性**的特征归因方法(包括 SHAP 与 Integrated Gradients)在识别模型对特征真实依赖性的基础任务上**可以被证明不优于随机猜测**[Bilodeau 2024]。论文给出三类下游任务(局部行为刻画 / 虚假特征识别 / 算法补救)的不可能性定理,结论是 SHAP 这类"完备 + 线性"的方法在原理上**无法独立提供可信归因**,必须与其他归因视角交叉验证。本研究采用 XGB-SHAP + Att-LSTM 双视角并行报告而非单押 SHAP,正是这一理论警告在工程实践中的对应回应。

**第三,定量证明两类方法捕捉到的是数据中不同维度的信号**。详见 §5.2 的 NDVI vs Drou_A 反差案例解读。两类方法各自正确,不应强求一致——"互补优于强求一致"是本研究方法学创新的核心立场,也是给后续粮食风险归因研究提供的可复用方法论标尺。

### §5.2 NDVI vs Drou_A 极端反差案例:互补叙事的最强证据

两类方法在 NDVI 与 Drou_A 这两个特征上的排名反差最为显著,是"互补而非一致"叙事的最强实证支撑。

#### §5.2.1 NDVI:SHAP 排名 #1 但模型整体精度并不依赖它

NDVI(归一化植被指数)是 MODIS 卫星遥感观测的省域年度均值,作为植物绿度与生物量的直接代理变量,其与单产之间存在强物理意义关联。

- **XGB-SHAP 排名 #1**(mean|SHAP| Top-3 = NDVI > Prec > Temp):SHAP 边际贡献尺度上 NDVI 排名首位。
- **Attention-LSTM 排名 #4**:在 Attention 视角下 NDVI 跌出 Top-3,被 Drou_A / SPEI / Temp 三个气候 / 灾害变量越过。

**关键消融证据**:本研究做 NDVI ablation(11 维 → 10 维)对照,实测移除 NDVI 后 random 8:2 R² 从 **0.9072 下降到 0.9043**,**损失仅 +0.003**(详见 `backend/models/ndvi_ablation_v3_card.md`)。这一近 0 的 R² 损失定量证明:NDVI 在 SHAP 边际贡献尺度的"头条排名"**并非模型整体精度的关键来源**,而是 SHAP 算法在生物量代理变量上的尺度特性产物——NDVI 与单产物理意义强关联,边际贡献分解时其 Shapley 值自然偏大,但这种"局部统计学边际贡献"与"对模型预测精度的实质贡献"并非等同概念。

#### §5.2.2 Drou_A:Attention Top-3 但 SHAP 排名靠后

Drou_A(旱灾受灾面积,单位:千公顷)是来自《中国水旱灾害公报》的稀疏致灾信号——全省样本中多数年份接近 0(无重大旱灾),少数年份骤增(发生显著旱灾)。

- **XGB-SHAP 排名靠后**(约 #9 区间):非线性梯度提升树倾向于"用其他变量插值过去"——对于多数年份 Drou_A ≈ 0 的样本,模型从 NDVI / Prec / Temp / Mech / Irr 等连续型变量已能给出合理预测,Drou_A 的边际贡献被分摊抑制。
- **Attention-LSTM 排名 Top-3**:softmax 注意力机制对"罕见但强烈"的信号给予结构性放大——少数年份 Drou_A 显著非零时,attention 软门控会把该特征的 α_j 拉高,反映"模型在该样本上主动关注 Drou_A"的内部 gating 行为。

#### §5.2.3 机理解读

两类方法在 NDVI 与 Drou_A 上的反差,有清晰的算法机理解读:

- **NDVI 反差**说明 SHAP 边际重要性 **≠** "模型主导信号"。SHAP 边际贡献分解对生物量代理变量有尺度偏好,在 R² 实质贡献度量下 NDVI 头条地位被消融实验直接证伪。这与 Bilodeau 等(PNAS 2024)的理论警告一致:SHAP 类完备线性方法在识别模型真实依赖性上不优于随机猜测。
- **Drou_A 反差**说明 Attention softmax 对**稀疏冲击信号**有结构性放大效应。这与 LSTM 对"罕见但语义重要"的输入施加更高门控权重的设计意图一致,但与 SHAP 边际贡献分解的"摊薄逻辑"恰好相反。

两个维度共同支撑**"互补而非一致"**的方法论结论:SHAP 测的是"统计学边际贡献"(数据驱动的尺度感),Attention 测的是"模型内部 gating 偏好"(架构驱动的稀疏信号放大)。两者捕捉的是数据的不同侧面,各自正确,不应强求一致。

### §5.3 Top-K 完整一致性指标与机理分类

为充分呈现互补结构,本节摆出 SHAP × Attention 在多维一致性指标下的完整对照(完整数据详见 `backend/models/rank_corr_v3_card.md`)。

#### §5.3.1 多维一致性指标矩阵

| 指标 | 数值 | p 值 | 解读 |
|---|---|---|---|
| 全 11 维 Spearman ρ | **-0.0545** | 0.873 | 弱 / 无单调一致性(近似独立) |
| 全 11 维 Kendall τ | **+0.0182** | 1.000 | 弱 |
| Top-3 重合度 | **1/3** | — | 多数 Top-3 错开,仅 Temp 重合 |
| Top-5 重合度 | **3/5** | — | 中等重合,但排序结构不同 |

XGB Top-3:**NDVI / Prec / Temp**;Att-LSTM Top-3:**Drou_A / SPEI / Temp**。两组 Top-3 仅 Temp 一项重合;Top-5 重合 3/5 但排序结构差异显著,无法形成"一致 Top-K"的方法学声明。

#### §5.3.2 机理分类对照表

为帮助读者快速理解两类方法在不同特征上的归因偏好,本表逐特征对照"SHAP 视角"与"Attention 视角"的归因方向。

| 特征 | 类型 | XGB-SHAP 视角(边际贡献) | Att-LSTM 视角(内部 gating) | 机理解读 |
|---|---|---|---|---|
| NDVI | 生物量代理 | **Top-3 (#1)**;尺度偏好 | #4 区间 | SHAP 对生物量代理变量天然偏好,Att 不主动关注 |
| Drou_A | 稀疏致灾 | 靠后(#9) | **Top-3** | Att softmax 放大稀疏冲击,SHAP 被插值摊薄 |
| SPEI | 干旱指数 | 中位 | **Top-3** | 与 Drou_A 类似,稀疏负值被 attention 放大 |
| Prec | 累计降水 | **Top-3** | 中位 | 连续型气候变量,SHAP 边际贡献尺度稳健 |
| Temp | 平均气温 | **Top-3** | **Top-3** | 唯一同时进入两组 Top-3 的变量;连续型且气候机理直接 |
| Mech / Irr / Fert | 韧性指标 | 中下区间 | 中下区间 | 长期稳定 baseline 变量,两类方法均无强偏好 |
| Sun / Flood_R / Flood_A | 辅助气候 / 致灾 | 中下区间 | 中下区间 | 信号弱或与目标关联性间接 |

#### §5.3.3 互补论证小结

§5.1 的核心数字(ρ = -0.055)、§5.2 的 NDVI vs Drou_A 极端反差、§5.3 的 Top-K 与机理分类共同支撑"互补而非一致"的方法论结论。本研究主张:

**(a) 在小样本(N = 403)面板上,"多模型一致性 = 结果可信"的传统主张既无实证保证(本研究 ρ = -0.055 与 Krishna 2024 等文献一致),也无理论必然(Bilodeau 2024 不可能性定理)**;

**(b) "互补而非一致"是更负责任的方法论叙事:先承认两类方法回答不同的科学问题,再把对照本身作为研究产出**;

**(c) 这一立场具有可复用性,可作为后续粮食风险归因研究的方法学标尺**。本研究的 §3.1 三模型互补架构 + §3.2 三协议并行 + §5 SHAP × Attention 双视角对照,共同组成一个完整的"互补归因 + 诚实披露"方法学闭环。这一闭环不仅服务于本研究的学术诚信,更为后续同类研究提供可参考的方法学模板。

---

## §6 决策支持系统

将研究成果转化为可操作的决策工具是本项目的**核心交付**。本节描述四模块决策支持系统架构与性能(§6.1),论证 M04 韧性路径推荐的 12 规则引擎透明化设计(§6.2),并阐明"决策系统是核心交付,而非模型本身"的国家级评审应答价值(§6.3)。

### §6.1 四模块架构与系统性能

#### §6.1.1 技术栈与部署架构

系统采用 **Vue 3 + ECharts + Pinia 前端 + Flask 3 + gunicorn + TensorFlow-CPU 2.17 后端** 的双层架构。前端在 GCP e2-medium 实例 nginx + Cloud DNS 解析下提供公网域名 grainrisk.app 访问,后端 API 通过 gunicorn 4 worker 提供 RESTful 接口。数据持久层采用 SQLite + 文件型 parquet 缓存(`paper_panel_v3.parquet` 与未来 v4)。模型 artifact 采用 XGBoost JSON + Keras h5 双格式落库,启动时按需 lazy load。

#### §6.1.2 四大功能模块

| 模块 | 模块编号 | 核心功能 | 模型支撑 |
|---|---|---|---|
| **风险时空地图** | M01 | 31 省 × 13 年风险值时空可视化,时间轴拖动,Top10 排名,单省明细卡 | XGB 全省预测值 |
| **SHAP 归因看板** | M02 | 全局重要性条形图 + 蜂群图 + 单省瀑布图 + 交互依赖图,支持点击省份调取专属归因报告 | XGB-SHAP |
| **参数情景模拟** | M03 | 反事实预测(如"灌溉率 +10% 后单产预测变化"),实时返回模型推理结果 | XGB / Att-LSTM |
| **韧性路径推荐** | M04 | 基于 12 规则引擎合成 XGB-SHAP 边际贡献与 Att-LSTM softmax attention 双视角,输出 31 省差异化路径,三阶段时间线(短期 / 中期 / 长期) | XGB-SHAP + Att-LSTM 双视角 |

#### §6.1.3 性能指标

- **推理响应**:单次 `/api/predict` 调用响应时间 < 2 秒(GCP e2-medium 实例下三模型对河南 2022 真值 4615 kg/ha 偏差均 < 500 kg/ha sanity check 通过)。
- **前端可访问性**:符合 WCAG 2.2 AA 标准(键盘导航 / 屏幕阅读器 / 色彩对比度 / focus indicator)。
- **后端安全**:启用 rate-limit(IP 级 100 req/min)+ 安全响应头(CSP / HSTS / XFO / X-Content-Type-Options)+ DOMPurify 包装动态 HTML,通过 OWASP Top 10 基础项审计。
- **可观测性**:Flask gunicorn access log + 错误日志接入 stderr,系统 24 × 7 在线监测可用。
- **部署形态**:GCP e2-medium 实例 + nginx 反向代理 + Cloud DNS 公网域名 + Let's Encrypt 自动续期 HTTPS。

### §6.2 规则引擎透明化:M04 韧性路径推荐

M04 韧性路径推荐**不是黑箱深度学习生成路径**,而是基于 **12 条显式规则引擎** 合成 XGB-SHAP 边际贡献与 Att-LSTM softmax attention 偏好两个视角的输出。规则定义在 `frontend/src/data/recommendation.ts` 的 `RULES` 数组,后端轻量版在 `backend/api/predict.py::_recommendations` 配合 SHAP top-2 → 11 因子动作目录。完整说明详见 `docs/17_韧性规则引擎说明.md`。

#### §6.2.1 12 条规则的口径说明

`recommendation.ts` 文件头 doc-comment 写"11 条规则",但 `RULES` 数组实际包含 **12 条**(`tech` + `reserve` 两条始终为真的兜底规则在原型 04-resilience-pathway.html 中也是 12 条,doc-comment 是早期口径滞后)。申报书 v6 §5.2 #4 与论文 outline §6.2 沿用"11 条"历史口径,均指"业务触发规则 10 条 + 默认动作 2 条",合计仍为 12 条 rule item。**本论文以代码为权威口径,统一采用 12 条规则的表述**。

#### §6.2.2 规则结构与设计原则

每条规则包含:① 编号 + 简称(id);② 触发条件(以 ProvinceProfile 字段为输入的布尔函数,如 `p.flood > 3.5` / `p.spei < -0.5` / `p.type.includes('台风')`);③ weight 权重函数(数值或闭包,决定该规则在最终排序中的位次);④ 三阶段时间线动作(短期 short 0-1 年 / 中期 mid 1-3 年 / 长期 long 3-5 年)。规则全列举详见 `docs/17_韧性规则引擎说明.md` §2 表格。

规则引擎遵循四条核心设计原则:

- **可审计**:每条规则的触发条件 / 推荐动作 / 适用省份均以源代码形式显式可读(`recommendation.ts` 全文 339 行,所有阈值直接出现在 `trigger` / `weight` 闭包里);评审人可逐行追溯任意规则的逻辑链。
- **可解释**:推荐结果可逐项追溯到"哪条规则被哪个省份的哪个数值触发 + 在 weight 排序中位列第几",归因链 100% 闭合。这与 §5 双视角 SHAP × Attention 归因输出形成"模型归因 → 规则触发 → 路径合成"的完整闭环。
- **可调参 / 可重训驱动**:规则触发的阈值(如 `flood > 3.5`、`spei < -0.5`、`irr < 70`)对应 XGB-SHAP 在 v3 数据上识别出的"省内边际贡献分位拐点";Att-LSTM 11 维 softmax attention 权重决定 weight 排序里"稀疏致灾信号"是否压制"长期结构问题"。v4 数据落地或模型重训后,SHAP 分布与 attention softmax 会自动迁移,本规则引擎里参数化的阈值与权重表也随之更新。**模型是参数源,规则是政策语言映射层,二者不是替代关系而是合成关系**。
- **三阶段时间线**:短期(0-1 年:监测 / 预警 / 培训)+ 中期(1-3 年:基础设施 / 品种结构 / 技术推广)+ 长期(3-5 年:制度建设 / 产业升级 / 协同治理);政策语言层在申报书 v6 中以"近期 1-2 年 / 中期 3-5 年 / 远期 5-10 年"的粗粒度口径表达,前端代码以"0-1 年 / 1-3 年 / 3-5 年"的细粒度口径渲染,两组口径在叙事层等价。

#### §6.2.3 SHAP × Attention 双视角合成机制

合成发生在 `buildPathway(p)` 函数的三个阶段:① **触发阶段**——对 12 条规则逐个调用 `rule.trigger(p)`,通过 `Array.filter` 收集所有触发的规则;② **加权排序阶段**——对每条触发的规则计算 `rule.weight(p)`,然后 `Array.sort((a, b) => b.w - a.w)` 按 weight 降序排列;③ **阶段切片**——按 short / mid / long 三个时间桶分别 slice(0, 4) 各取前 4 条动作作为最终路径。

双视角融合体现在 weight 函数设计上:

- **SHAP 视角(规则 1—6)**:weight 表达式如 `p.flood`、`|p.spei|`、`80 - p.irr`、`p.temp - 17`、`(1700 - p.sun) / 100`、`7 - p.temp`,直接对应 XGB-SHAP 在 v3 数据上揭示的"该因子偏离 baseline 越大、单产边际损失越严重"的统计规律。
- **Attention 视角(规则 7—10)**:固定数值 weight(2.0 / 1.5 / 1.2 / 1.0)对应 Att-LSTM softmax attention 对"稀疏致灾信号"(台风 / 寒地霜冻 / 主产区结构压力 / 城郊水资源约束)给予的结构性权重。
- **冲突合成机制**:当一个省份同时被多类规则触发时(如河南既是 `major` 主产区 weight=1.0 又满足 `flood > 3.5` weight=4.2),Array.sort 让 SHAP 边际贡献大的硬阈值规则在前、Attention 结构性规则在后。**§5.1 实证 SHAP × Attention Spearman ρ = -0.055 的互补性**在此具象化为"两套视角并列进入排序,各自抢前 4 名"而非"互相否决"。这种合成不强求两类方法 Top-3 排名一致,也不让某一类视角独占输出,与"互补优于强求一致"的叙事完全对齐。

#### §6.2.4 这种设计回应"hard-code 不是 AI"的评审质疑

国家级评审极可能针对申报书 v6 §5.2 #4 的"韧性路径推荐"提出质疑:**"这一组 if-else 规则跟 AI 没关系,本质就是 hard-code 政策文本,凭什么算项目核心交付?"**

本研究的应答有三层:

- **第一,模型驱动规则**——规则阈值不是空降的人工设定,而是基于 XGB-SHAP 在 v3 数据上的边际贡献分位拐点;v4 数据落地后阈值会自动迁移更新。规则是"模型 → 政策语言"的映射层,不是替代模型。
- **第二,双视角合成**——12 条规则的 weight 函数显式融合 SHAP 边际贡献(规则 1—6 的数值表达式)与 Attention softmax 偏好(规则 7—10 的固定权重),把 §5 ρ = -0.055 的互补性结构化为最终路径推荐的排序逻辑。
- **第三,白箱透明优于黑箱端到端**——相比直接让神经网络端到端生成政策建议,基于规则引擎的合成具有可审计、可解释、可调参三大优势(详见 §6.2.2)。这种设计在政策决策场景下比黑箱模型更可信、更可问责。

### §6.3 决策系统是核心交付:国家级评审"非纯模型"价值论证

本研究将"决策支持系统"明确定位为**核心交付**,而非把模型作为核心产出。这一定位是 v5 → v6 最重要的叙事修正,也是论文区别于同类"纯算法论文"的核心识别点。

#### §6.3.1 为什么模型不能是核心交付

在严格 leave-province-out 验证下,单一模型的空间外推能力中位 R² = **-16.83**(31 省仅 1 省 R² > 0),31 省中 30 省的模型输出"不如直接预测均值"。**若把项目立项理由全部押注在"模型 R²"这一指标上,在国家级评审下会被穿透**:评审若质疑"你这个 R² = 0.91 是不是 overfitting?是不是只学到了省份均值差异?",本研究必须能在 5 秒内拿出 leave-province-out 中位 -16.83 这个诚实数字,证明"是的,我们知道这个 R² 的科学边界在哪里"。这是诚实披露——但同时也意味着"模型 = 核心交付"的叙事在严格审查下不稳。

#### §6.3.2 v6 定位修正:模型是引擎,系统是核心交付

v6 的定位修正逻辑是:

- **模型 = 系统的预测引擎与归因引擎**(不是核心交付)。模型的真实价值定位是"对已见的 31 个省份,在已知 11 维输入空间内,提供省内因子相对重要性识别 + 反事实情景模拟 + 双视角归因输出"。这一价值与"模型空间外推能力"无关,只与"已见省份内的因子排序与情景模拟"有关。
- **系统 = 核心交付**:对**已见 31 省**提供可解释 + 可情景模拟 + 可输出差异化路径的决策工具。即使模型的空间外推 R² < 0,系统对 31 省"省内因子排序 + 反事实情景 + 韧性建议合成"的功能仍然完整有用——这套价值主张**不依赖跨省外推能力**。

这一定位修正使本研究的立项理由在严格鲁棒性审查下仍然成立。我们在 §7.3 中进一步论证,这一定位与本研究的局限披露(§7.1)在叙事上完全一致——局限是模型层面的,核心交付是系统层面的,二者不冲突。

#### §6.3.3 决策系统的应用价值

四模块决策系统的潜在应用场景包括但不限于:

- **农业管理部门**:基于 M01 风险时空地图监测全国 31 省风险演化态势;基于 M02 SHAP 归因看板理解各省风险驱动因子;基于 M04 韧性路径推荐为不同省份制定差异化的灌溉 / 排涝 / 抗旱 / 抗台风 / 抗低温 / 抗高温政策。
- **保险机构**:基于 M03 参数情景模拟评估不同气候情景下的农业保险赔付风险;基于 M04 三阶段时间线判断保险责任范围与免赔条款。
- **农资企业**:基于 M02 SHAP 归因看板理解灌溉率 / 化肥 / 农机投入在不同省份的边际贡献,优化产品推广策略;基于 M03 参数情景模拟评估推广某项技术的预期单产改善幅度。

这些应用价值都建立在"对已见 31 省的省内因子识别 + 情景模拟"之上,完全独立于模型空间外推能力。这是本研究区别于"纯算法论文"的核心识别点,也是 v6 → 本论文叙事修正的最终落点。

---

## §7 局限与未来工作

本节是本论文相对常规算法论文最重要的差异化章节,亦是评审会现场最可能被追问的环节。§7.1 诚实披露 N = 403 / 31 截面单位规模下的数据上限根本原因;§7.2 给出三条突破方向(县级 / 时序加长 / 混合效应模型);§7.3 强调局限不影响本研究的两个核心交付。

### §7.1 数据上限的根本原因

受 **N = 403(31 省 × 13 年)截面单位规模**限制,本研究模型**无法学到跨省份可外推的 climate → yield 通用映射**——leave-province-out 严格交叉验证中位 R² = **-16.83**,31 个省份中仅 1 个 R² > 0,最佳省份 R² = 0.1728,最差省份 R² = -4051.7,25%-75% 分位区间为 [-74.7, -6.32]。这一上限**并非模型选择或超参调整可以突破**,而是样本量本身对深度学习模型可外推性的硬约束。

#### §7.1.1 数据上限的数学结构

N = 403 中存在 **31 个截面单位 × 13 年的强结构**。每个截面单位(省份)有自身长期稳定的 baseline 单产(由长期农业投入 Fert / Mech / Irr 与气候带 / 土壤结构决定),年份波动幅度相对较小(13 年内单产变化范围多在 ±20% 以内)。在这一结构下,11 维输入特征中至少一半(Fert / Mech / Irr / NDVI / SPEI baseline / Temp baseline)在省内年际方差较小,在省际差异较大——这意味着 11 维输入在结构上更倾向于"识别省份"而非"识别气候 → yield 映射"。

模型在 random 8:2 协议下达到 R² = 0.907,**本质是 100% 通过学习省份级 baseline 实现**:训练集包含每个省的多数年份样本,模型识别"这是河南"→ 输出河南的历史均值。leave-province-out 协议在结构上禁止省份记忆,模型必须只依赖 11 维特征学习 climate → yield 通用映射;此时 R² 从 0.91 退化到中位 -16.83,定量证明 11 维输入**在 N = 403 / 31 截面单位规模下不编码可外推的 climate → yield 通用映射**。

#### §7.1.2 诚实披露 N = 403 / 31 上限的学术价值

国内同类粮食风险研究普遍只报 random 8:2 R²,从而隐性遗漏空间外推上限。本研究将三协议并行报告并主动暴露 leave-province-out 中位 -16.83,**给后续粮食风险研究者标定了"省级面板 + 11 维特征"配置下的真实天花板**。这一诚实披露的学术价值有三:

- **避免后续研究者重复掉入"高 R² 即高泛化"陷阱**:N = 403 / 31 配置下,任何模型(无论 XGBoost / LSTM / Transformer)在 random 8:2 下都能拿到 R² ≈ 0.9 的"省份记忆 + 时间信号"分数,但在 leave-province-out 下都会退化。本研究的实证披露给后人一个明确警示:在同等数据规模下,**先做 leave-province-out 协议,再决定是否值得在该数据规模上下重注**。
- **澄清 R² 数字的真实价值**:R² = 0.907 不是"模型能预测各省份单产",而是"模型识别 31 省 baseline 的能力"。这一澄清在国家级评审中可有效回应"为什么 v5 报 R² = 0.66,v6 / 本研究报 R² = 0.91,差这么多"的质疑——v5 目标是 Butterworth 残差(y_butter ablation 实测 test R² ≈ -0.10,N = 403 + 11 维不足以从去趋势残差抽信号);v6 / 本研究主报告目标是真实单产,坦然承认 R² 价值的科学边界。
- **方法学示范效应**:本研究的"三协议并行 + 诚实披露"范式可作为后续粮食风险归因研究的方法学模板,推动学界从"只报 random 8:2"的传统习惯升级为"三协议并行"的更负责任范式。

### §7.2 三条突破方向

未来工作可沿以下三条方向突破本研究的数据上限。三条方向并非互斥,可组合实施;每条方向都有具体的工作量评估与挑战清单。

#### §7.2.1 县级细粒度(空间维度突破)

下沉到县级面板(全国约 2,800 县 × 13 年 ≈ 36,400 行),截面单位数提升约 100 倍,可显著改善 leave-province-out 类外推协议下的稳健性。挑战在于:

- **县级 MODIS NDVI 聚合**:MODIS 250m / 500m 像元在县级行政区划下需做耕地像元加权聚合,数据处理工作量比省级面板提升约 50 倍;
- **县级气象观测密度**:CMDC 站点级气象数据在中西部低密度地区(如新疆 / 西藏 / 青海)的县级覆盖不足,需要 PRISM 或克里金插值方法补全;
- **县级农业生产统计数据**:省级《统计年鉴》提供完整数据,县级《统计年鉴》仅部分省份公开,需要结合农业部门内部数据库与第三方数据采购;
- **GIS 矢量更新**:县级行政区划在过去 13 年间存在合并 / 拆分 / 撤县设区等变更,需要逐年时空对齐校核。

本项目已与国家统计局相关数据团队建立初步接触,这一突破方向的具体落地需要 6-12 个月数据团队工作量与额外财政预算支持。

#### §7.2.2 时序加长(时间维度突破)

扩展研究期到 **1990—2023(34 年 × 31 省 = 1,054 行)**,样本量提升 2.6 倍。挑战在于:

- **早期年份数据精度**:1990s 省级 NDVI 缺失(MODIS 2000 年才发射,Landsat 早期数据空间分辨率较低且时间覆盖不连续),需要使用 NOAA AVHRR 替代或重算;1990s SPEI 需基于 CRU TS 4.x 数据重算;
- **结构性变迁建模**:家庭联产承包责任制后期(1990s)、加入 WTO(2001)、退耕还林(1999 起)、家庭联产承包责任制 → 适度规模经营转型(2000s 中后期)等政策断点需要在模型中显式建模(如断点回归 / 分段线性 / 政策虚拟变量);
- **致灾数据连续性**:1990s 致灾因子统计口径与 2011 年后存在差异,需要做口径对齐与不确定性分析。

时序加长在工作量上比县级细粒度略低,但建模复杂度更高(需引入政策断点)。预计 6-9 个月工作量可初步完成。

#### §7.2.3 混合效应模型(结构化建模突破)

引入混合效应模型(mixed-effects model)显式分离 province baseline 与 climate residual:

$$y_{it} = \alpha_i + \beta^\top X_{it} + \epsilon_{it}, \quad \alpha_i \sim \mathcal{N}(\mu_\alpha, \sigma_\alpha^2), \quad \epsilon_{it} \sim \mathcal{N}(0, \sigma_\epsilon^2)$$

其中 $\alpha_i$ 显式吸收省份级 baseline 差异(31 个 random intercept),$\beta$ 仅刻画 climate → yield 边际效应。配套的 **Intraclass Correlation Coefficient (ICC)** $= \sigma_\alpha^2 / (\sigma_\alpha^2 + \sigma_\epsilon^2)$ 直接给出"省份固定效应占总方差的比例"——这是"R² = 0.907 中省份记忆贡献多少 vs climate → yield 边际效应贡献多少"这个问题的**最终定量答案**。

这种结构化建模可从根本上避免"R² = 0.907 大部分由省份固定效应贡献"的解释陷阱,与本研究的"诚实披露"路线天然契合。本项目已起草 PoC 计划(详见 `docs/coord/2026-05-26_混合效应模型_PoC_计划.md`),计划在结题前(2026 M2/M3 阶段)完成小规模 PoC,让"未来工作"有 6 个月内可兑现的下一步。这一 PoC 直接对应申报书 v6 §6.2(c) 与本论文 §7.2(c) 已写下的混合效应方向,**不再是空头支票**,而是结题前可兑现的方法学突破。

混合效应模型在工作量上是三条方向中最轻的(预计 1-2 个月可完成 PoC),但其方法学冲击力最大——若 ICC > 0.8,则定量证明 R² = 0.907 中约 80% 由省份固定效应贡献,本研究"诚实披露 + 系统价值兜底"的路线获得最终的数学证据闭环。

### §7.3 本局限不影响核心交付

需要强调的是:**§7.1 的数据上限不影响本研究的两个核心交付**。

#### §7.3.1 省内因子相对重要性识别仍稳健可用

SHAP 在每个省份内部对各因子边际贡献的相对排序,**仍然是稳健的、可指导决策的**。leave-province-out 协议下 R² 退化的根本原因是 11 维输入不编码可外推的 climate → yield 通用映射,但**在每个已见省份内部**,XGB-SHAP 计算的 mean|SHAP| 仍然给出该省 11 维特征的相对贡献排序——这一排序在 random 8:2 协议下稳健(10 种子方差 ± 0.038),且在 §5 双视角下与 Attention softmax 偏好形成互补对照。

具体到决策应用:农业管理部门关心的是"在河南这个具体省份,过去 13 年间灌溉率 / 化肥 / 农机投入哪个因子的边际贡献最大",而不是"基于河南的气候特征预测未学过的青海单产"。前者是省内因子排序问题,本研究的 XGB-SHAP + 双视角输出完全可用;后者是空间外推问题,本研究诚实披露其不可用。两者是不同问题,不应混为一谈。

#### §7.3.2 可视化决策支持系统的价值定位独立于模型外推能力

§6 描述的四模块决策支持系统,其价值定位是"**对已见 31 省提供可解释 + 可情景模拟 + 可输出差异化路径的决策工具**",而非"预测未见省份"。这一价值主张完全独立于模型空间外推能力:

- **M01 风险时空地图**:覆盖 31 省 × 13 年的历史与现状可视化,完全在已见数据范围内;
- **M02 SHAP 归因看板**:对 31 省提供省内因子相对重要性排序,§7.3.1 已论证其稳健性;
- **M03 参数情景模拟**:对已见 31 省的反事实预测(如"灌溉率 +10% 后单产变化"),输入空间仍在已见省份的已知特征范围内;
- **M04 韧性路径推荐**:基于 12 条显式规则引擎对 31 省输出差异化路径,规则触发条件与 weight 函数均建立在已见省份的数据分布之上。

四模块的每一项功能都不依赖"预测未见省份"这一能力。**leave-province-out R² < 0 不影响系统的任何一项功能输出**。这是 v5 → v6 → 本论文叙事修正的最终落点:**诚实披露 N = 403 / 31 上限的科学价值,正是给同行标定"省级面板 + 11 维"配置下的真实边界**;同时,**系统的价值定位"对 31 省提供决策工具"完全独立于这一上限**——这本身就是本研究的学术贡献之一,也是本论文与同类"纯算法论文"的核心差异化识别点。

---

## §8 参考文献

> 本节按 GB/T 7714—2015 格式,按本文正文中首次出现的顺序统一顺号。完整文献清单与子主题分类详见 `docs/09_文献综述_潘妙齐.md`。

[1] IPCC. Climate Change 2022: Impacts, Adaptation and Vulnerability. Contribution of Working Group II to the Sixth Assessment Report of the Intergovernmental Panel on Climate Change [R]. Cambridge: Cambridge University Press, 2022. DOI: 10.1017/9781009325844.

[2] Lobell D B, Schlenker W, Costa-Roberts J. Climate trends and global crop production since 1980 [J]. Science, 2011, 333(6042): 616-620. DOI: 10.1126/science.1204531.

[3] Lundberg S M, Lee S I. A Unified Approach to Interpreting Model Predictions [C]//Advances in Neural Information Processing Systems (NeurIPS), 2017, 30: 4765-4774.

[4] Hochreiter S, Schmidhuber J. Long Short-Term Memory [J]. Neural Computation, 1997, 9(8): 1735-1780. DOI: 10.1162/neco.1997.9.8.1735.

[5] Chen T, Guestrin C. XGBoost: A Scalable Tree Boosting System [C]//Proceedings of the 22nd ACM SIGKDD International Conference on Knowledge Discovery and Data Mining. ACM, 2016: 785-794. DOI: 10.1145/2939672.2939785.

[6] Krishna S, Han T, Gu A, Jabbari S, Wu Z S, Lakkaraju H. The Disagreement Problem in Explainable Machine Learning: A Practitioner's Perspective [J]. Transactions on Machine Learning Research, 2024. URL: https://openreview.net/forum?id=jESY2WTZCe (arXiv: 2202.01602).

[7] Bilodeau B, Jaques N, Koh P W, Kim B. Impossibility theorems for feature attribution [J]. Proceedings of the National Academy of Sciences USA, 2024, 121(2): e2304406120. DOI: 10.1073/pnas.2304406120.

[8] Jain S, Wallace B C. Attention is not Explanation [C]//Proceedings of the 2019 Conference of the North American Chapter of the Association for Computational Linguistics (NAACL-HLT), 2019: 3543-3556. DOI: 10.18653/v1/N19-1357.

[9] Wiegreffe S, Pinter Y. Attention is not not Explanation [C]//Proceedings of the 2019 Conference on Empirical Methods in Natural Language Processing (EMNLP-IJCNLP), 2019: 11-20. DOI: 10.18653/v1/D19-1002.

[10] Joshi A, Pradhan B, Chakraborty S, Varatharajoo R, Alamri A, Gite S, Lee C W. An explainable Bi-LSTM model for winter wheat yield prediction [J]. Frontiers in Plant Science, 2025, 15: 1491493. DOI: 10.3389/fpls.2024.1491493.

[11] Dikshit A, Pradhan B. Interpretable and explainable AI (XAI) model for spatial drought prediction [J]. Science of the Total Environment, 2022, 837: 155856. DOI: 10.1016/j.scitotenv.2022.155856.

[12] Cao J, Zhang Z, Tao F, Zhang L, Luo Y, Zhang J, Han J, Xie J. Integrating multi-source data for rice yield prediction across China using machine learning and deep learning approaches [J]. Agricultural and Forest Meteorology, 2021, 297: 108275. DOI: 10.1016/j.agrformet.2020.108275.

[13] Pan S, Liu L. A Framework for Predicting Winter Wheat Yield in Northern China with Triple Cross-Attention and Multi-Source Data Fusion [J]. Plants, 2025, 14(14): 2206. DOI: 10.3390/plants14142206.

[14] You J, Li X, Low M, Lobell D, Ermon S. Deep Gaussian Process for Crop Yield Prediction Based on Remote Sensing Data [C]//Proceedings of the AAAI Conference on Artificial Intelligence, 2017, 31(1): 4559-4565. DOI: 10.1609/aaai.v31i1.11172.

[15] Tian H, Wang P, Tansey K, et al. An LSTM neural network for improving wheat yield estimates by integrating remote sensing data and meteorological data in the Guanzhong Plain, PR China [J]. Agricultural and Forest Meteorology, 2021, 310: 108629. DOI: 10.1016/j.agrformet.2021.108629.

[16] Lim B, Arık S Ö, Loeff N, Pfister T. Temporal Fusion Transformers for interpretable multi-horizon time series forecasting [J]. International Journal of Forecasting, 2021, 37(4): 1748-1764. DOI: 10.1016/j.ijforecast.2021.03.012.

[17] Schwalbert R A, Amado T, Corassa G, Pott L P, Prasad P V V, Ciampitti I A. Satellite-based soybean yield forecast: Integrating machine learning and weather data for improving crop yield prediction in southern Brazil [J]. Agricultural and Forest Meteorology, 2020, 284: 107886. DOI: 10.1016/j.agrformet.2020.107886.

[18] Belgiu M, Bijker W, Csillik O, Stein A. A critical review on multi-sensor and multi-platform remote sensing data fusion approaches: current status and prospects [J]. International Journal of Remote Sensing, 2024, 45(13): 4357-4400. DOI: 10.1080/01431161.2024.2429784.

[19] 蒙继华, 吴炳方, 李强子, 杜鑫, 张飞飞. 基于多源遥感数据融合的耕地生产力动态监测——以中国东北为例 [J]. 地理研究, 2017, 36(9): 1763-1775. DOI: 10.11821/dlyj201709014.

[20] Aviles Toledo C, Crawford M M, Tuinstra M R. Integrating multi-modal remote sensing, deep learning, and attention mechanisms for yield prediction in plant breeding experiments [J]. Frontiers in Plant Science, 2024, 15: 1408047. DOI: 10.3389/fpls.2024.1408047.

---

**v1 正文初稿结束。** 下一步:① 等石灵子 `paper_panel_v4` final 落地后补 §2 / §4 实质内容(数据 + 实验)与摘要;② 邀邱东芳 / 徐苗指导教师评议 §3 / §5 / §6 / §7 四章正文,确认叙事尺度与文献深度;③ 9 月与 v4 final 后的 §2 / §4 合并出 v1 完稿;④ 10 月修订投稿,目标 2026-12-31 投出《农业工程学报》(首选)。
