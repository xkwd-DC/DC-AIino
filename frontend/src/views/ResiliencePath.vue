<script setup lang="ts">
import { computed } from 'vue'
import { storeToRefs } from 'pinia'
import DOMPurify from 'dompurify'
import {
  PROVINCES_PROFILE,
  buildPathway,
  estimateBudget,
  type ActionItem,
} from '@/data/recommendation'
import { useProvinceStore } from '@/stores/useProvinceStore'
// a11y: 不同于 ECharts,本视图只用 CSS animation,prefers-reduced-motion 由全局
// global.css 媒体查询接管 (animation-duration:0.01ms)。这里仅取值用于条件渲染。
import { prefersReducedMotion } from '@/data/a11y'

// SECURITY: 所有 v-html 渲染必须经此 sanitize。
// 当前 desc 来自 recommendation.ts 内部硬编码，目前安全；
// 但 5/29 后会切换到 backend /api/recommendation/<省>（外部输入），
// 不在数据源切换时统一加 sanitize = XSS 漏洞 100% 出现。
// 防御性陷阱：今天加，未来扩展自动安全。
// 白名单只允许 <span class="hl|num"> 这两类标签 + class。
const ALLOWED_TAGS = ['span']
const ALLOWED_ATTR = ['class']
function sanitizeDesc(html: string): string {
  return DOMPurify.sanitize(html, { ALLOWED_TAGS, ALLOWED_ATTR })
}

// HIGH#8: Pinia store 共享省份选择 — ScenarioSim.vue 同步切换。
const provinceStore = useProvinceStore()
const { selectedIdx, selected } = storeToRefs(provinceStore)

const pathway = computed(() => buildPathway(selected.value))

const totalActions = computed(
  () => pathway.value.short.length + pathway.value.mid.length + pathway.value.long.length,
)

const budget = computed(() => estimateBudget(totalActions.value))

const yMean = computed(() => PROVINCES_PROFILE.reduce((s, p) => s + p.y, 0) / PROVINCES_PROFILE.length)
const irrMean = computed(() => PROVINCES_PROFILE.reduce((s, p) => s + p.irr, 0) / PROVINCES_PROFILE.length)
const floodMean = computed(() => PROVINCES_PROFILE.reduce((s, p) => s + p.flood, 0) / PROVINCES_PROFILE.length)

interface Metric {
  lbl: string
  val: string
  delta: string
  cls: 'up' | 'dn' | ''
}

const metrics = computed<Metric[]>(() => {
  const p = selected.value
  const yDelta = ((p.y - yMean.value) / yMean.value) * 100
  return [
    {
      lbl: '风险指数 Y',
      val: p.y.toFixed(3),
      delta: yDelta >= 0 ? `▲ ${yDelta.toFixed(1)}%` : `▼ ${Math.abs(yDelta).toFixed(1)}%`,
      cls: yDelta >= 0 ? 'up' : 'dn',
    },
    {
      lbl: '全国排名',
      val: `第 ${p.rank}`,
      delta: p.rank <= 10 ? '高风险区' : p.rank >= 22 ? '低风险区' : '中等风险',
      cls: p.rank <= 10 ? 'up' : p.rank >= 22 ? 'dn' : '',
    },
    {
      lbl: '灌溉率',
      val: `${p.irr.toFixed(0)}%`,
      delta: p.irr < irrMean.value ? '▼ 低于均值' : '▲ 高于均值',
      cls: p.irr < irrMean.value ? 'up' : 'dn',
    },
    {
      lbl: '洪涝占比',
      val: `${p.flood.toFixed(1)}%`,
      delta: p.flood > floodMean.value ? '▲ 高于均值' : '▼ 低于均值',
      cls: p.flood > floodMean.value ? 'up' : 'dn',
    },
  ]
})

interface StageVM {
  key: 'short' | 'mid' | 'long'
  cls: 'short' | 'mid' | 'long'
  title: string
  range: string
  sub: string[]
  items: ActionItem[]
}

const stages = computed<StageVM[]>(() => [
  {
    key: 'short',
    cls: 'short',
    title: '短期应急',
    range: '0 — 1 年',
    sub: ['监测', '预警', '培训'],
    items: pathway.value.short,
  },
  {
    key: 'mid',
    cls: 'mid',
    title: '中期建设',
    range: '1 — 3 年',
    sub: ['基础设施', '品种结构', '技术推广'],
    items: pathway.value.mid,
  },
  {
    key: 'long',
    cls: 'long',
    title: '长期战略',
    range: '3 — 5 年',
    sub: ['制度建设', '产业升级', '协同治理'],
    items: pathway.value.long,
  },
])
</script>

<template>
  <section class="page">
    <header class="page-head">
      <div class="eyebrow">M04 · RESILIENCE PATHWAY ENGINE · v2.1</div>
      <h2>韧性路径推荐</h2>
      <p class="lead">
        基于省份风险指纹（灌溉/洪涝/SPEI/温度/日照/省域类型）匹配 11 条规则，自动生成三阶段（短期 / 中期 / 长期）行动路径。
        可用于农业农村厅政策决策、农险机构产品定价、农科院课题立项、储备局空间布局等场景。
      </p>
    </header>

    <div class="grid">
      <!-- 左 sidebar -->
      <aside class="sidebar" aria-label="韧性路径侧边栏">
        <div class="card">
          <div class="card-head">
            <div>
              <div class="num">M04-A · TARGET</div>
              <h3 id="pathway-target-heading">选择省份</h3>
            </div>
          </div>
          <!-- a11y SC 1.3.1 + 4.1.2:select 显式 label 关联 -->
          <label class="sr-only" for="province-select-pathway">韧性路径目标省份选择器</label>
          <select
            id="province-select-pathway"
            v-model.number="selectedIdx"
            class="province-select"
            aria-labelledby="pathway-target-heading"
          >
            <option v-for="(p, i) in PROVINCES_PROFILE" :key="p.name" :value="i">
              {{ p.name }} · {{ p.type }}
            </option>
          </select>
        </div>

        <div class="card">
          <div class="card-head">
            <div>
              <div class="num">M04-B · PROFILE</div>
              <h3>省份风险画像</h3>
            </div>
            <span
              class="rank-tag"
              :class="selected.rank <= 10 ? 'hi' : selected.rank >= 22 ? 'lo' : 'mid'"
            >RANK #{{ selected.rank }}</span>
          </div>
          <div class="prov-name">{{ selected.name }}<span class="suffix">省</span></div>
          <div class="prov-type">{{ selected.type }}</div>
          <p class="prov-desc">{{ selected.desc }}</p>
          <div class="metrics-grid">
            <div v-for="m in metrics" :key="m.lbl" class="metric">
              <div class="lbl">{{ m.lbl }}</div>
              <div class="val">{{ m.val }}</div>
              <div class="delta" :class="m.cls">{{ m.delta }}</div>
            </div>
          </div>
        </div>

        <div class="card">
          <div class="card-head">
            <div>
              <div class="num">M04-C · AUDIENCE</div>
              <h3>面向用户</h3>
            </div>
          </div>
          <div class="audience-list">
            <div class="audience-item">
              <div class="audience-icon green">政</div>
              <div class="audience-meta">
                <div class="role">省/市农业农村厅</div>
                <div class="desc">POLICY · 决策参考</div>
              </div>
            </div>
            <div class="audience-item">
              <div class="audience-icon blue">险</div>
              <div class="audience-meta">
                <div class="role">中国人寿财险等农险机构</div>
                <div class="desc">INSURANCE · 产品定价</div>
              </div>
            </div>
            <div class="audience-item">
              <div class="audience-icon amber">研</div>
              <div class="audience-meta">
                <div class="role">农科院粮食产业研究机构</div>
                <div class="desc">RESEARCH · 课题立项</div>
              </div>
            </div>
            <div class="audience-item">
              <div class="audience-icon purple">储</div>
              <div class="audience-meta">
                <div class="role">国家粮食和物资储备局</div>
                <div class="desc">RESERVE · 储备布局</div>
              </div>
            </div>
          </div>
        </div>
      </aside>

      <!-- 右 timeline -->
      <section class="timeline-wrap">
        <div class="timeline-meta">
          <span class="label">M04-D · PATHWAY</span>
          <div class="stats">
            <span>路径长度 <span class="v">{{ totalActions }}</span> 项</span>
            <span>预算量级 <span class="v">{{ budget }}</span></span>
            <span>覆盖年限 <span class="v">0 — 5 年</span></span>
          </div>
        </div>

        <!-- key 强制切省份时 re-mount → 重放 stagger 入场动画。
             a11y SC 2.3.3:reduced-motion 时 animationDelay 也归零,
             否则即便 global @media 把 duration 设为 0.01ms,数百 ms 的 delay
             仍会让卡片"延迟显示",对认知障碍 / 前庭敏感用户不友好。 -->
        <div :key="selectedIdx" class="stages" role="list" aria-label="韧性路径三阶段">
          <div
            v-for="(s, si) in stages"
            :key="s.key"
            class="stage"
            :class="s.cls"
            role="listitem"
            :style="{ animationDelay: prefersReducedMotion() ? '0s' : si * 0.12 + 's' }"
          >
            <div class="stage-marker" aria-hidden="true"></div>
            <div class="stage-head">
              <h3>
                {{ s.title }}
                <span class="stage-tag">STAGE {{ si + 1 }}</span>
              </h3>
              <span class="stage-period">PERIOD · <span class="v">{{ s.range }}</span></span>
            </div>
            <div class="stage-sub">
              <template v-for="(sub, i) in s.sub" :key="sub">
                <span class="acc">{{ sub }}</span>
                <span v-if="i < s.sub.length - 1" class="dot" aria-hidden="true"> · </span>
              </template>
            </div>
            <div class="actions" role="list" :aria-label="`${s.title}行动项列表`">
              <div v-if="s.items.length === 0" class="action-empty">
                该省份在此阶段无显著匹配规则，可根据本地实际补充行动项
              </div>
              <div
                v-for="(it, i) in s.items"
                v-else
                :key="it.ruleId"
                class="action"
                role="listitem"
                :style="{ animationDelay: prefersReducedMotion() ? '0s' : si * 0.12 + i * 0.06 + 0.2 + 's' }"
              >
                <div class="action-num">{{ String(i + 1).padStart(2, '0') }}</div>
                <div class="action-body">
                  <div class="action-title">{{ it.title }}</div>
                  <!-- desc 经 DOMPurify 白名单（仅 <span class>）。即便未来切外部 API 也防 XSS。 -->
                  <div class="action-desc" v-html="sanitizeDesc(it.desc)"></div>
                  <div class="action-tags">
                    <span
                      v-for="t in it.tags"
                      :key="t"
                      class="action-tag"
                      :class="{ priority: t.includes('优先') }"
                    >{{ t }}</span>
                  </div>
                </div>
              </div>
            </div>
          </div>
        </div>
      </section>
    </div>

    <footer class="page-foot">
      <a href="/prototypes/04-resilience-pathway.html" target="_blank" class="proto-link">查看原型 HTML ↗</a>
      <span class="note">11 条规则引擎前端实现于 <code>frontend/src/data/recommendation.ts</code>；
        5/29 后端 <code>services/recommendation.py</code> 同步落地 + 提供 <code>/api/recommendation/&lt;省&gt;</code></span>
    </footer>
  </section>
</template>

<style scoped>
.page { padding: 24px 32px; max-width: 1480px; margin: 0 auto; }

.page-head { margin-bottom: 24px; }
.eyebrow {
  font-family: var(--font-mono);
  font-size: 10px;
  color: var(--green);
  letter-spacing: 1.5px;
  text-transform: uppercase;
  margin-bottom: 8px;
}
.page-head h2 {
  font-family: var(--font-serif);
  font-size: 26px;
  font-weight: 600;
  margin-bottom: 6px;
}
.lead { font-size: 13px; color: var(--text-2); max-width: 920px; line-height: 1.7; }

.grid {
  display: grid;
  grid-template-columns: minmax(280px, 360px) minmax(0, 1fr);
  gap: 20px;
}

/* ============ sidebar ============ */
.sidebar { display: flex; flex-direction: column; gap: 16px; }

.card {
  background: var(--bg-card);
  border: 1px solid var(--border);
  border-radius: var(--r-xl);
  padding: 16px;
}
.card-head {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  margin-bottom: 14px;
  padding-bottom: 10px;
  border-bottom: 1px solid var(--border);
}
.card-head .num {
  font-family: var(--font-mono);
  font-size: 9px;
  color: var(--text-3);
  letter-spacing: 1px;
  margin-bottom: 2px;
}
.card-head h3 {
  font-family: var(--font-serif);
  font-size: 14px;
  font-weight: 600;
}

.province-select {
  width: 100%;
  background: var(--bg-elev);
  border: 1px solid var(--border-strong);
  border-radius: var(--r-md);
  color: var(--text);
  padding: 10px 12px;
  font-size: 12px;
  font-family: var(--font-sans);
  cursor: pointer;
  appearance: none;
  background-image: url("data:image/svg+xml;utf8,<svg xmlns='http://www.w3.org/2000/svg' width='10' height='6' viewBox='0 0 10 6'><path d='M0 0l5 6 5-6z' fill='%236B7A72'/></svg>");
  background-repeat: no-repeat;
  background-position: right 12px center;
  background-size: 8px;
}
/* a11y SC 2.4.11 Focus Appearance:替代 outline:none */
.province-select:focus { border-color: var(--green); }
.province-select:focus-visible {
  outline: var(--focus-ring);
  outline-offset: var(--focus-offset);
  border-color: var(--green-bright);
}

.rank-tag {
  font-family: var(--font-mono);
  font-size: 10px;
  padding: 3px 8px;
  border-radius: var(--r-sm);
  letter-spacing: 0.5px;
}
.rank-tag.hi { color: var(--risk-5); background: rgba(126, 69, 48, 0.18); }
.rank-tag.mid { color: var(--amber-bright); background: rgba(230, 182, 85, 0.12); }
.rank-tag.lo { color: var(--green-bright); background: rgba(160, 183, 133, 0.12); }

.prov-name {
  font-family: var(--font-serif);
  font-size: 30px;
  font-weight: 600;
  margin-bottom: 4px;
}
.prov-name .suffix {
  font-size: 14px;
  color: var(--text-3);
  margin-left: 4px;
  font-weight: 400;
}
.prov-type {
  font-family: var(--font-mono);
  font-size: 11px;
  color: var(--green);
  letter-spacing: 0.5px;
  margin-bottom: 10px;
}
.prov-desc {
  font-size: 12px;
  line-height: 1.7;
  color: var(--text-2);
  margin-bottom: 14px;
}

.metrics-grid {
  display: grid;
  grid-template-columns: repeat(2, 1fr);
  gap: 8px;
}
.metric {
  background: var(--bg-elev);
  border-radius: var(--r-sm);
  padding: 10px;
}
.metric .lbl {
  font-family: var(--font-mono);
  font-size: 9px;
  color: var(--text-3);
  letter-spacing: 0.5px;
  margin-bottom: 4px;
}
.metric .val {
  font-family: var(--font-mono);
  font-size: 18px;
  font-weight: 600;
  color: var(--text);
  line-height: 1.1;
}
.metric .delta {
  font-family: var(--font-mono);
  font-size: 10px;
  margin-top: 4px;
  color: var(--text-3);
}
.metric .delta.up { color: var(--risk-4); }
.metric .delta.dn { color: var(--green-bright); }

.audience-list { display: flex; flex-direction: column; gap: 10px; }
.audience-item {
  display: flex;
  gap: 10px;
  align-items: center;
}
.audience-icon {
  width: 30px; height: 30px;
  border-radius: 50%;
  font-family: var(--font-serif);
  font-weight: 600;
  font-size: 13px;
  display: flex;
  align-items: center;
  justify-content: center;
  color: #0E1A14;
  flex-shrink: 0;
}
.audience-icon.green { background: var(--green); }
.audience-icon.blue { background: var(--blue); }
.audience-icon.amber { background: var(--amber); }
.audience-icon.purple { background: var(--purple); }
.audience-meta .role {
  font-size: 12px;
  color: var(--text);
  font-weight: 500;
}
.audience-meta .desc {
  font-family: var(--font-mono);
  font-size: 9px;
  color: var(--text-3);
  letter-spacing: 0.5px;
  margin-top: 2px;
}

/* ============ timeline ============ */
.timeline-wrap {
  background: var(--bg-card);
  border: 1px solid var(--border);
  border-radius: var(--r-xl);
  padding: 20px;
  display: flex;
  flex-direction: column;
  gap: 18px;
}

.timeline-meta {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding-bottom: 14px;
  border-bottom: 1px solid var(--border);
}
.timeline-meta .label {
  font-family: var(--font-mono);
  font-size: 10px;
  color: var(--green);
  letter-spacing: 1.2px;
}
.timeline-meta .stats {
  display: flex;
  gap: 18px;
  font-family: var(--font-mono);
  font-size: 11px;
  color: var(--text-3);
}
.timeline-meta .v {
  color: var(--text);
  font-weight: 600;
  margin-left: 4px;
}

.stages { display: flex; flex-direction: column; gap: 18px; }

.stage {
  position: relative;
  padding: 16px 16px 16px 28px;
  background: var(--bg);
  border-radius: var(--r-md);
  border-left: 3px solid;
  opacity: 0;
  animation: fadeStage 0.5s var(--ease-out) forwards;
}
.stage.short { border-left-color: var(--green); }
.stage.mid { border-left-color: var(--amber); }
.stage.long { border-left-color: var(--blue); }

@keyframes fadeStage {
  from { opacity: 0; transform: translateY(8px); }
  to { opacity: 1; transform: translateY(0); }
}

.stage-marker {
  position: absolute;
  left: -7px;
  top: 22px;
  width: 11px; height: 11px;
  border-radius: 50%;
  background: var(--bg);
  border: 2px solid;
}
.stage.short .stage-marker { border-color: var(--green); }
.stage.mid .stage-marker { border-color: var(--amber); }
.stage.long .stage-marker { border-color: var(--blue); }

.stage-head {
  display: flex;
  justify-content: space-between;
  align-items: baseline;
  margin-bottom: 6px;
}
.stage-head h3 {
  font-family: var(--font-serif);
  font-size: 17px;
  font-weight: 600;
  color: var(--text);
}
.stage-head h3::before {
  content: '▸';
  margin-right: 6px;
  font-size: 14px;
}
.stage.short .stage-head h3::before { color: var(--green); }
.stage.mid .stage-head h3::before { color: var(--amber); }
.stage.long .stage-head h3::before { color: var(--blue); }
.stage-tag {
  font-family: var(--font-mono);
  font-size: 10px;
  color: var(--text-3);
  font-weight: 400;
  margin-left: 6px;
}
.stage-period {
  font-family: var(--font-mono);
  font-size: 9px;
  color: var(--text-3);
  letter-spacing: 1px;
}
.stage-period .v { color: var(--text); margin-left: 4px; font-weight: 600; }

.stage-sub {
  font-family: var(--font-mono);
  font-size: 10px;
  color: var(--text-3);
  margin-bottom: 12px;
  letter-spacing: 0.3px;
}
.stage-sub .acc { color: var(--green-bright); }
.stage.mid .stage-sub .acc { color: var(--amber-bright); }
.stage.long .stage-sub .acc { color: var(--blue-bright); }
.stage-sub .dot { color: var(--border-strong); margin: 0 4px; }

.actions { display: flex; flex-direction: column; gap: 10px; }
.action-empty {
  font-family: var(--font-mono);
  font-size: 11px;
  color: var(--text-3);
  padding: 14px;
  background: var(--bg-elev);
  border-radius: var(--r-sm);
}

.action {
  display: grid;
  grid-template-columns: 36px 1fr;
  gap: 12px;
  padding: 10px 12px;
  background: var(--bg-elev);
  border-radius: var(--r-sm);
  border-left: 2px solid transparent;
  opacity: 0;
  animation: fadeAction 0.4s var(--ease-out) forwards;
}
@keyframes fadeAction {
  from { opacity: 0; transform: translateX(-4px); }
  to { opacity: 1; transform: translateX(0); }
}
.stage.short .action { border-left-color: rgba(160, 183, 133, 0.4); }
.stage.mid .action { border-left-color: rgba(230, 182, 85, 0.4); }
.stage.long .action { border-left-color: rgba(107, 168, 181, 0.4); }

.action-num {
  font-family: var(--font-mono);
  font-size: 18px;
  font-weight: 700;
  color: var(--text-3);
  line-height: 1;
  align-self: center;
}
.stage.short .action-num { color: var(--green); }
.stage.mid .action-num { color: var(--amber); }
.stage.long .action-num { color: var(--blue); }

.action-body { min-width: 0; }
.action-title {
  font-family: var(--font-serif);
  font-size: 13px;
  font-weight: 600;
  color: var(--text);
  margin-bottom: 4px;
}
.action-desc {
  font-size: 12px;
  line-height: 1.65;
  color: var(--text-2);
  margin-bottom: 8px;
}
.action-desc :deep(.hl) {
  color: var(--green-bright);
  font-weight: 500;
}
.stage.mid .action-desc :deep(.hl) { color: var(--amber-bright); }
.stage.long .action-desc :deep(.hl) { color: var(--blue-bright); }
.action-desc :deep(.num) {
  font-family: var(--font-mono);
  font-weight: 600;
  color: var(--text);
}

.action-tags { display: flex; flex-wrap: wrap; gap: 6px; }
.action-tag {
  font-family: var(--font-mono);
  font-size: 9px;
  padding: 2px 7px;
  border-radius: 10px;
  background: var(--bg-card);
  color: var(--text-3);
  border: 1px solid var(--border);
  letter-spacing: 0.3px;
}
.action-tag.priority {
  color: var(--amber-bright);
  border-color: rgba(230, 182, 85, 0.4);
  background: rgba(230, 182, 85, 0.1);
}

.page-foot {
  margin-top: 24px;
  padding-top: 16px;
  border-top: 1px solid var(--border);
  display: flex;
  justify-content: space-between;
  align-items: center;
  font-size: 11px;
  color: var(--text-3);
  gap: 16px;
}
.page-foot .note {
  font-family: var(--font-mono);
  text-align: right;
}
.page-foot .note code {
  background: var(--bg-elev);
  padding: 1px 5px;
  border-radius: 2px;
  font-size: 10px;
}
.proto-link {
  flex-shrink: 0;
  padding: 6px 14px;
  background: var(--bg-elev);
  border: 1px solid var(--border-strong);
  border-radius: var(--r-md);
  color: var(--green-bright);
  font-family: var(--font-mono);
  font-size: 11px;
  letter-spacing: 0.3px;
  transition: all var(--dur-fast);
}
.proto-link:hover {
  border-color: var(--green);
  transform: translateY(-1px);
}
</style>
