// 逐关键帧检查单个 beat 的真实渲染结果（不看 Studio、不跑整片渲染）。
// 起一个以项目根为 base 的静态服务器打开 compositions/xxx.html（和 Studio 的资源解析口径一致），
// 把该 composition 的 CSS 时间轴 seek 到指定秒数并截图。
//
// 用法:
//   node tools/qa-beat.mjs compositions/beat-1-risk-map.html 0.6,2.8,4.9,5.9
//   node tools/qa-beat.mjs compositions/beat-1-risk-map.html 4.9 --scale 1
//   node tools/qa-beat.mjs compositions/beat-1-risk-map.html 4.9 --scale 1 --clip 1330,770,530,290
import { createServer } from 'node:http';
import { mkdir, readFile } from 'node:fs/promises';
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

const CHROME = 'C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe';

const [target, timesArg = '0', ...rest] = process.argv.slice(2);
if (!target) {
  console.error('usage: node tools/qa-beat.mjs <composition.html> <t1,t2,...> [--scale 0.5]');
  process.exit(1);
}
const scaleIdx = rest.indexOf('--scale');
const deviceScaleFactor = scaleIdx >= 0 ? Number(rest[scaleIdx + 1]) : 0.5;
const clipIdx = rest.indexOf('--clip');
const clip =
  clipIdx >= 0
    ? (() => {
        const [x, y, width, height] = rest[clipIdx + 1].split(',').map(Number);
        return { x, y, width, height };
      })()
    : null;

const times = timesArg
  .split(',')
  .map((s) => Number(s.trim()))
  .filter((n) => Number.isFinite(n));

const file = path.resolve(target);
const projectRoot = process.cwd();
const outDir = path.resolve('.cache/qa', path.basename(file, '.html'));
await mkdir(outDir, { recursive: true });

// ── 静态服务器：根 = 项目根，HTML 注入 <base href="/">（Studio 同款解析口径） ──────
const MIME = {
  '.html': 'text/html; charset=utf-8',
  '.css': 'text/css; charset=utf-8',
  '.js': 'text/javascript; charset=utf-8',
  '.mjs': 'text/javascript; charset=utf-8',
  '.json': 'application/json; charset=utf-8',
  '.png': 'image/png',
  '.jpg': 'image/jpeg',
  '.jpeg': 'image/jpeg',
  '.svg': 'image/svg+xml',
  '.wav': 'audio/wav',
  '.mp3': 'audio/mpeg',
  '.woff2': 'font/woff2',
};

const server = createServer(async (req, res) => {
  try {
    const urlPath = decodeURIComponent((req.url ?? '/').split('?')[0]);
    const abs = path.join(projectRoot, urlPath);
    if (!abs.startsWith(projectRoot)) {
      res.writeHead(403).end('forbidden');
      return;
    }
    let body = await readFile(abs);
    const ext = path.extname(abs).toLowerCase();
    if (ext === '.html') {
      body = Buffer.from(
        body.toString('utf8').replace('<head>', '<head>\n    <base href="/" />'),
        'utf8',
      );
    }
    res.writeHead(200, { 'content-type': MIME[ext] ?? 'application/octet-stream' });
    res.end(body);
  } catch {
    res.writeHead(404).end('not found');
  }
});
await new Promise((resolve) => server.listen(0, '127.0.0.1', resolve));
const baseUrl = `http://127.0.0.1:${server.address().port}/`;

const browser = await puppeteer.launch({
  executablePath: CHROME,
  headless: 'new',
  args: ['--force-device-scale-factor=1', '--hide-scrollbars', '--disable-lcd-text'],
});

const page = await browser.newPage();
await page.setViewport({ width: 1920, height: 1080, deviceScaleFactor });

const consoleErrors = [];
page.on('console', (msg) => {
  if (msg.type() === 'error') consoleErrors.push(msg.text());
});

const rel = path.relative(projectRoot, file).split(path.sep).join('/');
await page.goto(baseUrl + rel, { waitUntil: 'networkidle2', timeout: 60000 });
await page.evaluate(() => document.fonts.ready);
await page.evaluate(() =>
  Promise.all(
    Array.from(document.images).map((img) => (img.complete ? null : img.decode().catch(() => null))),
  ),
);

const meta = await page.evaluate(() => ({
  timelines: Object.keys(window.__timelines ?? {}),
  compositionIds: Array.from(document.querySelectorAll('[data-composition-id]')).map((el) =>
    el.getAttribute('data-composition-id'),
  ),
  brokenImages: Array.from(document.images)
    .filter((img) => !img.naturalWidth)
    .map((img) => img.getAttribute('src')),
}));

const tlName = meta.timelines[0];
if (!tlName) {
  console.error('no window.__timelines registered — 时间轴脚本没跑起来');
  await browser.close();
  process.exit(1);
}

for (const t of times) {
  await page.evaluate(
    (name, time) => {
      window.__timelines[name].pause();
      window.__timelines[name].seek(time);
    },
    tlName,
    t,
  );
  await new Promise((r) => setTimeout(r, 260));
  const out = path.join(
    outDir,
    `t${String(t).replace('.', '_')}${clip ? '-crop' : ''}.png`,
  );
  await page.screenshot(clip ? { path: out, clip } : { path: out });
  console.log(`t=${t.toFixed(2)}s → ${path.relative(process.cwd(), out)}`);
}

console.log(`timeline: ${tlName} (${meta.timelines.length} registered), 时长 ${await page.evaluate(
  (name) => window.__timelines[name].duration().toFixed(3),
  tlName,
)}s`);
if (meta.brokenImages.length) console.log(`⚠ 图片没加载: ${meta.brokenImages.join(', ')}`);
if (consoleErrors.length) console.log(`⚠ console errors: ${consoleErrors.slice(0, 8).join(' | ')}`);

await browser.close();
server.close();
