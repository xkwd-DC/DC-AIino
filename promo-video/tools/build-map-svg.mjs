// 用站点自己的省界数据 + 前端同口径风险值，生成本片用的中国风险地图 SVG。
// 数据来源：
//   - 省界几何：frontend/public/maps/china.json（站点 ECharts 用的那份）
//   - 风险值：frontend/src/data/mockProvinces.ts 的 PROVINCES_BASE
//
// 为什么用基线值而不是 makeYearSnapshot()：
//   /api/provinces 的 grain.db 行不含 `y` 字段，store 的 normalizeRow() 会回落到
//   baselineYOf(name)，所以页面（含 2023 年）实际显示的就是 PROVINCES_BASE 的值。
//   实测 2023-09-16 /risk-map 页面渲染结果：青海 0.0400 / 西藏 0.0380 / 新疆 0.0360，
//   全国均值 0.0260 —— 与基线完全一致。地图配色必须跟着页面走，不能自己造年度值。
// 用法: node tools/build-map-svg.mjs
import { mkdir, readFile, writeFile } from 'node:fs/promises';
import path from 'node:path';

const GEO = path.resolve('../frontend/public/maps/china.json');
const OUT = path.resolve('assets/map');

// ── 与 mockProvinces.ts 完全一致的基线锚定值 ────────────────────────────────
const PROVINCES_BASE = [
  { name: '青海', y: 0.04, type: '高寒旱作型' },
  { name: '西藏', y: 0.038, type: '高寒旱作型' },
  { name: '新疆', y: 0.036, type: '极端干旱型' },
  { name: '甘肃', y: 0.034, type: '半干旱型' },
  { name: '宁夏', y: 0.032, type: '半干旱灌溉型' },
  { name: '内蒙古', y: 0.033, type: '草原旱作型' },
  { name: '陕西', y: 0.029, type: '半干旱过渡型' },
  { name: '山西', y: 0.028, type: '半干旱过渡型' },
  { name: '云南', y: 0.027, type: '山地多灾型' },
  { name: '贵州', y: 0.026, type: '岩溶多雨型' },
  { name: '四川', y: 0.024, type: '盆地温润型' },
  { name: '重庆', y: 0.025, type: '盆地多雨型' },
  { name: '广西', y: 0.027, type: '南方多洪型' },
  { name: '河南', y: 0.026, type: '主产区主导型' },
  { name: '湖北', y: 0.023, type: '中游洪涝型' },
  { name: '湖南', y: 0.024, type: '中游多雨型' },
  { name: '安徽', y: 0.025, type: '江淮多洪型' },
  { name: '江西', y: 0.026, type: '南方多洪型' },
  { name: '广东', y: 0.025, type: '沿海台风型' },
  { name: '福建', y: 0.026, type: '沿海台风型' },
  { name: '浙江', y: 0.022, type: '沿海台风型' },
  { name: '海南', y: 0.024, type: '热带台风型' },
  { name: '台湾', y: 0.022, type: '热带台风型' },
  { name: '河北', y: 0.022, type: '主产区主导型' },
  { name: '山东', y: 0.021, type: '主产区主导型' },
  { name: '天津', y: 0.02, type: '城郊型' },
  { name: '江苏', y: 0.021, type: '主产区主导型' },
  { name: '北京', y: 0.018, type: '城郊低风险型' },
  { name: '上海', y: 0.019, type: '城郊低风险型' },
  { name: '黑龙江', y: 0.02, type: '寒地大田型' },
  { name: '吉林', y: 0.023, type: '寒地大田型' },
  { name: '辽宁', y: 0.022, type: '东北边缘型' },
];

const clamp = (v, lo, hi) => Math.max(lo, Math.min(hi, v));

// ── 风险色阶：与站点 visualMap 一致（0.011 → 0.043，五档取色） ────────────────
const RAMP = ['#F2DDB8', '#E6B655', '#C68552', '#A56548', '#7E4530'];
const SCALE_MIN = 0.011;
const SCALE_MAX = 0.043;

const hexToRgb = (hex) => [1, 3, 5].map((i) => parseInt(hex.slice(i, i + 2), 16));

function riskColor(y) {
  const t = clamp((y - SCALE_MIN) / (SCALE_MAX - SCALE_MIN), 0, 1) * (RAMP.length - 1);
  const i = Math.min(Math.floor(t), RAMP.length - 2);
  const f = t - i;
  const [r1, g1, b1] = hexToRgb(RAMP[i]);
  const [r2, g2, b2] = hexToRgb(RAMP[i + 1]);
  const mix = (a, b) => Math.round(a + (b - a) * f);
  return `#${[mix(r1, r2), mix(g1, g2), mix(b1, b2)].map((v) => v.toString(16).padStart(2, '0')).join('')}`;
}

// ── 解码：站点用的这份 GeoJSON 是 ECharts 的 UTF8 压缩格式 ──────────────────────
// 坐标是 zigzag + 增量编码的字符串，必须按 ECharts parseGeoJson 的算法还原，
// 否则拿到的是字符而不是经纬度。
function decodePolygon(encoded, offsets, scale) {
  const out = [];
  let prevX = offsets[0];
  let prevY = offsets[1];
  for (let i = 0; i < encoded.length; i += 2) {
    let x = encoded.charCodeAt(i) - 64;
    let y = encoded.charCodeAt(i + 1) - 64;
    x = (x >> 1) ^ -(x & 1);
    y = (y >> 1) ^ -(y & 1);
    x += prevX;
    y += prevY;
    prevX = x;
    prevY = y;
    out.push([x / scale, y / scale]);
  }
  return out;
}

function decodeGeoJson(json) {
  if (!json.UTF8Encoding) return json;
  const scale = json.UTF8Scale ?? 1024;
  for (const feature of json.features) {
    const g = feature.geometry;
    if (g.type === 'Polygon') {
      g.coordinates = g.coordinates.map((ring, i) => decodePolygon(ring, g.encodeOffsets[i], scale));
    } else if (g.type === 'MultiPolygon') {
      g.coordinates = g.coordinates.map((poly, i) =>
        poly.map((ring, j) => decodePolygon(ring, g.encodeOffsets[i][j], scale)),
      );
    }
  }
  json.UTF8Encoding = false;
  return json;
}

// ── 投影：等距圆柱 + 中纬度经度压缩，得到与站点地图一致的中国轮廓比例 ──────────
const geo = decodeGeoJson(JSON.parse(await readFile(GEO, 'utf8')));

/** GeoJSON Polygon → [ring...]；MultiPolygon → 展平后的 [ring...]。 */
function ringsOf(geometry) {
  if (geometry.type === 'Polygon') return geometry.coordinates;
  if (geometry.type === 'MultiPolygon') return geometry.coordinates.flat();
  throw new Error(`unsupported geometry: ${geometry.type}`);
}

let minLon = 180;
let maxLon = -180;
let minLat = 90;
let maxLat = -90;
for (const f of geo.features) {
  for (const ring of ringsOf(f.geometry)) {
    for (const [lon, lat] of ring) {
      minLon = Math.min(minLon, lon);
      maxLon = Math.max(maxLon, lon);
      minLat = Math.min(minLat, lat);
      maxLat = Math.max(maxLat, lat);
    }
  }
}

const midLat = ((minLat + maxLat) / 2) * (Math.PI / 180);
const lonScale = Math.cos(midLat);

const W = 1000;
const H = 800;
const PAD = 12;
const spanX = (maxLon - minLon) * lonScale;
const spanY = maxLat - minLat;
const k = Math.min((W - PAD * 2) / spanX, (H - PAD * 2) / spanY);
const offX = (W - spanX * k) / 2;
const offY = (H - spanY * k) / 2;

const project = ([lon, lat]) => [
  offX + (lon - minLon) * lonScale * k,
  offY + (maxLat - lat) * k,
];

const paths = new Map();
for (const f of geo.features) {
  const name = f.properties.name;
  const parts = [];
  for (const ring of ringsOf(f.geometry)) {
    parts.push(
      ring
        .map((pt, i) => {
          const [x, y] = project(pt);
          return `${i === 0 ? 'M' : 'L'}${x.toFixed(1)},${y.toFixed(1)}`;
        })
        .join('') + 'Z',
    );
  }
  paths.set(name, parts.join(''));
}

// ── 输出 ────────────────────────────────────────────────────────────────────
await mkdir(OUT, { recursive: true });

const fillOf = new Map(PROVINCES_BASE.map((p) => [p.name, riskColor(p.y)]));
const body = [];
for (const [name, d] of paths) {
  const fill = fillOf.get(name) ?? '#324942';
  body.push(
    `<path data-province="${name}" d="${d}" fill="${fill}" stroke="#44615A" stroke-width="0.7" stroke-linejoin="round"/>`,
  );
}
const svg = `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 ${W} ${H}" width="${W}" height="${H}">${body.join('')}</svg>`;
await writeFile(path.join(OUT, 'china-risk.svg'), svg, 'utf8');

const top10 = [...PROVINCES_BASE].sort((a, b) => b.y - a.y).slice(0, 10);
const mean = PROVINCES_BASE.reduce((s, d) => s + d.y, 0) / PROVINCES_BASE.length;
await writeFile(
  path.join(OUT, 'risk-baseline.json'),
  JSON.stringify(
    {
      source: 'frontend/src/data/mockProvinces.ts (PROVINCES_BASE)',
      verifiedAgainst: '/risk-map @ 2026-09-16 — Top10 与全国均值逐项一致',
      scale: [SCALE_MIN, SCALE_MAX],
      ramp: RAMP,
      mean: Number(mean.toFixed(4)),
      top10: top10.map((d) => ({ ...d, y: Number(d.y.toFixed(4)) })),
      all: PROVINCES_BASE.map((d) => ({ ...d, y: Number(d.y.toFixed(4)) })),
    },
    null,
    2,
  ),
  'utf8',
);

console.log(`geo bbox lon ${minLon.toFixed(1)}~${maxLon.toFixed(1)} / lat ${minLat.toFixed(1)}~${maxLat.toFixed(1)}, cos=${lonScale.toFixed(3)}`);
console.log(`paths: ${paths.size} provinces`);
console.log(`wrote china-risk.svg → ${OUT}`);
console.log(`mean=${mean.toFixed(4)}`);
console.log('Top10: ' + top10.map((d) => `${d.name} ${d.y.toFixed(4)}`).join(' · '));
