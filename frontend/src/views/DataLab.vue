<script setup lang="ts">
/**
 * M08 · 数据整备
 *
 * 四步：上传 → 映射 → 质检 → 导出。
 * 定位：只产出「对齐后的面板 + 质检报告 + 复现脚本」，不写主库、不出风险结论。
 * 质检规则来自县级面板踩过的坑（单位、重名县、市辖区合计行、总产/单产矛盾）。
 */
import { computed, reactive, ref } from 'vue'
import {
  createIngestSession,
  exportUrl,
  runIngest,
  type Finding,
  type IngestMode,
  type Mapping,
  type RunResult,
  type SessionCreated,
} from '@/api/ingest'

const steps = [
  { id: 1, name: '上传', hint: '统计表 + 地理文件' },
  { id: 2, name: '映射', hint: '对字段、定单位' },
  { id: 3, name: '质检', hint: '阻断 / 警告 / 提示' },
  { id: 4, name: '导出', hint: '面板 + 报告 + 脚本' },
]

const step = ref(1)
const mode = ref<IngestMode>('china')
const statsFile = ref<File | null>(null)
const geoFile = ref<File | null>(null)
const session = ref<SessionCreated | null>(null)
const result = ref<RunResult | null>(null)

const mapping = reactive<Record<string, string>>({})
const units = reactive<Record<string, string>>({})

const uploading = ref(false)
const running = ref(false)
const error = ref('')
const dragging = reactive({ stats: false, geo: false })

const canUpload = computed(() => {
  if (!statsFile.value) return false
  return mode.value === 'china' || !!geoFile.value
})

const mappedUnitFields = computed(() =>
  Object.keys(session.value?.unit_options ?? {}).filter((key) => mapping[key]),
)

const grouped = computed(() => {
  const findings = result.value?.findings ?? []
  return {
    blocker: findings.filter((f) => f.level === 'blocker'),
    warning: findings.filter((f) => f.level === 'warning'),
    info: findings.filter((f) => f.level === 'info'),
  }
})

const previewColumns = computed(() => (result.value?.columns ?? []).slice(0, 7))

const levelOrder = ['blocker', 'warning', 'info'] as const

const levelMeta: Record<string, { label: string; tone: string }> = {
  blocker: { label: '阻断', tone: 'red' },
  warning: { label: '警告', tone: 'amber' },
  info: { label: '提示', tone: 'blue' },
}

function pickFile(kind: 'stats' | 'geo', list: FileList | null) {
  const file = list?.[0]
  if (!file) return
  if (kind === 'stats') statsFile.value = file
  else geoFile.value = file
  resetSession()
}

function onDrop(kind: 'stats' | 'geo', event: DragEvent) {
  dragging[kind] = false
  pickFile(kind, event.dataTransfer?.files ?? null)
}

function resetSession() {
  session.value = null
  result.value = null
  error.value = ''
  if (step.value > 1) step.value = 1
  for (const key of Object.keys(mapping)) delete mapping[key]
  for (const key of Object.keys(units)) delete units[key]
}

function switchMode(next: IngestMode) {
  if (mode.value === next) return
  mode.value = next
  geoFile.value = null
  resetSession()
}

function formatSize(bytes: number) {
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
  return `${(bytes / 1024 / 1024).toFixed(1)} MB`
}

async function upload() {
  if (!canUpload.value || !statsFile.value) return
  uploading.value = true
  error.value = ''
  try {
    const data = await createIngestSession({
      mode: mode.value,
      stats: statsFile.value,
      geo: geoFile.value,
    })
    session.value = data
    for (const spec of data.field_specs) {
      mapping[spec.key] = data.mapping[spec.key]?.column ?? ''
    }
    for (const key of Object.keys(data.unit_options)) {
      units[key] = data.units.chosen[key] ?? ''
    }
    step.value = 2
  } catch (e) {
    error.value = e instanceof Error ? e.message : '上传失败'
  } finally {
    uploading.value = false
  }
}

async function run() {
  if (!session.value) return
  running.value = true
  error.value = ''
  try {
    const payload: Mapping = {}
    for (const spec of session.value.field_specs) {
      const column = mapping[spec.key] || null
      payload[spec.key] = {
        column,
        confidence: column ? 1 : 0,
        matched_alias: matchedAlias(spec.key, column),
      }
    }
    result.value = await runIngest(session.value.session_id, {
      mapping: payload,
      units: { ...units },
    })
    step.value = 3
  } catch (e) {
    error.value = e instanceof Error ? e.message : '清洗失败'
  } finally {
    running.value = false
  }
}

function matchedAlias(key: string, column: string | null) {
  if (!column) return ''
  return session.value?.mapping[key]?.matched_alias ?? ''
}

function downloadTemplate() {
  const rows = [
    '县名,年份,粮食产量(吨),播种面积(千公顷),单产(吨/公顷)',
    '商水县,2018,547400,80.5,6.8',
    '商水县,2019,556920,81.2,6.86',
    '商水县,2020,542030,80.9,6.7',
  ]
  const blob = new Blob(['\ufeff' + rows.join('\r\n')], {
    type: 'text/csv;charset=utf-8',
  })
  const link = document.createElement('a')
  link.href = URL.createObjectURL(blob)
  link.download = 'M08_数据整备模板.csv'
  link.click()
  URL.revokeObjectURL(link.href)
}

function openExport(kind: 'csv' | 'report' | 'script') {
  if (!session.value) return
  window.open(exportUrl(session.value.session_id, kind), '_blank')
}

function cell(value: unknown) {
  if (value === null || value === undefined || value === '') return '—'
  if (typeof value === 'number') return Number.isInteger(value) ? value : value.toFixed(3)
  return String(value)
}

function restart() {
  statsFile.value = null
  geoFile.value = null
  step.value = 1
  resetSession()
}
</script>

<template>
  <div class="lab">
    <header class="page-head">
      <div>
        <div class="eyebrow">M08 · 数据整备</div>
        <h2>把别人的表，变成能复现的面板</h2>
        <p class="lead">
          上传 → 对齐口径 → 体检 → 导出。系统只交出「清洗后的面板 + 质检报告 + 复现脚本」，
          不写主库、不出风险结论。
        </p>
      </div>
      <div class="head-note">
        <div class="note-title">中国模式</div>
        <div class="note-body">内置 1,199 县边界与 2012–2023 气候</div>
        <div class="note-title">国外模式</div>
        <div class="note-body">需上传 GeoJSON，气候取本地 4.6km 栅格</div>
      </div>
    </header>

    <ol class="stepper" aria-label="数据整备步骤">
      <li
        v-for="item in steps"
        :key="item.id"
        :class="{ active: step === item.id, done: step > item.id }"
      >
        <span class="num" aria-hidden="true">{{ step > item.id ? '✓' : item.id }}</span>
        <span class="txt">
          <strong>{{ item.name }}</strong>
          <em>{{ item.hint }}</em>
        </span>
      </li>
    </ol>

    <p v-if="error" class="alert" role="alert" aria-live="polite">{{ error }}</p>

    <!-- ── 1 上传 ─────────────────────────────────────────────── -->
    <section v-show="step === 1" class="panel">
      <div class="mode-row">
        <div class="seg" role="group" aria-label="数据归属">
          <button
            :class="{ on: mode === 'china' }"
            :aria-pressed="mode === 'china'"
            @click="switchMode('china')"
          >
            中国数据
            <small>用内置边界与气候</small>
          </button>
          <button
            :class="{ on: mode === 'custom' }"
            :aria-pressed="mode === 'custom'"
            @click="switchMode('custom')"
          >
            其他国家
            <small>自带 GeoJSON 边界</small>
          </button>
        </div>
        <button class="link-btn" type="button" @click="downloadTemplate">
          下载 CSV 模板
        </button>
      </div>

      <div class="drops">
        <label
          class="drop"
          :class="{ over: dragging.stats, filled: !!statsFile }"
          @dragover.prevent="dragging.stats = true"
          @dragleave.prevent="dragging.stats = false"
          @drop.prevent="onDrop('stats', $event)"
        >
          <input
            type="file"
            accept=".csv,.txt,.tsv,.xlsx,.xlsm"
            class="sr-only"
            @change="pickFile('stats', ($event.target as HTMLInputElement).files)"
          />
          <span class="badge">必填</span>
          <strong>统计表</strong>
          <span class="hint">CSV / XLSX，≤ 10 MB</span>
          <span v-if="statsFile" class="file">
            {{ statsFile.name }} · {{ formatSize(statsFile.size) }}
          </span>
          <span v-else class="cta">拖到这里，或点击选择</span>
        </label>

        <label
          class="drop"
          :class="{ over: dragging.geo, filled: !!geoFile, muted: mode === 'china' }"
          @dragover.prevent="dragging.geo = true"
          @dragleave.prevent="dragging.geo = false"
          @drop.prevent="onDrop('geo', $event)"
        >
          <input
            type="file"
            accept=".json,.geojson"
            class="sr-only"
            @change="pickFile('geo', ($event.target as HTMLInputElement).files)"
          />
          <span class="badge" :class="{ ghost: mode === 'china' }">
            {{ mode === 'china' ? '不需要' : '必填' }}
          </span>
          <strong>地理文件</strong>
          <span class="hint">GeoJSON 面要素，带 name 属性</span>
          <span v-if="geoFile" class="file">
            {{ geoFile.name }} · {{ formatSize(geoFile.size) }}
          </span>
          <span v-else class="cta">
            {{ mode === 'china' ? '中国模式用内置县级边界' : '拖到这里，或点击选择' }}
          </span>
        </label>
      </div>

      <div class="actions">
        <button class="primary" :disabled="!canUpload || uploading" @click="upload">
          {{ uploading ? '解析中…' : '解析并进入映射' }}
        </button>
        <span v-if="!canUpload" class="actions-hint">
          {{ statsFile ? '请补上地理文件' : '先选一个统计表' }}
        </span>
      </div>

      <div class="boundary">
        <strong>边界</strong>
        <span>
          内置模型只在中国 10 个主产省训练，别国数据只做清洗与气候拼接，不做风险打分。
        </span>
      </div>
    </section>

    <!-- ── 2 映射 ─────────────────────────────────────────────── -->
    <section v-show="step === 2 && session" class="panel">
      <div class="panel-head">
        <div>
          <h3>字段映射</h3>
          <p>
            {{ session?.source_file }} · {{ session?.rows }} 行 ·
            {{
              session?.years.length
                ? `${session.years[0]}–${session.years[session.years.length - 1]}`
                : '未识别年份'
            }}
          </p>
        </div>
        <span class="pill">{{ mode === 'china' ? '中国模式' : '国外模式' }}</span>
      </div>

      <div class="map-grid">
        <div class="map-row head">
          <span>标准字段</span>
          <span>上传列</span>
          <span>说明</span>
        </div>
        <div
          v-for="spec in session?.field_specs ?? []"
          :key="spec.key"
          class="map-row"
        >
          <label :for="`map-${spec.key}`" class="field-label">
            {{ spec.label }}
            <em v-if="spec.required" class="req">必填</em>
          </label>
          <select
            :id="`map-${spec.key}`"
            v-model="mapping[spec.key]"
            class="select"
          >
            <option value="">— 不使用 —</option>
            <option v-for="col in session?.columns ?? []" :key="col" :value="col">
              {{ col }}
            </option>
          </select>
          <span class="confidence">
            <template v-if="mapping[spec.key]">
              <span class="dot ok" aria-hidden="true"></span>
              已对上
            </template>
            <template v-else>未映射</template>
          </span>
        </div>
      </div>

      <div v-if="mappedUnitFields.length" class="units">
        <h3>单位口径</h3>
        <p class="units-lead">
          单位错一档，结果差 1000 倍。下面的建议来自列的数值量级，最终以你的原始表为准。
        </p>
        <div
          v-for="key in mappedUnitFields"
          :key="key"
          class="unit-row"
        >
          <span class="field-label">{{ session?.field_specs.find((s) => s.key === key)?.label }}</span>
          <select v-model="units[key]" class="select">
            <option
              v-for="(_, unit) in session?.unit_options[key] ?? {}"
              :key="unit"
              :value="unit"
            >
              {{ unit }}
            </option>
          </select>
          <span v-if="session?.units.inferred[key]" class="confidence">
            建议「{{ session?.units.inferred[key].suggested }}」·
            {{ session?.units.inferred[key].reason }}
          </span>
        </div>
      </div>

      <div class="actions">
        <button class="ghost" type="button" @click="step = 1">上一步</button>
        <button class="primary" :disabled="running" @click="run">
          {{ running ? '清洗中…' : '执行质检' }}
        </button>
        <span v-if="running" class="actions-hint">
          国外模式要读本地栅格，可能需要 20–60 秒
        </span>
      </div>
    </section>

    <!-- ── 3 质检 ─────────────────────────────────────────────── -->
    <section v-show="step === 3 && result" class="panel">
      <div class="tiles">
        <div class="tile">
          <span>输出行数</span>
          <strong>{{ result?.summary.output_rows }}</strong>
        </div>
        <div class="tile">
          <span>地区匹配</span>
          <strong>{{ Math.round((result?.summary.match_rate ?? 0) * 100) }}%</strong>
          <em>{{ result?.summary.matched }} / {{ result?.summary.input_rows }}</em>
        </div>
        <div class="tile">
          <span>气候覆盖</span>
          <strong>{{ Math.round((result?.summary.climate_rate ?? 0) * 100) }}%</strong>
          <em>{{ result?.summary.climate_covered }} / {{ result?.summary.input_rows }}</em>
        </div>
        <div class="tile" :class="{ alert: result?.blocked }">
          <span>结论</span>
          <strong>{{ result?.blocked ? '有阻断项' : '可导出' }}</strong>
          <em>
            {{
              result?.blocked
                ? '先处理阻断项'
                : `${result?.findings.length ?? 0} 条检查，${
                    (result?.findings ?? []).filter((f) => f.level !== 'info').length
                  } 条需留意`
            }}
          </em>
        </div>
      </div>

      <div class="findings">
        <div
          v-for="level in levelOrder"
          :key="level"
          class="group"
        >
          <template v-if="grouped[level].length">
            <h3 :class="levelMeta[level].tone">
              {{ levelMeta[level].label }}
              <span>{{ grouped[level].length }}</span>
            </h3>
            <article
              v-for="item in grouped[level]"
              :key="item.rule"
              class="finding"
              :class="levelMeta[level].tone"
            >
              <header>
                <strong>{{ item.title }}</strong>
                <span v-if="item.count" class="count">{{ item.count }} 行</span>
              </header>
              <p>{{ item.detail }}</p>
              <p v-if="item.samples.length" class="samples">
                示例：{{ item.samples.join('、') }}
              </p>
              <p v-if="item.suggestion" class="suggest">建议：{{ item.suggestion }}</p>
            </article>
          </template>
        </div>
        <p v-if="!result?.findings.length" class="clean">
          没有发现问题。可以导出。
        </p>
      </div>

      <div class="actions">
        <button class="ghost" type="button" @click="step = 2">回去改映射</button>
        <button class="primary" @click="step = 4">查看结果与导出</button>
      </div>
    </section>

    <!-- ── 4 导出 ─────────────────────────────────────────────── -->
    <section v-show="step === 4 && result" class="panel">
      <div class="panel-head">
        <div>
          <h3>清洗结果</h3>
          <p>前 20 行预览 · 共 {{ result?.summary.output_rows }} 行 · {{ result?.columns.length }} 列</p>
        </div>
        <span class="pill mono">{{ result?.session_id.slice(0, 8) }}</span>
      </div>

      <div class="table-wrap">
        <table>
          <thead>
            <tr>
              <th v-for="col in previewColumns" :key="col">{{ col }}</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="(row, index) in result?.preview ?? []" :key="index">
              <td v-for="col in previewColumns" :key="col">{{ cell(row[col]) }}</td>
            </tr>
          </tbody>
        </table>
      </div>
      <p class="table-note">
        预览只显示前 7 列，完整 {{ result?.columns.length }} 列在导出的 CSV 里。
      </p>

      <div class="exports">
        <button
          v-for="item in result?.exports ?? []"
          :key="item.kind"
          class="export"
          @click="openExport(item.kind)"
        >
          <strong>{{ item.label }}</strong>
          <span>{{ item.hint }}</span>
          <em aria-hidden="true">↓</em>
        </button>
      </div>

      <div class="boundary">
        <strong>记住</strong>
        <span>
          这份结果只证明「表已对齐、可用」。2023 年无产量真值；气候取自县治最近格点，不是全县面平均。
        </span>
      </div>

      <div class="actions">
        <button class="ghost" type="button" @click="step = 3">回看质检</button>
        <button class="primary" type="button" @click="restart">换一个文件</button>
      </div>
    </section>
  </div>
</template>

<style scoped>
.lab {
  padding: 28px 32px 64px;
  max-width: 1180px;
  margin: 0 auto;
}

.page-head {
  display: flex;
  justify-content: space-between;
  gap: 32px;
  align-items: flex-start;
  margin-bottom: 24px;
}
.eyebrow {
  font-family: var(--font-mono);
  font-size: 11px;
  letter-spacing: 1.2px;
  color: var(--green);
  text-transform: uppercase;
}
.page-head h2 {
  font-family: var(--font-serif);
  font-size: 26px;
  font-weight: 600;
  margin: 6px 0 8px;
}
.lead {
  color: var(--text-2);
  font-size: 13px;
  max-width: 560px;
}
.head-note {
  min-width: 260px;
  background: var(--bg-2);
  border: 1px solid var(--border);
  border-radius: var(--r-xl);
  padding: 14px 16px;
  font-size: 12px;
}
.note-title {
  color: var(--text-3);
  font-family: var(--font-mono);
  font-size: 10px;
  letter-spacing: 0.8px;
  margin-bottom: 2px;
}
.note-body {
  color: var(--text);
  margin-bottom: 10px;
}
.note-body:last-child { margin-bottom: 0; }

.stepper {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 10px;
  list-style: none;
  margin-bottom: 20px;
}
.stepper li {
  display: flex;
  gap: 10px;
  align-items: center;
  padding: 12px 14px;
  border: 1px solid var(--border);
  border-radius: var(--r-lg);
  background: var(--bg-2);
  color: var(--text-3);
}
.stepper li.active {
  border-color: rgba(160, 183, 133, 0.45);
  background: rgba(160, 183, 133, 0.08);
  color: var(--text);
}
.stepper li.done { color: var(--text-2); }
.stepper .num {
  width: 24px;
  height: 24px;
  border-radius: 50%;
  display: grid;
  place-items: center;
  font-family: var(--font-mono);
  font-size: 11px;
  border: 1px solid var(--border-strong);
}
.stepper li.active .num {
  background: var(--green);
  color: #0E1A14;
  border-color: var(--green);
}
.stepper li.done .num { color: var(--green); border-color: var(--green-deep); }
.stepper .txt { display: flex; flex-direction: column; line-height: 1.35; }
.stepper strong { font-size: 12px; font-weight: 600; }
.stepper em { font-style: normal; font-size: 10px; color: var(--text-3); }

.panel {
  background: var(--bg-card);
  border: 1px solid var(--border);
  border-radius: var(--r-xl);
  padding: 22px 24px;
}

.mode-row {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 16px;
  margin-bottom: 18px;
}
.seg { display: flex; gap: 8px; }
.seg button {
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  gap: 2px;
  padding: 10px 16px;
  border: 1px solid var(--border);
  border-radius: var(--r-lg);
  background: var(--bg-2);
  font-size: 13px;
  color: var(--text-2);
  transition: all var(--dur-fast);
}
.seg button small { font-size: 10px; color: var(--text-3); }
.seg button.on {
  color: var(--text);
  border-color: rgba(160, 183, 133, 0.5);
  background: rgba(160, 183, 133, 0.1);
}
.link-btn {
  font-size: 12px;
  color: var(--green);
  text-decoration: underline;
  text-underline-offset: 3px;
}

.drops {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 14px;
}
.drop {
  position: relative;
  display: flex;
  flex-direction: column;
  gap: 4px;
  padding: 22px;
  min-height: 150px;
  border: 1px dashed var(--border-strong);
  border-radius: var(--r-xl);
  background: var(--bg-2);
  cursor: pointer;
  transition: all var(--dur-fast);
}
.drop:hover,
.drop.over {
  border-color: var(--green);
  background: rgba(160, 183, 133, 0.06);
}
.drop.filled { border-style: solid; border-color: var(--green-deep); }
.drop.muted { opacity: 0.72; }
.drop strong { font-size: 14px; }
.drop .hint { font-size: 11px; color: var(--text-3); }
.drop .cta { margin-top: auto; font-size: 12px; color: var(--green); }
.drop .file { margin-top: auto; font-family: var(--font-mono); font-size: 11px; color: var(--text); }
.badge {
  align-self: flex-start;
  font-family: var(--font-mono);
  font-size: 9px;
  letter-spacing: 0.6px;
  padding: 2px 6px;
  border-radius: 3px;
  background: rgba(230, 182, 85, 0.16);
  color: var(--amber);
  margin-bottom: 6px;
}
.badge.ghost { background: rgba(149, 163, 155, 0.12); color: var(--text-3); }

.actions {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-top: 20px;
}
.actions-hint { font-size: 11px; color: var(--text-3); }
.primary {
  padding: 10px 20px;
  border-radius: var(--r-md);
  background: var(--green);
  color: #0E1A14;
  font-weight: 600;
  font-size: 13px;
  transition: all var(--dur-fast);
}
.primary:hover:not(:disabled) { background: var(--green-bright); }
.primary:disabled { opacity: 0.45; cursor: not-allowed; }
.ghost {
  padding: 10px 18px;
  border-radius: var(--r-md);
  border: 1px solid var(--border-strong);
  color: var(--text-2);
  font-size: 13px;
}
.ghost:hover { color: var(--text); border-color: var(--green-deep); }

.boundary {
  display: flex;
  gap: 10px;
  margin-top: 18px;
  padding: 12px 14px;
  border-left: 2px solid var(--amber);
  background: rgba(230, 182, 85, 0.06);
  border-radius: 0 var(--r-md) var(--r-md) 0;
  font-size: 12px;
  color: var(--text-2);
}
.boundary strong { color: var(--amber); white-space: nowrap; }

.panel-head {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  margin-bottom: 16px;
}
.panel-head h3 { font-size: 15px; margin-bottom: 4px; }
.panel-head p { font-size: 12px; color: var(--text-3); }
.pill {
  font-size: 10px;
  font-family: var(--font-mono);
  letter-spacing: 0.6px;
  padding: 4px 10px;
  border: 1px solid var(--border-strong);
  border-radius: 999px;
  color: var(--text-2);
}

.map-grid { border: 1px solid var(--border); border-radius: var(--r-lg); overflow: hidden; }
.map-row {
  display: grid;
  grid-template-columns: 180px minmax(180px, 1fr) 220px;
  gap: 14px;
  align-items: center;
  padding: 9px 14px;
  border-bottom: 1px solid var(--border);
  font-size: 12px;
}
.map-row:last-child { border-bottom: none; }
.map-row.head {
  background: var(--bg-2);
  color: var(--text-3);
  font-family: var(--font-mono);
  font-size: 10px;
  letter-spacing: 0.6px;
}
.field-label { display: flex; align-items: center; gap: 6px; color: var(--text); }
.req { font-style: normal; font-size: 9px; color: var(--amber); }
.select {
  width: 100%;
  padding: 7px 10px;
  background: var(--bg-2);
  border: 1px solid var(--border-strong);
  border-radius: var(--r-md);
  color: var(--text);
  font-size: 12px;
}
.confidence { font-size: 11px; color: var(--text-3); display: flex; align-items: center; gap: 6px; }
.dot { width: 6px; height: 6px; border-radius: 50%; display: inline-block; }
.dot.ok { background: var(--green); }

.units { margin-top: 18px; }
.units h3 { font-size: 14px; margin-bottom: 4px; }
.units-lead { font-size: 11px; color: var(--text-3); margin-bottom: 10px; }
.unit-row {
  display: grid;
  grid-template-columns: 180px 160px 1fr;
  gap: 14px;
  align-items: center;
  padding: 7px 0;
  font-size: 12px;
}

.tiles {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 10px;
  margin-bottom: 20px;
}
.tile {
  padding: 14px 16px;
  border: 1px solid var(--border);
  border-radius: var(--r-lg);
  background: var(--bg-2);
  display: flex;
  flex-direction: column;
  gap: 2px;
}
.tile span { font-size: 10px; color: var(--text-3); letter-spacing: 0.4px; }
.tile strong { font-family: var(--font-mono); font-size: 20px; }
.tile em { font-style: normal; font-size: 10px; color: var(--text-3); }
.tile.alert { border-color: rgba(184, 111, 77, 0.5); }
.tile.alert strong { color: var(--red-bright); }

.group h3 {
  font-size: 12px;
  letter-spacing: 0.4px;
  margin: 16px 0 8px;
  display: flex;
  align-items: center;
  gap: 8px;
}
.group h3 span {
  font-family: var(--font-mono);
  font-size: 10px;
  padding: 1px 6px;
  border-radius: 3px;
  background: var(--bg-2);
}
.group h3.red { color: var(--red-bright); }
.group h3.amber { color: var(--amber); }
.group h3.blue { color: var(--blue-bright); }

.finding {
  padding: 12px 14px;
  border-radius: var(--r-lg);
  background: var(--bg-2);
  border-left: 2px solid var(--border-strong);
  margin-bottom: 8px;
  font-size: 12px;
}
.finding.red { border-left-color: var(--red); }
.finding.amber { border-left-color: var(--amber); }
.finding.blue { border-left-color: var(--blue); }
.finding header { display: flex; justify-content: space-between; gap: 12px; margin-bottom: 4px; }
.finding strong { font-size: 13px; }
.finding .count { font-family: var(--font-mono); font-size: 10px; color: var(--text-3); }
.finding p { color: var(--text-2); line-height: 1.65; }
.finding .samples { font-family: var(--font-mono); font-size: 11px; color: var(--text-3); }
.finding .suggest { color: var(--green); }
.clean { color: var(--green); font-size: 13px; padding: 20px 0; }

.table-wrap { overflow-x: auto; border: 1px solid var(--border); border-radius: var(--r-lg); }
table { width: 100%; border-collapse: collapse; font-size: 11px; }
th, td { padding: 8px 12px; text-align: left; white-space: nowrap; border-bottom: 1px solid var(--border); }
th { background: var(--bg-2); color: var(--text-3); font-weight: 500; font-family: var(--font-mono); font-size: 10px; }
td { color: var(--text-2); font-family: var(--font-mono); }
tbody tr:last-child td { border-bottom: none; }
.table-note { font-size: 10px; color: var(--text-3); margin-top: 6px; }

.exports { display: grid; grid-template-columns: repeat(3, 1fr); gap: 10px; margin-top: 18px; }
.export {
  position: relative;
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  gap: 2px;
  padding: 14px 16px;
  border: 1px solid var(--border-strong);
  border-radius: var(--r-lg);
  background: var(--bg-2);
  text-align: left;
  transition: all var(--dur-fast);
}
.export:hover { border-color: var(--green); background: rgba(160, 183, 133, 0.08); }
.export strong { font-size: 13px; }
.export span { font-size: 10px; color: var(--text-3); }
.export em { position: absolute; right: 14px; top: 12px; font-style: normal; color: var(--green); }

.alert {
  padding: 10px 14px;
  border-radius: var(--r-md);
  background: rgba(184, 111, 77, 0.15);
  border: 1px solid rgba(184, 111, 77, 0.4);
  color: var(--red-bright);
  font-size: 12px;
  margin-bottom: 14px;
}

@media (max-width: 900px) {
  .lab { padding: 20px 16px 48px; }
  .page-head { flex-direction: column; }
  .head-note { width: 100%; }
  .stepper { grid-template-columns: repeat(2, 1fr); }
  .drops, .tiles, .exports { grid-template-columns: 1fr; }
  .map-row { grid-template-columns: 1fr; gap: 6px; }
  .map-row.head { display: none; }
  .unit-row { grid-template-columns: 1fr; gap: 6px; }
}
</style>
