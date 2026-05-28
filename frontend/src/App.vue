<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useRoute } from 'vue-router'
import { fetchHealth } from '@/api/health'

const route = useRoute()
const healthState = ref<'loading' | 'ok' | 'fail'>('loading')

onMounted(async () => {
  try {
    await fetchHealth()
    healthState.value = 'ok'
  } catch (e) {
    healthState.value = 'fail'
    console.error('[health] failed', e)
  }
})

const tabs = [
  { code: 'M01', name: '风险时空地图', path: '/risk-map' },
  { code: 'M02', name: 'SHAP 归因看板', path: '/shap' },
  { code: 'M03', name: '参数情景模拟', path: '/scenario' },
  { code: 'M04', name: '韧性路径推荐', path: '/pathway' },
]

// a11y(WCAG SC 1.4.1 Use of Color):健康状态不能只靠颜色。
// 加 icon(✓ / ✗ / …)+ 文本 + aria-live,屏幕阅读器朗读状态变化。
const healthIcon = computed(() => {
  if (healthState.value === 'ok') return '✓'
  if (healthState.value === 'fail') return '✗'
  return '…'
})
const healthLabel = computed(() => {
  if (healthState.value === 'ok') return '系统运行正常'
  if (healthState.value === 'fail') return '系统暂时不可达'
  return '系统就绪中'
})
</script>

<template>
  <!-- a11y(WCAG SC 2.4.1 Bypass Blocks):skip-link 让键盘用户跳过 header 直接到主内容。 -->
  <a href="#app-main" class="sr-only sr-only-focusable skip-link">跳转到主要内容</a>

  <header class="app-header" role="banner">
    <div class="brand">
      <div class="brand-logo" aria-hidden="true">粮</div>
      <div class="brand-text">
        <h1>极端气候下粮食生产风险智能分析</h1>
        <div class="sub">FOOD-RISK INTELLIGENCE PLATFORM</div>
      </div>
    </div>

    <!-- a11y(SC 4.1.2):主导航 aria-label + 当前 tab aria-current="page" -->
    <nav class="tabs" aria-label="主导航" role="navigation">
      <router-link
        v-for="t in tabs"
        :key="t.path"
        :to="t.path"
        class="tab"
        :class="{ active: route.path === t.path }"
        :aria-current="route.path === t.path ? 'page' : undefined"
        :aria-label="`${t.code} ${t.name}`"
      >
        <span class="code" aria-hidden="true">{{ t.code }}</span>
        <span class="name">{{ t.name }}</span>
      </router-link>
    </nav>

    <div class="header-right">
      <!-- a11y(SC 1.4.1 Use of Color + SC 4.1.3 Status Messages):
           健康状态依然通过 aria-live 朗读;视觉上仅在异常时显示文字 chip,
           正常 / 加载态只显示一个柔和的状态点,避免对外演示出现"检测中"字样。 -->
      <span
        class="health"
        :class="healthState"
        role="status"
        aria-live="polite"
        :aria-label="healthLabel"
      >
        <span class="dot" aria-hidden="true"></span>
        <span v-if="healthState === 'fail'" class="icon" aria-hidden="true">{{ healthIcon }}</span>
        <span v-if="healthState === 'fail'" class="label">系统暂时不可达</span>
      </span>
    </div>
  </header>

  <main id="app-main" class="app-main" role="main" tabindex="-1">
    <router-view v-slot="{ Component }">
      <transition name="fade" mode="out-in">
        <component :is="Component" />
      </transition>
    </router-view>
  </main>
</template>

<style scoped>
.app-header {
  position: sticky;
  top: 0;
  z-index: 100;
  background: rgba(22, 37, 32, 0.88);
  backdrop-filter: blur(16px);
  border-bottom: 1px solid var(--border);
  padding: 12px 32px;
  display: flex;
  align-items: center;
  gap: 32px;
}

.brand { display: flex; align-items: center; gap: 12px; flex-shrink: 0; }
.brand-logo {
  width: 34px; height: 34px;
  background: linear-gradient(135deg, var(--green-deep), var(--green));
  border-radius: var(--r-lg);
  display: flex; align-items: center; justify-content: center;
  font-family: var(--font-serif);
  font-weight: 700;
  font-size: 16px;
  color: #0E1A14;
}
.brand-text h1 {
  font-family: var(--font-serif);
  font-size: 14px;
  font-weight: 600;
  letter-spacing: 0.3px;
  line-height: 1.2;
}
.brand-text .sub {
  font-family: var(--font-mono);
  font-size: 9px;
  color: var(--text-3);
  letter-spacing: 1.1px;
  text-transform: uppercase;
  margin-top: 2px;
}

.tabs { display: flex; gap: 4px; flex: 1; }
.tab {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 14px;
  border-radius: var(--r-md);
  font-size: 12px;
  color: var(--text-2);
  transition: all var(--dur-fast);
  border: 1px solid transparent;
}
.tab:hover { color: var(--text); background: var(--bg-elev); }
.tab.active {
  color: var(--green-bright);
  background: rgba(160, 183, 133, 0.10);
  border-color: rgba(160, 183, 133, 0.25);
}
.tab .code {
  font-family: var(--font-mono);
  font-size: 10px;
  color: var(--text-3);
  letter-spacing: 0.5px;
}
.tab.active .code { color: var(--green); }
.tab .name { font-weight: 500; }

.header-right { flex-shrink: 0; }

.health {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  padding: 6px 10px;
  border-radius: var(--r-md);
  font-family: var(--font-mono);
  font-size: 11px;
  letter-spacing: 0.5px;
  background: transparent;
  border: 1px solid transparent;
  transition: all var(--dur-fast);
}
/* 仅在失败时露出 chip 外观,正常/加载态保持极简 */
.health.fail {
  padding: 6px 14px;
  background: var(--bg-elev);
  border-color: rgba(184, 111, 77, 0.3);
}
.health .dot {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: var(--text-3);
}
/* a11y SC 1.4.1: icon 通道补充色彩,色盲 / 高对比模式仍能识别状态 */
.health .icon {
  font-family: var(--font-mono);
  font-size: 12px;
  font-weight: 700;
  line-height: 1;
}
.health.ok { color: var(--green-bright); border-color: rgba(160, 183, 133, 0.25); }
.health.ok .dot { background: var(--green); animation: pulseDot 2.2s infinite; }
.health.fail { color: var(--red-bright); border-color: rgba(184, 111, 77, 0.3); }
.health.fail .dot { background: var(--red); }
.health.loading { color: var(--amber); }
.health.loading .dot { background: var(--amber); }

.app-main { flex: 1; }

.fade-enter-active, .fade-leave-active { transition: opacity var(--dur-base) var(--ease-out); }
.fade-enter-from, .fade-leave-to { opacity: 0; }
</style>
