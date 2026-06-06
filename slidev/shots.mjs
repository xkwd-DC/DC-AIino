// 截取实机系统各模块页面,作为答辩 deck 的静态保险页。
// 用法: PLAYWRIGHT_HOST_PLATFORM_OVERRIDE=ubuntu24.04 node shots.mjs
import { chromium } from 'playwright-chromium'
import { mkdirSync } from 'node:fs'

const BASE = process.env.BASE || 'http://localhost:5173'
const OUT = '/home/darcy/DC/DC/frontend/public/deck-shots'
const PAGES = [
  ['overview', '00-overview'],
  ['risk-map', '01-risk-map'],
  ['shap', '02-shap'],
  ['scenario', '03-scenario'],
  ['pathway', '04-pathway'],
  ['monitor', '05-monitor'],
]

mkdirSync(OUT, { recursive: true })
const browser = await chromium.launch({ args: ['--no-sandbox', '--disable-gpu', '--disable-dev-shm-usage'] })
const ctx = await browser.newContext({ viewport: { width: 1600, height: 900 }, deviceScaleFactor: 2 })
const page = await ctx.newPage()

for (const [route, name] of PAGES) {
  try {
    await page.goto(`${BASE}/${route}`, { waitUntil: 'networkidle', timeout: 45000 })
    await page.waitForTimeout(3800) // 等 ECharts 地图 / 图表 / 入场动画
    await page.screenshot({ path: `${OUT}/${name}.png` })
    console.log('OK  ', name)
  } catch (e) {
    console.log('FAIL', name, e.message)
  }
}

await browser.close()
console.log('DONE -> ' + OUT)
