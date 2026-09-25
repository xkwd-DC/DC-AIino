// 用 Playwright + 系统 Chrome 对 6 个模块截图（1920×1080）。
// 避免 networkidle（Vite HMR WebSocket 永不空闲），改用 domcontentloaded + 显式等待。
import { createRequire } from 'node:module'
const require = createRequire(import.meta.url)
const { chromium } = require(
  'C:/Users/darcy/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright',
)

const BASE = 'http://localhost:5173'
const OUT = 'D:/DC/DC-AIino/_shots'

// 页面路由 → (文件名, 等待的正文锚点)
const PAGES = [
  { path: '/overview', alias: 'M00_系统总览' },
  { path: '/risk-map', alias: 'M01_风险时空地图' },
  { path: '/shap', alias: 'M02_SHAP归因看板' },
  { path: '/scenario', alias: 'M03_参数情景模拟' },
  { path: '/pathway', alias: 'M04_韧性路径推荐' },
  { path: '/monitor', alias: 'M05_推演监控' },
]

async function main() {
  const browser = await chromium.launch({ channel: 'chrome', headless: true })
  const ctx = await browser.newContext({ viewport: { width: 1920, height: 1080 }, deviceScaleFactor: 1 })
  const page = await ctx.newPage()

  // 阻塞外部字体/外链，避免沙箱网络导致 load 挂起
  await page.route(/^https?:\/\/(fonts\.googleapis\.com|fonts\.gstatic\.com|.*\.trycloudflare\.com)/, (r) => r.abort())

  for (const { path, alias } of PAGES) {
    console.log(`>> load ${path}`)
    await page.goto(BASE + path, { waitUntil: 'domcontentloaded', timeout: 30000 })
    // 等待网络空闲一个窗口 + 图表渲染
    await page.waitForTimeout(4500)
    const file = `${OUT}/${alias}.png`
    await page.screenshot({ path: file, fullPage: false })
    console.log(`   saved ${file}`)
  }

  await browser.close()
  console.log('DONE')
}

main().catch((e) => {
  console.error('FATAL:', e)
  process.exit(1)
})
