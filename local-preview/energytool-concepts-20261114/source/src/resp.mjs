// Проверка адаптива выбранных направлений: node src/resp.mjs
import fs from 'node:fs';
import path from 'node:path';
import { createRequire } from 'node:module';
const require = createRequire('/opt/npm-tools/node_modules/');
const { chromium } = require('playwright');
const root = path.resolve(path.dirname(new URL(import.meta.url).pathname), '..');
const out = path.join(root, 'png', 'resp'); fs.mkdirSync(out, { recursive: true });
const jobs = [
  ['c02-a-start', 1280, 800], ['c02-b-wait', 1280, 800], ['c02-c-answer', 1280, 800],
  ['c02-b-wait', 1920, 1080], ['c02-c-answer', 1920, 1080],
  ['c03-b-wait', 1280, 800], ['c03-b-wait', 1920, 1080],
  ['c02-m1-answer', 360, 780], ['c02-m2-sheet', 360, 780], ['c03-m1-wait', 360, 780],
];
const browser = await chromium.launch({ executablePath: '/usr/bin/google-chrome', args: ['--no-sandbox', '--font-render-hinting=none'] });
for (const [id, w, h] of jobs) {
  const ctx = await browser.newContext({ viewport: { width: w, height: h }, deviceScaleFactor: 1 });
  const p = await ctx.newPage();
  await p.goto('file://' + path.join(root, 'html', id + '.html'));
  await p.evaluate(([w, h]) => { document.body.style.width = w + 'px'; document.body.style.height = h + 'px'; }, [w, h]);
  await p.evaluate(() => document.fonts.ready);
  const bad = await p.evaluate(() => { const W = innerWidth; const o = []; for (const e of document.querySelectorAll('body *')) { const r = e.getBoundingClientRect(); if (r.width && (r.right > W + 1 || r.left < -1) && !e.closest('.mstrip')) o.push(e.className || e.tagName); } const sb = document.querySelector('.et-sidebar .et-card'); const wsp = document.querySelector('.et-workspace'); if (sb && wsp) { const a = sb.getBoundingClientRect(), b = wsp.getBoundingClientRect(); if (a.right > b.left - 8) o.push('SIDEBAR-OVERLAP ' + a.right + '>' + b.left); } return [...new Set(o)].slice(0, 6); });
  await p.screenshot({ path: path.join(out, `${id}-${w}.png`) });
  console.log(id, w + '×' + h, bad.length ? 'ISSUES ' + JSON.stringify(bad) : 'ok');
  await ctx.close();
}
await browser.close();
