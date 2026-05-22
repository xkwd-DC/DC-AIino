<script setup lang="ts">
// M03 参数情景模拟 — Vue 化 Phase 3.4 实装
</script>

<template>
  <section class="page">
    <div class="eyebrow">M03 · SCENARIO SIMULATION</div>
    <h2>参数情景模拟</h2>
    <p class="lead">5 滑块实时联动 + 双仪表盘 + odometer 数字滚动 + 情景保存。Phase 3.4 实装。</p>
    <div class="placeholder">
      <p>Vue 化 pending · Phase 3.4 ddl 6/12（mock 推理 API 已就位）</p>
      <a href="/prototypes/03-scenario-sim.html" target="_blank">查看周煜楠静态原型 ↗</a>
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
