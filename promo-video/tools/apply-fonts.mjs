// 把 assets/fonts/local.css（子集字体，~1KB）内联进每个 composition，
// 并确保 GSAP 指向本地文件、Google Fonts 的外链已清掉。
//
// 为什么不内联 build-vendor.mjs 生成的 fonts.css：那份含 208 个 @font-face
// unicode-range 分片、共 970KB，渲染器会报 "Invalid array length" 且导航超时。
//
// 用法: node tools/apply-fonts.mjs
import { readFileSync, writeFileSync, readdirSync, existsSync } from 'node:fs';
import path from 'node:path';

const ROOT = path.resolve('.');
const LOCAL_CSS = path.join(ROOT, 'assets/fonts/local.css');

if (!existsSync(LOCAL_CSS)) {
  console.error('assets/fonts/local.css 不存在，先跑: python tools/build-fonts-local.py');
  process.exit(1);
}
const fontCss = readFileSync(LOCAL_CSS, 'utf8').trim();
const block = `<style id="local-fonts">\n      ${fontCss.split('\n').join('\n      ')}\n    </style>`;

for (const file of readdirSync(path.join(ROOT, 'compositions')).filter((f) => f.endsWith('.html'))) {
  const full = path.join(ROOT, 'compositions', file);
  let html = readFileSync(full, 'utf8');
  const before = html.length;

  // 1) 清掉所有 Google Fonts 的外链（preconnect 与 css2 两种形态）
  html = html.replace(/[ \t]*<link[^>]*fonts\.(googleapis|gstatic)\.com[^>]*>\s*/g, '');
  html = html.replace(/[ \t]*<link\b[^>]*?href="https:\/\/fonts\.googleapis\.com\/css2[\s\S]*?>\s*/g, '');

  // 2) GSAP 指向本地
  html = html.replace(/<script src="https:\/\/cdn\.jsdelivr\.net[^"]*"><\/script>/g, '<script src="assets/vendor/gsap.min.js"></script>');

  // 3) 内联子集字体的 @font-face
  if (/<style id="local-fonts">[\s\S]*?<\/style>/.test(html)) {
    html = html.replace(/[ \t]*<style id="local-fonts">[\s\S]*?<\/style>\n?/, block + '\n');
  } else {
    html = html.replace(/\n(\s*)<style>/, `\n$1${block}\n$1<style>`);
  }

  writeFileSync(full, html, 'utf8');
  const cdn = /fonts\.googleapis\.com|fonts\.gstatic\.com|cdn\.jsdelivr\.net/.test(html);
  console.log(
    `${file.padEnd(24)} ${(before / 1024).toFixed(0)}KB → ${(html.length / 1024).toFixed(0)}KB` +
      `${cdn ? '  ⚠ 仍有 CDN 引用' : '  ok'}`,
  );
}
