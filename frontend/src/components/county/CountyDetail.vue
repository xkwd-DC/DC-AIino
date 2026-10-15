<script setup lang="ts">
/**
 * M07-B 选中县明细。纯展示组件:数据由父视图取好传入。
 *
 * 两件事分开讲:
 * 1. 「当年偏离」(clim_anomaly)—— 相对本县 2012–2023 常态,逐年可比,风险等级出处;
 * 2. 「气候画像」(clim_contrib + 16 维 SHAP)—— 该县气候条件本身偏有利/偏不利,
 *    跨县可比但含县际结构差异,不解释为"今年风险高"。
 */
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import * as echarts from 'echarts'
import type { CountyAttribution, CountyHistory, CountyHistoryEntry } from '@/api/county'
import { getCSSVar } from '@/data/mockProvinces'
import { motionDuration, prefersReducedMotion } from '@/data/a11y'

const props = defineProps<{
  meta: CountyHistory['county'] | null
  series: CountyHistoryEntry[]
  attribution: CountyAttribution | null
  year: number
  loading: boolean
  error: string | null
}>()

const RISK_LABELS = ['低', '较低', '中等', '较高', '高']

const current = computed<CountyHistoryEntry | null>(
  () => props.series.find((s) => s.year === props.year) ?? null,
)

const topItems = computed(() =>
  (props.attribution?.items ?? [])
    .filter((i) => i.shap != null)
    .slice(0, 6),
)

const maxAbsShap = computed(() =>
  Math.max(1e-6, ...topItems.value.map((i) => Math.abs(i.shap ?? 0))),
)

const chartEl = ref<HTMLDivElement | null>(null)
let chart: echarts.ECharts | null = null
let resizeObserver: ResizeObserver | null = null

function renderChart() {
  if (!chartEl.value) return
  if (!chart) {
    chart = echarts.init(chartEl.value, undefined, { renderer: 'canvas' })
    if ('ResizeObserver' in window) {
      resizeObserver = new ResizeObserver(() => chart?.resize())
      resizeObserver.observe(chartEl.value)
    }
  }
  const years = props.series.map((s) => String(s.year))
  const values = props.series.map((s) => s.clim_anomaly)
  const idx = props.series.findIndex((s) => s.year === props.year)

  chart.setOption(
    {
      backgroundColor: 'transparent',
      grid: { left: 4, right: 4, top: 10, bottom: 18, containLabel: true },
      xAxis: {
        type: 'category',
        data: years,
        axisLine: { lineStyle: { color: getCSSVar('--border-strong') } },
        axisLabel: { color: getCSSVar('--text-3'), fontSize: 9, interval: 1 },
        axisTick: { show: false },
      },
      yAxis: {
        type: 'value',
        name: 'Δ',
        nameTextStyle: { color: getCSSVar('--text-3'), fontSize: 10 },
        splitLine: { lineStyle: { color: 'rgba(68,97,90,0.35)' } },
        axisLabel: { color: getCSSVar('--text-3'), fontSize: 9 },
      },
      tooltip: {
        trigger: 'axis',
        backgroundColor: getCSSVar('--bg-card'),
        borderColor: getCSSVar('--border-strong'),
        textStyle: { color: getCSSVar('--text'), fontSize: 11 },
        formatter: (params: Array<{ axisValue: string; value: number }>) => {
          const p = params[0]
          return `${p.axisValue} 年 · 气候异常 Δ <b>${p.value >= 0 ? '+' : ''}${p.value.toFixed(3)}</b>`
        },
      },
      series: [
        {
          type: 'bar',
          data: values.map((v, i) => ({
            value: v,
            itemStyle: {
              color: i === idx
                ? getCSSVar('--green-bright')
                : v < 0
                  ? getCSSVar('--risk-4')
                  : getCSSVar('--green-deep'),
              borderRadius: [2, 2, 0, 0],
            },
          })),
          barMaxWidth: 14,
        },
      ],
      animation: !prefersReducedMotion(),
      animationDuration: motionDuration(400),
    },
    true,
  )
}

onMounted(() => {
  renderChart()
})
onBeforeUnmount(() => {
  resizeObserver?.disconnect()
  resizeObserver = null
  chart?.dispose()
  chart = null
})
// flush: 'post' —— 明细卡是 v-else-if 条件渲染,元素要在 DOM 更新之后才存在,
// 默认 pre flush 会在容器还没挂上时就去 init,导致图表空白。
watch(
  () => [props.series, props.year, chartEl.value] as const,
  () => { renderChart() },
  { flush: 'post' },
)
</script>

<template>
  <section class="detail" aria-labelledby="county-detail-title">
    <header class="detail-head">
      <div class="eyebrow">SELECTED · 县级明细</div>
      <h3 id="county-detail-title">
        {{ meta ? `${meta.province} · ${meta.county}` : '未选择县' }}
      </h3>
      <p v-if="meta" class="sub">
        {{ meta.city ?? '—' }} · 县代码 <span class="mono">{{ meta.county_code }}</span>
        <span v-if="!meta.on_map" class="tag warn">无独立县级边界(年鉴"市辖区"合计行)</span>
      </p>
    </header>

    <p v-if="!meta" class="hint">在地图上点击任意县,或从下方「高风险县清单」里选一个。</p>
    <p v-else-if="error" class="hint error" role="alert">{{ error }}</p>
    <p v-else-if="loading" class="hint" role="status" aria-live="polite">正在读取该县数据…</p>

    <template v-else-if="current">
      <dl class="metrics">
        <div>
          <dt>风险等级</dt>
          <dd>
            <span class="risk-chip" :data-level="current.risk_level">
              L{{ current.risk_level }} {{ RISK_LABELS[current.risk_level - 1] }}
            </span>
            <span class="mono sub-inline">年内分位 {{ current.risk_pct.toFixed(0) }}%</span>
          </dd>
        </div>
        <div>
          <dt>气候异常 Δ(相对本县常态)</dt>
          <dd class="mono" :class="current.clim_anomaly < 0 ? 'neg' : 'pos'">
            {{ current.clim_anomaly >= 0 ? '+' : '' }}{{ current.clim_anomaly.toFixed(3) }}
          </dd>
        </div>
        <div>
          <dt>气候条件画像(跨县可比)</dt>
          <dd class="mono">{{ current.clim_contrib.toFixed(3) }}
            <span class="sub-inline">分位 {{ current.contrib_pct.toFixed(0) }}%</span>
          </dd>
        </div>
        <div>
          <dt>当年粮食总产量</dt>
          <dd class="mono">
            {{ current.grain_output_t == null
              ? '无数据'
              : Math.round(current.grain_output_t).toLocaleString('zh-CN') + ' 吨' }}
          </dd>
        </div>
      </dl>

      <p v-if="current.y_true == null" class="extrap-note" role="note">
        <span aria-hidden="true">⚠</span>
        该年无产量真值（县域统计年鉴未出版该年数据），这里的归因是模型外推 ——
        只可读「当年气候条件」，不可读「已核实的产量偏差」。
      </p>

      <div class="chart-block">
        <h4>气候异常逐年轨迹 <span class="mono">Δ = 当年气候贡献 − 本县历年均值</span></h4>
        <div
          ref="chartEl"
          class="mini-chart"
          role="img"
          :aria-label="`${meta?.county ?? ''} 2012 至 2023 年气候异常逐年柱状图,当前选中 ${year} 年`"
        ></div>
      </div>

      <div class="shap-block">
        <h4>
          当年归因 Top 6
          <span class="mono">Δlog(总产量) 边际贡献</span>
        </h4>
        <p
          v-if="attribution && !attribution.available"
          class="hint"
        >该年无气候特征,无法归因。</p>
        <ul v-else class="shap-list">
          <li v-for="item in topItems" :key="item.feature">
            <div class="shap-row">
              <span class="name">{{ item.label }}</span>
              <span class="value mono">
                {{ (item.value ?? 0).toFixed(1) }} {{ item.unit }}
              </span>
              <span class="contrib mono" :class="(item.shap ?? 0) < 0 ? 'neg' : 'pos'">
                {{ (item.shap ?? 0) >= 0 ? '+' : '' }}{{ (item.shap ?? 0).toFixed(3) }}
              </span>
            </div>
            <div class="bar-track" aria-hidden="true">
              <div
                class="bar"
                :class="(item.shap ?? 0) < 0 ? 'neg' : 'pos'"
                :style="{ width: (Math.abs(item.shap ?? 0) / maxAbsShap) * 100 + '%' }"
              ></div>
            </div>
            <div class="flags">
              <span v-if="item.direction_stable === true" class="tag stable">
                ✓ 方向跨时间稳定
              </span>
              <span v-else-if="item.direction_stable === false" class="tag unstable">
                ⚠ 方向跨时间翻转,不作因果解读
              </span>
              <span v-else class="tag">无方向证据</span>
            </div>
          </li>
        </ul>
      </div>

      <p class="footnote">
        风险等级来自 <span class="mono">clim_anomaly</span>(县内去均值),回答"今年该县气候相对自身常态偏差多大";
        <span class="mono">clim_contrib</span> 是气候条件画像,含县际结构差异,不能当"今年风险"读。
      </p>
    </template>
  </section>
</template>

<style scoped>
.detail {
  background: var(--bg-card);
  border: 1px solid var(--border);
  border-radius: var(--r-lg);
  padding: var(--sp-5);
  height: 100%;
  overflow-y: auto;
}
.detail-head { margin-bottom: var(--sp-4); }
.eyebrow {
  font-family: var(--font-mono);
  font-size: 10px;
  letter-spacing: 1.2px;
  color: var(--text-3);
  text-transform: uppercase;
}
h3 {
  font-family: var(--font-serif);
  font-size: 17px;
  font-weight: 600;
  margin-top: var(--sp-1);
}
h4 {
  font-size: 12px;
  font-weight: 600;
  color: var(--text-2);
  display: flex;
  justify-content: space-between;
  align-items: baseline;
  gap: var(--sp-2);
  margin-bottom: var(--sp-2);
}
h4 .mono, .footnote .mono, .sub .mono {
  font-family: var(--font-mono);
  font-size: 10.5px;
  color: var(--text-3);
  font-weight: 400;
}
.sub { font-size: 11px; color: var(--text-3); }
.hint { font-size: 12px; color: var(--text-3); padding: var(--sp-4) 0; }
.hint.error { color: var(--amber-bright); }

.metrics {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: var(--sp-3);
  margin-bottom: var(--sp-5);
}
.metrics dt { font-size: 10.5px; color: var(--text-3); }
.metrics dd { font-size: 14px; margin-top: 2px; }
.metrics .mono { font-family: var(--font-mono); }
.sub-inline { font-size: 10.5px; color: var(--text-3); margin-left: 4px; }
.pos { color: var(--green-bright); }
.neg { color: var(--red-bright); }

.risk-chip {
  display: inline-block;
  padding: 2px 8px;
  border-radius: var(--r-sm);
  font-family: var(--font-mono);
  font-size: 12px;
  font-weight: 600;
  color: #0E1A14;
}
.risk-chip[data-level='1'] { background: var(--risk-1); }
.risk-chip[data-level='2'] { background: var(--risk-2); }
.risk-chip[data-level='3'] { background: var(--risk-3); color: #FFF; }
.risk-chip[data-level='4'] { background: var(--risk-4); color: #FFF; }
.risk-chip[data-level='5'] { background: var(--risk-5); color: #FFF; }

.extrap-note {
  display: flex;
  gap: var(--sp-2);
  font-size: 11px;
  color: var(--amber-bright);
  background: rgba(230, 182, 85, 0.08);
  border: 1px solid rgba(230, 182, 85, 0.25);
  border-radius: var(--r-sm);
  padding: var(--sp-2) var(--sp-3);
  margin-bottom: var(--sp-4);
  line-height: 1.6;
}

.chart-block { margin-bottom: var(--sp-5); }
.mini-chart { width: 100%; height: 130px; }

.shap-list { list-style: none; }
.shap-list li { margin-bottom: var(--sp-3); }
.shap-row {
  display: grid;
  grid-template-columns: 1fr auto auto;
  gap: var(--sp-2);
  align-items: baseline;
  font-size: 11.5px;
}
.shap-row .name { color: var(--text-2); }
.shap-row .mono { font-family: var(--font-mono); font-size: 11px; }
.shap-row .value { color: var(--text-3); }
.bar-track {
  height: 4px;
  background: var(--bg-2);
  border-radius: 2px;
  margin: 4px 0 3px;
  overflow: hidden;
}
.bar { height: 100%; border-radius: 2px; }
.bar.neg { background: var(--red); }
.bar.pos { background: var(--green); }
.flags { display: flex; gap: var(--sp-2); }
.tag {
  font-size: 10px;
  color: var(--text-3);
  border: 1px solid var(--border);
  border-radius: var(--r-sm);
  padding: 1px 5px;
}
.tag.stable { color: var(--green-bright); border-color: rgba(160, 183, 133, 0.35); }
.tag.unstable { color: var(--amber-bright); border-color: rgba(230, 182, 85, 0.35); }
.tag.warn { color: var(--amber-bright); border-color: rgba(230, 182, 85, 0.35); margin-left: 4px; }

.footnote {
  margin-top: var(--sp-4);
  padding-top: var(--sp-3);
  border-top: 1px solid var(--border);
  font-size: 11px;
  color: var(--text-3);
  line-height: 1.6;
}
</style>
