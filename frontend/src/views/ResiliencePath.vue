<script setup lang="ts">
// M04 韧性路径推荐 — Vue 化 Phase 3.5 实装（不依赖熊鑫，5/31 ddl）
</script>

<template>
  <section class="page">
    <div class="eyebrow">M04 · RESILIENCE PATHWAY</div>
    <h2>韧性路径推荐</h2>
    <p class="lead">基于省份风险指纹三阶段（短/中/长期）行动路径。Phase 3.5 实装（5/31 ddl，不依赖熊鑫）。</p>
    <div class="placeholder">
      <p>Vue 化 pending · 后端需补 /api/recommendation/&lt;province&gt; (11 规则引擎 Python 化)</p>
      <a href="/prototypes/04-resilience-pathway.html" target="_blank">查看周煜楠静态原型 ↗</a>
    </div>
  </section>
</template>

<style scoped>
.page { padding: 24px 32px; max-width: 1320px; margin: 0 auto; }
.eyebrow {
  font-family: var(--font-mono);
  font-size: 10px;
  color: var(--green);
  letter-spacing: 1.5px;
  text-transform: uppercase;
  margin-bottom: 8px;
}
h2 { font-family: var(--font-serif); font-size: 26px; font-weight: 600; margin-bottom: 6px; }
.lead { font-size: 13px; color: var(--text-2); max-width: 720px; margin-bottom: 32px; }
.placeholder {
  background: var(--bg-card);
  border: 1px dashed var(--border-strong);
  border-radius: var(--r-xl);
  padding: 32px;
}
.placeholder a {
  display: inline-block;
  margin-top: 12px;
  padding: 6px 14px;
  background: var(--bg-elev);
  border: 1px solid var(--border-strong);
  border-radius: var(--r-md);
  color: var(--green-bright);
  font-family: var(--font-mono);
  font-size: 11px;
}
</style>
