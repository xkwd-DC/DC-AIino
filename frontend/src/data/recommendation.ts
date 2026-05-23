/**
 * M04 韧性路径规则引擎。
 *
 * 11 条规则各自带 trigger + weight + (short/mid/long) action。命中后按 weight 排序，
 * 每阶段截 top 4 作为最终路径。所有规则、文案、阈值均与
 * `frontend/prototypes/04-resilience-pathway.html` § 2 RULES 一致，
 * 移植 TS + 显式类型。
 *
 * 后端 `backend/services/recommendation.py` 5/29 前会把这套规则
 * 同步翻译过去（接 `/api/recommendation/<province>`）。届时本文件可下沉为
 * fallback / 离线模式资源，view 直接走 API。
 */
import { PROVINCES_BASE, type ProvinceBase } from './mockProvinces'

export interface ProvinceProfile extends ProvinceBase {
  rank: number
  desc: string
}

export interface ActionItem {
  title: string
  desc: string // 可能含 <span class="hl"> / <span class="num"> 内嵌富文本，渲染处用 v-html
  tags: string[]
  ruleId: string
}

export interface Pathway {
  short: ActionItem[]
  mid: ActionItem[]
  long: ActionItem[]
}

interface ActionTemplate {
  title: string
  desc: string
  tags: string[]
}

interface Rule {
  id: string
  trigger: (p: ProvinceProfile) => boolean
  weight: (p: ProvinceProfile) => number
  short?: ActionTemplate
  mid?: ActionTemplate
  long?: ActionTemplate
}

const PROVINCE_DESC: Record<string, string> = {
  青海: '高海拔生态脆弱区，春旱与低温冻害并存，作物生长季短，主要承担青稞、油菜等寒地作物供给。',
  西藏: '日照充沛但灌溉基础薄弱，雅鲁藏布河谷农区受春旱影响显著，生产恢复成本高。',
  新疆: '绿洲农业典型代表，完全依赖灌溉，水资源压力大，极端干旱事件影响兵团粮食生产。',
  甘肃: '陇中半干旱区降水年际波动剧烈，旱作小麦受 SPEI 异常影响最为敏感，土壤侵蚀风险较高。',
  宁夏: '黄灌区水资源高度依赖黄河引水，节水改造已成约束粮食安全的核心议题。',
  内蒙古: '横跨干湿带，西部沙化退化加剧，东部黑土区降水变率上升，农牧交错带稳定性下降。',
  陕西: '关中平原与陕北黄土高原并存，北部春旱、南部伏旱叠加，渭河流域局地洪涝时有发生。',
  山西: '丘陵山地多、灌溉基础薄弱，春季气温回升快易引发墒情不足，小麦扬花期对温度敏感。',
  云南: '立体气候明显，坝区与山区风险差异大，春旱与夏涝交替出现，泥石流次生灾害威胁突出。',
  贵州: '岩溶地貌持水能力差，降水虽多但有效利用率低，工程性缺水问题长期存在。',
  广西: '西江流域汛期长、洪涝高发，珠江-西江经济带粮食生产受洪灾影响显著。',
  河南: '全国粮食主产区，单产风险主要来自夏季洪涝与汛期降水集中，2021 年"7·20"暴雨造成显著减产。',
  江西: '鄱阳湖流域调蓄能力波动大，梅雨期与台风期叠加，水稻双季种植受连阴雨影响明显。',
  福建: '台风登陆密集，沿海农区每年承受 4-5 次台风影响，海水倒灌威胁低海拔农田。',
  重庆: '伏旱与汛期洪涝并存，日照偏少不利水稻灌浆，三峡库区消落带农业受水位调度影响。',
  安徽: '江淮分水岭一带洪涝、干旱、连阴雨多发，小麦赤霉病和水稻稻飞虱风险叠加。',
  广东: '热带和亚热带季风气候，台风、暴雨、咸潮多重风险，珠江三角洲受咸潮上溯影响明显。',
  海南: '热带季风岛屿气候，台风暴雨频次最高，种业基地建设对气候稳定性要求极高。',
  四川: '盆地积水易、排水难，川西高原与川东盆地风险类型迥异，日照偏少影响油菜籽产量。',
  湖南: '洞庭湖区调蓄能力受围垦影响，梅雨期暴雨集中，双季稻区病虫害发生程度上升。',
  湖北: '江汉平原圩区密布，汛期内涝是主要风险源，2020 年长江流域大水后排涝能力升级仍待加强。',
  吉林: '黑土带核心区，玉米单产高但生长季短，初霜冻和春涝是主要的气候致损因子。',
  河北: '华北平原小麦-玉米轮作核心区，地下水超采严重，夏季干热风威胁灌浆期产量。',
  辽宁: '辽河平原与辽东丘陵风险结构不同，春旱秋涝时有发生，海水倒灌对辽河口农区构成压力。',
  浙江: '浙东沿海与浙西山区差异大，台风登陆频次高，丘陵地带耕地破碎化降低规模化抗灾能力。',
  山东: '黄淮海粮仓的重要支撑，设施化程度全国领先，但黄河三角洲盐碱地利用仍是核心议题。',
  江苏: '苏北与苏南地势平坦，水网密布，排涝条件相对完善，但梅雨期连阴雨与高温胁迫并存。',
  黑龙江: '全国第一商品粮基地，大豆-玉米-水稻三大作物供给重镇，初霜冻提前是单产波动的主因。',
  天津: '城郊型农业为主，水资源约束突出，海水倒灌与海平面上升对低海拔农田有长期威胁。',
  上海: '高标准农田比例全国领先，设施农业占比高，主要风险来自台风与城市化压力。',
  北京: '都市农业为主，生产规模小但科技化水平高，主要任务在于种源安全与示范基地建设。',
  台湾: '热带亚热带季风气候，台风登陆频次高，水稻为主，山地耕地破碎化。',
}

export const PROVINCES_PROFILE: ProvinceProfile[] = (() => {
  const ranked = [...PROVINCES_BASE].sort((a, b) => b.y - a.y)
  return ranked.map((p, i) => ({
    ...p,
    rank: i + 1,
    desc: PROVINCE_DESC[p.name] ?? `${p.name}：${p.type}，年均温 ${p.temp.toFixed(1)}°C，洪涝占比 ${p.flood.toFixed(1)}%。`,
  }))
})()

const RULES: Rule[] = [
  {
    id: 'flood',
    trigger: (p) => p.flood > 3.5,
    weight: (p) => p.flood,
    short: {
      title: '建立县域洪涝监测预警网络',
      desc: '依托现有 <span class="hl">气象站点 + 水文测站 + 高分卫星遥感</span> 数据，在重点县建成 <span class="num">15-20</span> 个加密监测节点，实现 <span class="num">6 小时</span> 内汛情预警，联动农业农村厅与应急管理厅响应机制。',
      tags: ['监测预警', '气象 / 应急'],
    },
    mid: {
      title: '提升排涝防洪与圩堤标准',
      desc: '系统提升主产农田的排涝标准至 <span class="num">10 年一遇</span>，重点圩堤段加固至 <span class="num">20 年一遇</span>，配套泵站电力升级。优先治理 SHAP 风险贡献最高的连片低洼区。',
      tags: ['基建', '水利 / 财政', '⚡ 优先'],
    },
    long: {
      title: '构建流域韧性治理共同体',
      desc: '推动跨省市流域协同治理机制，纳入气候适应性指标考核，与 <span class="hl">财险机构</span> 联合开发"区域天气指数保险"，形成 <span class="num">3 道</span> 防线的韧性体系。',
      tags: ['制度', '跨部门协同'],
    },
  },
  {
    id: 'irrigation',
    trigger: (p) => p.irr < 70,
    weight: (p) => 80 - p.irr,
    short: {
      title: '部署土壤墒情自动监测站',
      desc: '在主要农区按 <span class="num">每 5000 公顷 1 站</span> 密度部署土壤墒情监测站，实时上传至农业农村厅决策平台。优先覆盖 SPEI 长期偏负的乡镇。',
      tags: ['监测', '科技 / 智慧农业'],
    },
    mid: {
      title: '推进高标准农田灌溉升级',
      desc: '将灌溉率由 <span class="num">当前水平</span> 提升至 <span class="num">75%</span> 以上，优先采用 <span class="hl">滴灌、喷灌</span> 等节水形式，亩均节水 <span class="num">30-40%</span>，模型预测可降低单产风险约 <span class="num">15%</span>。',
      tags: ['基建', '节水 / 财政', '⚡ 优先'],
    },
    long: {
      title: '建立水权-水价-水量协同制度',
      desc: '探索建立县域水权交易机制，以经济杠杆引导农业用水结构优化。配套阶梯水价政策，在确保粮食安全的前提下逐步压减低效用水。',
      tags: ['制度', '水利改革'],
    },
  },
  {
    id: 'drought',
    trigger: (p) => p.spei < -0.5,
    weight: (p) => Math.abs(p.spei),
    short: {
      title: '建立 SPEI 滚动评估机制',
      desc: '联合气象与农业部门，按 <span class="num">月度</span> 更新县域 SPEI，识别连续 <span class="num">3 个月</span> 偏负的高风险区，提前启动抗旱应急储备调度。',
      tags: ['监测预警'],
    },
    mid: {
      title: '引入耐旱品种与节水栽培技术',
      desc: '在干旱压力区试点 <span class="hl">耐旱小麦、耐旱玉米</span> 品种，配套地膜覆盖、垄沟集雨等节水栽培技术，试验区单产稳定性提升约 <span class="num">12%</span>。',
      tags: ['品种 / 技术推广'],
    },
    long: {
      title: '探索可持续水资源利用模式',
      desc: '在水资源刚性约束下，推进雨水集蓄、再生水农用、人工增雨等多源水利用，长期建立 <span class="hl">"以水定产"</span> 的生产布局。',
      tags: ['战略', '资源约束'],
    },
  },
  {
    id: 'heat',
    trigger: (p) => p.temp > 18,
    weight: (p) => p.temp - 17,
    short: {
      title: '建立穗期高温预警与应急喷灌响应',
      desc: '针对水稻孕穗-抽穗期 <span class="hl">高温热害</span>，联动气象部门提前 <span class="num">72 小时</span> 预警，组织灌区"以水调温"应急响应，减少高温危害。',
      tags: ['监测预警', '应急'],
    },
    mid: {
      title: '推广耐热品种与种植结构调整',
      desc: '试验区引入 <span class="hl">中科发系列、华占系列</span> 等耐热水稻品种，推进早籼稻向中晚籼调整，延后扬花期避开极端高温窗口。',
      tags: ['品种 / 结构调整'],
    },
    long: {
      title: '建立气候适应性育种联合体',
      desc: '联合中国农科院、地方农科院、种子企业，围绕本省主推品种建立 <span class="hl">气候适应性育种</span> 共建机制，长期培育匹配 <span class="num">+2°C</span> 情景的新品种序列。',
      tags: ['研究 / 育种'],
    },
  },
  {
    id: 'low_sun',
    trigger: (p) => p.sun < 1700,
    weight: (p) => (1700 - p.sun) / 100,
    short: {
      title: '加强连阴雨季节作物长势监测',
      desc: '在连阴雨易发期（梅雨/秋绵雨），启动 <span class="num">日度</span> 长势遥感监测，识别光合受抑面积，提前进行肥料补施与病害预防。',
      tags: ['监测', '农技指导'],
    },
    mid: {
      title: '推广光合补偿型栽培管理',
      desc: '推广 <span class="hl">光合调控剂、合理密植、宽窄行</span> 等增光技术，改善冠层光分布；同时调整品种比例，引入低光照品种，提升弱光胁迫下的稳产能力。',
      tags: ['栽培技术'],
    },
  },
  {
    id: 'cold',
    trigger: (p) => p.temp < 6,
    weight: (p) => 7 - p.temp,
    short: {
      title: '建立春季低温与初霜冻预警',
      desc: '联合气象站点开展 <span class="num">逐日</span> 低温过程预报，重点针对玉米拔节期与水稻分蘖期低温冷害，组织覆盖物、烟熏等防御措施。',
      tags: ['监测预警'],
    },
    mid: {
      title: '推广耐冷早熟品种与农机匹配',
      desc: '加快 <span class="hl">活动积温 2100°C·d 以下</span> 耐冷早熟玉米/水稻品种推广；农机配套上采用大马力播种机缩短播种窗口，提升积温利用率。',
      tags: ['品种 / 农机'],
    },
  },
  {
    id: 'typhoon',
    trigger: (p) => p.type.includes('台风') || p.type.includes('热带'),
    weight: () => 2.0,
    short: {
      title: '建立台风路径与农业损失评估快响应机制',
      desc: '台风预警发布后 <span class="num">12 小时</span> 内，基于路径预报和地块矢量数据，生成县级损失评估初值，推送至农险机构启动核保流程。',
      tags: ['监测预警', '保险联动'],
    },
    mid: {
      title: '优化滨海农区作物结构与抗倒伏品种',
      desc: '在台风高发带 <span class="num">3 公里</span> 缓冲区内，推广 <span class="hl">矮秆抗倒伏</span> 品种，推进"水稻-冬种"轮作模式，降低风灾期与抽穗期重叠概率。',
      tags: ['结构调整', '品种'],
    },
    long: {
      title: '构建沿海农业保险与再保险协同体系',
      desc: '与 <span class="hl">财险机构、再保险公司</span> 共建沿海农业巨灾保险池，引入参数化保险（降水 / 风速指数），提升农户灾后恢复能力。',
      tags: ['保险 / 制度'],
    },
  },
  {
    id: 'cold_belt',
    trigger: (p) => p.type.includes('寒地'),
    weight: () => 1.5,
    short: {
      title: '黑土地保护性耕作监测',
      desc: '在主产区按 <span class="num">每 1 万亩 1 点</span> 监测黑土有机质、耕层厚度、容重等指标，识别退化风险地块，精准下达保护性耕作补贴。',
      tags: ['监测', '黑土保护'],
    },
    mid: {
      title: '完善积温利用与轮作休耕协同',
      desc: '推进玉米-大豆 <span class="hl">"一主两辅"</span> 轮作，扩大大豆面积同时利用根瘤固氮恢复地力，在低积温年份保障稳产。',
      tags: ['结构调整'],
    },
    long: {
      title: '建设"中国大粮仓"长期稳定性研究平台',
      desc: '联合农科院与高校，建设黑土区气候适应性长期定位试验，围绕 <span class="num">30-50 年</span> 周期开展土壤-作物-气候耦合研究。',
      tags: ['研究 / 长期'],
    },
  },
  {
    id: 'major',
    trigger: (p) => p.type.includes('主产区'),
    weight: () => 1.0,
    short: {
      title: '建立主产区单产稳产预警仪表盘',
      desc: '面向农业农村厅决策层，集成本系统的实时 SHAP 推理结果，形成省级 <span class="hl">"周更新"</span> 单产稳产仪表盘，作为应急储备调度依据。',
      tags: ['决策支持'],
    },
    mid: {
      title: '推进社会化服务规模化与机械化升级',
      desc: '通过农机合作社、托管服务、订单农业等方式，在主产县推动 <span class="num">综合机械化率 &gt; 85%</span>，降低劳动力短缺与极端天气下抢收抢种风险。',
      tags: ['服务 / 农机'],
    },
    long: {
      title: '建设主产区韧性农业示范带',
      desc: '联动 <span class="hl">农科院、农业农村厅、龙头企业</span> 共建省级韧性农业示范带，集成水利、品种、保险、信息服务于一体，作为全国可复制经验向同类省份输出。',
      tags: ['战略 / 示范'],
    },
  },
  {
    id: 'urban',
    trigger: (p) => p.type.includes('城郊'),
    weight: () => 1.2,
    short: {
      title: '建设都市农业气候监测示范网',
      desc: '在城郊农区构建 <span class="hl">气象-土壤-生理</span> 一体化监测示范网络，服务于设施农业、种业基地的精准管理，作为全国可视化窗口对外展示。',
      tags: ['监测 / 示范'],
    },
    mid: {
      title: '强化种业自主创新与基地保护',
      desc: '依托 <span class="hl">中国农大、农科院</span> 等科研机构，建设国家级种业创新区与南繁北育协同基地，保障粮食 <span class="num">"种源"</span> 自主可控。',
      tags: ['种业 / 战略'],
    },
    long: {
      title: '建立都市群粮食协同应急储备',
      desc: '在京津冀、长三角等都市群尺度建立粮食协同应急储备机制，跨区域调度时间 &lt; <span class="num">24 小时</span>，提升超大城市食品供应链韧性。',
      tags: ['储备 / 都市群'],
    },
  },
  {
    id: 'tech',
    trigger: () => true,
    weight: () => 0.7,
    mid: {
      title: '建设智慧农业决策中枢平台',
      desc: '集成卫星遥感、气象、土壤、农情数据，在省级农业农村厅部署 <span class="hl">"数字农业大脑"</span>，实现 <span class="num">乡镇级</span> 风险预测与精准农技推送，模型推理时延 &lt; <span class="num">2 秒</span>。',
      tags: ['数字化', '智慧农业'],
    },
    long: {
      title: '推动种业振兴与气候适应性育种',
      desc: '联合 <span class="hl">中国农科院、隆平高科等头部种企</span>，围绕本省主导作物开展 <span class="num">10 年期</span> 气候适应性育种计划，储备应对 <span class="num">+1.5°C ~ +2°C</span> 升温情景的新品种序列。',
      tags: ['育种 / 战略'],
    },
  },
  {
    id: 'reserve',
    trigger: () => true,
    weight: () => 0.5,
    long: {
      title: '优化粮食储备空间布局',
      desc: '协同 <span class="hl">国家粮食和物资储备局</span>，在跨流域、跨气候带的关键节点城市增设储备库，与本省风险结构形成对冲，提升极端事件下的省际调运效率。',
      tags: ['储备 / 战略'],
    },
  },
]

const MAX_PER_STAGE = 4

export function buildPathway(p: ProvinceProfile): Pathway {
  const triggered = RULES.filter((r) => r.trigger(p))
    .map((r) => ({ rule: r, w: r.weight(p) }))
    .sort((a, b) => b.w - a.w)

  const short: ActionItem[] = []
  const mid: ActionItem[] = []
  const long: ActionItem[] = []

  for (const { rule } of triggered) {
    if (rule.short) short.push({ ...rule.short, ruleId: rule.id })
    if (rule.mid) mid.push({ ...rule.mid, ruleId: rule.id })
    if (rule.long) long.push({ ...rule.long, ruleId: rule.id })
  }

  return {
    short: short.slice(0, MAX_PER_STAGE),
    mid: mid.slice(0, MAX_PER_STAGE),
    long: long.slice(0, MAX_PER_STAGE),
  }
}

export function estimateBudget(total: number): string {
  if (total >= 10) return '¥ 高'
  if (total >= 7) return '¥ 中'
  return '¥ 低'
}
