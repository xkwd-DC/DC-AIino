<script setup lang="ts">
// M02 SHAP 归因看板 — Vue 化 Phase 3.3 实装（依赖熊鑫 Phase 2 模型）
</script>

<template>
  <section class="page">
    <div class="eyebrow">M02 · SHAP ATTRIBUTION DASHBOARD</div>
    <h2>SHAP 归因看板</h2>
    <p class="lead">11 特征全局重要性 + Waterfall + Beeswarm + 4 张解读卡。Phase 3.3 实装（等熊鑫模型）。</p>
    <div class="placeholder">
      <p>Vue 化 pending · Phase 3.3 ddl 6/10</p>
      <a href="/prototypes/02-shap-dashboard.html" target="_blank">查看周煜楠静态原型 ↗</a>
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
