// 逐路由截图：给 promo 视频准备高清素材
// 用法: node tools/shoot.mjs
import { mkdir, writeFile } from 'node:fs/promises';
import { createRequire } from 'node:module';
import path from 'node:path';

// puppeteer-core 不在本工程 node_modules 里，借用 hyperframes CLI 自带的那份。
// 用 HF_MODULES 覆盖，或在 npx 缓存里自动探测。
const require = createRequire(
  path.join(
    process.env.HF_MODULES ??
      path.join(process.env.LOCALAPPDATA ?? '', 'npm-cache', '_npx', '702923228c2ce1e6', 'node_modules'),
    'noop.js',
  ),
);
const puppeteer = require('puppeteer-core');

const CHROME = 'C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe';
const BASE = 'http://localhost:5173';
const OUT = path.resolve('shots');

const ROUTES = [
  { name: '00-overview', route: '/overview' },
  { name: '01-risk-map', route: '/risk-map' },
  { name: '02-shap', route: '/shap' },
  { name: '03-scenario', route: '/scenario' },
  { name: '04-pathway', route: '/pathway' },
  { name: '05-monitor', route: '/monitor' },
  { name: '06-chat', route: '/chat' },
];

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

await mkdir(OUT, { recursive: true });

const browser = await puppeteer.launch({
  executablePath: CHROME,
  headless: 'new',
  args: ['--force-device-scale-factor=1', '--hide-scrollbars', '--disable-lcd-text'],
});

const page = await browser.newPage();
await page.setViewport({ width: 1920, height: 1080, deviceScaleFactor: 2 });

const report = [];

for (const { name, route } of ROUTES) {
  const url = `${BASE}${route}`;
  await page.goto(url, { waitUntil: 'networkidle2', timeout: 60000 });
  // 等 ECharts 画完 + 入场动画落定
  await page.evaluate(() => document.fonts.ready);
  await sleep(3500);

  const meta = await page.evaluate(() => ({
    title: document.title,
    h1: document.querySelector('h1')?.innerText?.trim() ?? '',
    h2: document.querySelector('h2')?.innerText?.trim() ?? '',
    canvases: document.querySelectorAll('canvas').length,
    scrollHeight: document.documentElement.scrollHeight,
  }));

  const viewportPath = path.join(OUT, `${name}.png`);
  await page.screenshot({ path: viewportPath });

  const fullPath = path.join(OUT, `${name}-full.png`);
  await page.screenshot({ path: fullPath, fullPage: true });

  report.push({ name, route, ...meta });
  console.log(
    `${name.padEnd(12)} ${route.padEnd(11)} h2="${meta.h2}" canvas=${meta.canvases} pageH=${meta.scrollHeight}`,
  );
}

await writeFile(path.join(OUT, 'index.json'), JSON.stringify(report, null, 2), 'utf8');
await browser.close();
console.log(`\nDONE → ${OUT}`);
