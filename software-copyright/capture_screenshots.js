const { chromium } = require('playwright');
const path = require('path');
const fs = require('fs');

const BASE_URL = 'http://127.0.0.1:5173';
const OUT_DIR = path.join(__dirname, '..', 'screenshots');

const pages = [
  { name: 'M00_系统总览', path: '/overview' },
  { name: 'M01_风险时空地图', path: '/risk-map' },
  { name: 'M02_SHAP归因看板', path: '/shap' },
  { name: 'M03_参数情景模拟', path: '/scenario' },
  { name: 'M04_韧性路径推荐', path: '/pathway' },
  { name: 'M05_推演监控', path: '/monitor' },
];

(async () => {
  if (!fs.existsSync(OUT_DIR)) fs.mkdirSync(OUT_DIR, { recursive: true });

  const browser = await chromium.launch({ headless: true });
  const context = await browser.newContext({
    viewport: { width: 1920, height: 1080 },
    deviceScaleFactor: 1,
  });

  for (const p of pages) {
    console.log(`Screenshot: ${p.name}`);
    const page = await context.newPage();
    try {
      await page.goto(BASE_URL + p.path, { waitUntil: 'networkidle', timeout: 15000 });
      await page.waitForTimeout(2000);
      await page.screenshot({
        path: path.join(OUT_DIR, `${p.name}.png`),
        fullPage: false,
      });
      console.log(`  OK: ${p.name}.png`);
    } catch (err) {
      console.log(`  FAIL: ${p.name} - ${err.message}`);
    } finally {
      await page.close();
    }
  }

  await browser.close();
  console.log('Done!');
})();
