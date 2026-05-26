/**
 * a11y 工具:`prefers-reduced-motion` 检测 + ECharts 动画时长适配。
 *
 * 背景:CSS @media (prefers-reduced-motion: reduce) 只能管 CSS animation/transition,
 * ECharts canvas 走自己的 JS 动画引擎,需要 JS 显式探测后传 `animationDuration: 0`。
 *
 * WCAG 2.2 SC 2.3.3 Animation from Interactions (AAA, but treated as AA-blocking for M1 评审)。
 */

/**
 * 用户是否启用「减少动画」OS 偏好。
 * SSR-safe:服务端 / 测试环境无 window 时 fallback false。
 */
export function prefersReducedMotion(): boolean {
  if (typeof window === 'undefined' || !window.matchMedia) return false
  try {
    return window.matchMedia('(prefers-reduced-motion: reduce)').matches
  } catch {
    return false
  }
}

/**
 * 包装一个 ECharts animationDuration:
 * 若用户开了 reduced motion 则返回 0,否则返回原值。
 *
 * 用法:
 *   animationDuration: motionDuration(800)
 */
export function motionDuration(ms: number): number {
  return prefersReducedMotion() ? 0 : ms
}
