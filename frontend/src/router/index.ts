import { createRouter, createWebHistory } from 'vue-router'

const router = createRouter({
  history: createWebHistory(),
  routes: [
    { path: '/', redirect: '/overview' },
    {
      path: '/overview',
      name: 'overview',
      component: () => import('@/views/Overview.vue'),
      meta: { title: '系统总览', code: 'M00' },
    },
    {
      path: '/risk-map',
      name: 'risk-map',
      component: () => import('@/views/RiskMap.vue'),
      meta: { title: '风险时空地图', code: 'M01' },
    },
    {
      path: '/shap',
      name: 'shap',
      component: () => import('@/views/ShapDashboard.vue'),
      meta: { title: 'SHAP 归因看板', code: 'M02' },
    },
    {
      path: '/scenario',
      name: 'scenario',
      component: () => import('@/views/ScenarioSim.vue'),
      meta: { title: '参数情景模拟', code: 'M03' },
    },
    {
      path: '/pathway',
      name: 'pathway',
      component: () => import('@/views/ResiliencePath.vue'),
      meta: { title: '韧性路径推荐', code: 'M04' },
    },
    {
      path: '/monitor',
      name: 'monitor',
      component: () => import('@/views/InferenceTrace.vue'),
      meta: { title: '推演监控', code: 'M05' },
    },
  ],
})

export default router
