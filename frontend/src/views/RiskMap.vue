<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { fetchProvinces, type Province } from '@/api/province'

const provinces = ref<Province[]>([])
const error = ref<string | null>(null)

onMounted(async () => {
  try {
    provinces.value = await fetchProvinces()
  } catch (e) {
    error.value = (e as Error).message
  }
})
</script>

<template>
  <section class="page">
    <div class="page-head">
      <div>
        <div class="eyebrow">M01 · SPATIO-TEMPORAL RISK MAP</div>
        <h2>风险时空地图</h2>
        <p class="lead">31 省 2011–2023 年粮食生产风险时空分布。Vue 化中（Phase 3.2，5/29-31 完成）。</p>
      </div>
    </div>

    <div class="placeholder">
      <div class="ph-num">01</div>
      <h3>占位 · Vue 化进度</h3>
      <ul class="check">
        <li>✅ 路由就绪</li>
        <li>✅ axios + /api/provinces 已联通：当前拉到 <strong>{{ provinces.length }}</strong> 个省份</li>
        <li>🟡 ECharts 中国地图 — 待 Phase 4 灌库 + Phase 3.2 实装</li>
        <li>🟡 时间滑块 (2011-2023) — 等 /api/provinces?year API</li>
        <li>🟡 Top10 + 明细卡 + 对比抽屉 — 沿用 prototypes/01-risk-map.html</li>
      </ul>

      <div v-if="error" class="error">API error: {{ error }}</div>

      <div v-if="provinces.length" class="preview">
        <div class="preview-title">前 5 个省份（来自 /api/provinces）</div>
        <table>
          <thead>
            <tr><th>省</th><th>类型</th><th>风险 Y</th><th>灌溉</th><th>洪涝</th></tr>
          </thead>
          <tbody>
            <tr v-for="p in provinces.slice(0, 5)" :key="p.name">
              <td>{{ p.name }}</td>
              <td>{{ p.type }}</td>
              <td>{{ p.y.toFixed(4) }}</td>
              <td>{{ p.irr.toFixed(1) }}%</td>
              <td>{{ p.flood.toFixed(1) }}%</td>
            </tr>
          </tbody>
        </table>
      </div>

      <a href="/prototypes/01-risk-map.html" class="proto-link" target="_blank">
        查看周煜楠静态原型 ↗
      </a>
    </div>
  </section>
</template>

<style scoped>
.page { padding: 24px 32px; max-width: 1320px; margin: 0 auto; }

.page-head { margin-bottom: 32px; }
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
.lead { font-size: 13px; color: var(--text-2); max-width: 720px; line-height: 1.7; }

.placeholder {
  background: var(--bg-card);
  border: 1px dashed var(--border-strong);
  border-radius: var(--r-xl);
  padding: 32px;
  position: relative;
}
.ph-num {
  position: absolute;
  top: 24px;
  right: 32px;
  font-family: var(--font-mono);
  font-size: 48px;
  font-weight: 700;
  color: var(--bg-elev);
  line-height: 1;
}
.placeholder h3 {
  font-family: var(--font-serif);
  font-size: 18px;
  margin-bottom: 16px;
}

.check { list-style: none; padding: 0; }
.check li {
  padding: 6px 0;
  font-size: 13px;
  border-bottom: 1px dashed var(--border);
}
.check li:last-child { border-bottom: none; }
.check strong {
  color: var(--green-bright);
  font-family: var(--font-mono);
  font-weight: 600;
}

.error {
  margin-top: 16px;
  padding: 10px 14px;
  background: rgba(184, 111, 77, 0.12);
  border: 1px solid var(--red);
  border-radius: var(--r-md);
  color: var(--red-bright);
  font-family: var(--font-mono);
  font-size: 12px;
}

.preview {
  margin-top: 24px;
  padding-top: 24px;
  border-top: 1px dashed var(--border);
}
.preview-title {
  font-family: var(--font-mono);
  font-size: 10px;
  color: var(--text-3);
  letter-spacing: 1px;
  text-transform: uppercase;
  margin-bottom: 12px;
}
table { width: 100%; border-collapse: collapse; font-size: 13px; }
th, td {
  text-align: left;
  padding: 8px 12px;
  border-bottom: 1px solid var(--border);
}
th {
  color: var(--text-3);
  font-family: var(--font-mono);
  font-size: 10px;
  font-weight: 600;
  letter-spacing: 0.5px;
  text-transform: uppercase;
}
td { color: var(--text-2); }

.proto-link {
  display: inline-block;
  margin-top: 20px;
  padding: 8px 16px;
  background: var(--bg-elev);
  border: 1px solid var(--border-strong);
  border-radius: var(--r-md);
  color: var(--green-bright);
  font-size: 12px;
  font-family: var(--font-mono);
  letter-spacing: 0.3px;
  transition: all var(--dur-fast);
}
.proto-link:hover {
  border-color: var(--green);
  transform: translateY(-1px);
}
</style>
