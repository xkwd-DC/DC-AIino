// 把 GSAP 与三套字体从 CDN 落到本地，并把 @font-face 内联进每个 composition。
//
// 为什么必须本地化：validate 时出现过
//   ✗ Failed to load npm/gsap@3.14.2/dist/gsap.min.js: net::ERR_CONNECTION_CLOSED
//   ✗ gsap is not defined
//   ✗ Failed to load css2: net::ERR_CONNECTION_CLOSED
// 网络一抖，动画直接不跑、字体掉回系统字体。渲染必须是可复现的。
//
// 用法: node tools/build-vendor.mjs
import { execFileSync } from 'node:child_process';
import { existsSync, readFileSync, mkdirSync, writeFileSync, readdirSync } from 'node:fs';
import path from 'node:path';

const ROOT = path.resolve('.');
const FONT_DIR = path.join(ROOT, 'assets/fonts');
const VENDOR_DIR = path.join(ROOT, 'assets/vendor');
const PROXY = 'http://127.0.0.1:7890';
const UA =
  'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36';

const GSAP_URL = 'https://cdn.jsdelivr.net/npm/gsap@3.14.2/dist/gsap.min.js';
const FONT_CSS_URL =
  'https://fonts.googleapis.com/css2?family=Noto+Serif+SC:wght@400;500;600;700&family=Noto+Sans+SC:wght@300;400;500;600;700&family=JetBrains+Mono:wght@400;500;600&display=swap';

mkdirSync(FONT_DIR, { recursive: true });
mkdirSync(VENDOR_DIR, { recursive: true });

/** curl 直连优先，失败再走本地代理：这台机器的国际出口时好时坏。 */
function curl(url, out, extra = []) {
  const base = ['-sSL', '--connect-timeout', '20', '--retry', '2', '--retry-delay', '1', url, '-o', out, ...extra];
  try {
    execFileSync('curl.exe', base, { stdio: 'pipe' });
    return true;
  } catch {
    try {
      execFileSync('curl.exe', [...base, '--proxy', PROXY], { stdio: 'pipe' });
      return true;
    } catch (err) {
      console.warn(`  ! download failed: ${url}`);
      return false;
    }
  }
}

// ── 1. GSAP ────────────────────────────────────────────────────────────────
const gsapOut = path.join(VENDOR_DIR, 'gsap.min.js');
if (!existsSync(gsapOut) || readFileSync(gsapOut).length < 10000) {
  console.log('fetching gsap…');
  curl(GSAP_URL, gsapOut);
}
console.log(`gsap.min.js ${(readFileSync(gsapOut).length / 1024).toFixed(0)} KB`);

// ── 2. 字体 CSS（带 Chrome UA 才会返回 woff2 + unicode-range）───────────────
const cssTmp = path.join(FONT_DIR, '.google-fonts.css');
console.log('fetching google fonts css…');
curl(FONT_CSS_URL, cssTmp, ['-H', `User-Agent: ${UA}`]);
let css = readFileSync(cssTmp, 'utf8');

// ── 3. 逐个 woff2 下载到 assets/fonts，并把 CSS 里的 url 改写成本地路径 ──────
const urls = [...new Set([...css.matchAll(/url\((https:\/\/[^)]+\.woff2)\)/g)].map((m) => m[1]))];
console.log(`font files referenced: ${urls.length}`);

const localName = (u) => u.split('/').pop().split('?')[0];
let downloaded = 0;
for (const u of urls) {
  const target = path.join(FONT_DIR, localName(u));
  if (existsSync(target) && readFileSync(target).length > 512) continue;
  if (curl(u, target)) downloaded += 1;
}
console.log(`downloaded ${downloaded} new font files (total ${readdirSync(FONT_DIR).length - 1})`);

css = css.replace(/url\((https:\/\/[^)]+\.woff2)\)/g, (_m, u) => `url('assets/fonts/${localName(u)}')`);

const header = `/* 由 tools/build-vendor.mjs 生成：Google Fonts 本地化，避免渲染时依赖外网。
   字体：Noto Serif SC / Noto Sans SC / JetBrains Mono。不要手改，重跑脚本即可。 */\n`;
writeFileSync(path.join(FONT_DIR, 'fonts.css'), header + css, 'utf8');
console.log(`fonts.css ${(css.length / 1024).toFixed(0)} KB`);

// ── 4. 内联进每个 composition：换掉 CDN script + 三个 Google link ───────────
const CDN_GSAP = /<script src="https:\/\/cdn\.jsdelivr\.net\/npm\/gsap@[^"]+"><\/script>/;
const GF_LINKS = /[ \t]*<link rel="preconnect" href="https:\/\/fonts\.(googleapis|gstatic)\.com"[^>]*>\n?/g;
const GF_CSS_LINK = /[ \t]*<link\s*\n?\s*href="https:\/\/fonts\.googleapis\.com\/css2[^>]*>\n?/g;

const files = readdirSync(path.join(ROOT, 'compositions')).filter((f) => f.endsWith('.html'));
for (const file of files) {
  const full = path.join(ROOT, 'compositions', file);
  let html = readFileSync(full, 'utf8');

  html = html.replace(GF_LINKS, '');
  html = html.replace(GF_CSS_LINK, '');
  html = html.replace(/[ \t]*<link[\s\S]{0,220}?fonts\.googleapis\.com\/css2[\s\S]{0,220}?\/>\n?/g, '');
  html = html.replace(CDN_GSAP, '<script src="assets/vendor/gsap.min.js"></script>');
  html = html.replace(/<script src="https:?\/?\/?cdn\.jsdelivr\.net[^"]*"><\/script>/g, '<script src="assets/vendor/gsap.min.js"></script>');

  const block = `<style id="local-fonts">\n${css}\n    </style>`;
  if (/<style id="local-fonts">[\s\S]*?<\/style>/.test(html)) {
    html = html.replace(/<style id="local-fonts">[\s\S]*?<\/style>/, block);
  } else {
    html = html.replace(/(\n\s*)<style>/, `$1${block}$1<style>`);
  }

  writeFileSync(full, html, 'utf8');
  const stillCdn = /fonts\.googleapis\.com|cdn\.jsdelivr\.net/.test(html);
  console.log(`${file}: gsap→local, fonts inlined${stillCdn ? '  ⚠ 仍有 CDN 引用' : ''}`);
}
console.log('done');
