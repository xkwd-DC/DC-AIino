// 读取 /risk-map 页面上真实渲染出来的 Top10 与均值，确认视频用哪套数字。
// 用法: node tools/probe-riskmap.mjs
import { createRequire } from 'node:module';
import path from 'node:path';

const require = createRequire(
  path.join(
    process.env.HF_MODULES ??
      path.join(process.env.LOCALAPPDATA ?? '', 'npm-cache', '_npx', '702923228c2ce1e6', 'node_modules'),
    'noop.js',
  ),
);
const puppeteer = require('puppeteer-core');

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const browser = await puppeteer.launch({
  executablePath: 'C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe',
  headless: 'new',
});
const page = await browser.newPage();
await page.setViewport({ width: 1920, height: 1080, deviceScaleFactor: 2 });
await page.goto('http://localhost:5173/risk-map', { waitUntil: 'networkidle2', timeout: 60000 });
await sleep(4000);

const read = () =>
  page.evaluate(() => {
    const rows = [...document.querySelectorAll('.top10-body li')].map((li) => li.innerText.replace(/\s+/g, ' ').trim());
    const body = document.body.innerText;
    const mean = body.match(/当前年份全国均值\s*([\d.]+)/)?.[1] ?? null;
    const year = body.match(/YEAR[^\d]*(\d{4})/)?.[1] ?? null;
    return { year, mean, rows: rows.slice(0, 10) };
  });

const first = await read();
console.log('default year:', first.year, 'mean:', first.mean);
console.log(first.rows.join('\n'));

// 换到 2015 再看一次，确认颜色/数值是否随年份变化
const changed = await page.evaluate(() => {
  const ticks = [...document.querySelectorAll('[role="slider"], .tick, .year-tick')];
  return ticks.length;
});
console.log('slider-ish elements:', changed);

await browser.close();
