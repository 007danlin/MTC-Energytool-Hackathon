// Рендер PNG: node src/render.mjs [фильтр] [scale]
import fs from 'node:fs';
import path from 'node:path';
import { createRequire } from 'node:module';
const require = createRequire('/opt/npm-tools/node_modules/');
const { chromium } = require('playwright');
const root = path.resolve(path.dirname(new URL(import.meta.url).pathname), '..');
const filter = process.argv[2] || '';
const scale = Number(process.argv[3] || 2);
const outSub = process.argv[4] || 'png';
const index = JSON.parse(fs.readFileSync(path.join(root, 'tmp', 'index.json'), 'utf8')).filter(s => !filter || s.id.includes(filter));
const browser = await chromium.launch({ executablePath: '/usr/bin/google-chrome', args: ['--no-sandbox', '--font-render-hinting=none'] });
const report = [];
for (const s of index) {
  const ctx = await browser.newContext({ viewport: { width: s.w, height: s.h }, deviceScaleFactor: scale });
  const p = await ctx.newPage();
  await p.goto('file://' + path.join(root, 'html', s.id + '.html'));
  await p.evaluate(() => document.fonts.ready);
  // проверки: горизонтальное переполнение, обрезанный текст, вылет за рамку экрана
  const issues = await p.evaluate(() => {
    const out = [];
    const W = innerWidth, H = innerHeight;
    for (const el of document.querySelectorAll('body *')) {
      const cs = getComputedStyle(el);
      if (cs.display === 'none' || cs.visibility === 'hidden') continue;
      const r = el.getBoundingClientRect();
      if (!r.width || !r.height) continue;
      const tag = el.tagName.toLowerCase() + (el.className && typeof el.className === 'string' ? '.' + el.className.trim().split(/\s+/).join('.') : '');
      if (r.right > W + 1 || r.left < -1) out.push('x-overflow ' + tag + ' ' + Math.round(r.left) + '..' + Math.round(r.right));
      if (el.scrollWidth > el.clientWidth + 1 && cs.overflowX !== 'visible' && !['hidden'].includes(cs.overflowX) ) out.push('scrollX ' + tag);
      if ((cs.overflow === 'hidden' || cs.overflowY === 'hidden') && el.scrollHeight > el.clientHeight + 2 && !el.matches('.et-scroll,.clip-ok,body,html')) out.push('clipY ' + tag + ' ' + el.scrollHeight + '>' + el.clientHeight);
    }
    const sc = document.querySelector('.et-scroll');
    if (sc && sc.scrollHeight > sc.clientHeight + 2 && !sc.classList.contains('bottom')) out.push('SCROLL-OVERFLOW .et-scroll ' + sc.scrollHeight + '>' + sc.clientHeight);
    return [...new Set(out)].slice(0, 12);
  });
  if (issues.length) report.push(s.id + '\n  ' + issues.join('\n  '));
  await p.screenshot({ path: path.join(root, outSub, s.id + '.png') });
  await ctx.close();
}
await browser.close();
console.log('rendered', index.length);
if (report.length) console.log('ISSUES:\n' + report.join('\n'));
