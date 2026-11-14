// Кадры раскадровки из работающего прототипа: node src/story.mjs
import fs from 'node:fs';
import path from 'node:path';
import { createRequire } from 'node:module';
const require = createRequire('/opt/npm-tools/node_modules/');
const { chromium } = require('playwright');
const root = path.resolve(path.dirname(new URL(import.meta.url).pathname), '..');
const out = path.join(root, 'png', 'story'); fs.mkdirSync(out, { recursive: true });
const scale = Number(process.argv[2] || 1);
const browser = await chromium.launch({ executablePath: '/usr/bin/google-chrome', args: ['--no-sandbox', '--font-render-hinting=none'] });
const open = async q => { const ctx = await browser.newContext({ viewport: { width: 1440, height: 1004 }, deviceScaleFactor: scale }); const p = await ctx.newPage(); const errs = []; p.on('pageerror', e => errs.push(e.message)); p.on('console', m => m.type() === 'error' && errs.push(m.text())); await p.goto('file://' + path.join(root, 'dist/prototype.html') + q); await p.evaluate(() => document.fonts.ready); return { p, errs, ctx }; };
const shot = (p, name) => p.screenshot({ path: path.join(out, name + '.png'), clip: { x: 0, y: 44, width: 1440, height: 960 } });
const at = async (p, t0, ms) => { const d = ms - (Date.now() - t0); if (d > 0) await p.waitForTimeout(d); };

const main = (async () => {
  const { p, errs } = await open('?scenario=long');
  await shot(p, 'f0-start');
  await p.click('[data-suggest]'); await p.waitForTimeout(150);
  await shot(p, 'f1-ready');
  await p.click('.et-send'); let t0 = Date.now();
  await at(p, t0, 110); await shot(p, 'f2-sent-110ms');
  await at(p, t0, 520); await shot(p, 'f3-pending-520ms');
  await at(p, t0, 1500); await shot(p, 'f4-short-1500ms');
  await at(p, t0, 4600); await shot(p, 'f5-useful-4600ms');
  await at(p, t0, 14090); await shot(p, 'f6-arrive-90ms');
  await at(p, t0, 14900); await shot(p, 'f7-clarify');
  await p.click('[data-reply]'); t0 = Date.now();
  await at(p, t0, 1500); await shot(p, 'f8-second-wait');
  await at(p, t0, 5200 + 110); await shot(p, 'f9-answer-110ms');
  await at(p, t0, 5200 + 1200); await shot(p, 'f10-answer');
  return errs;
})();
const longw = (async () => {
  const { p, errs } = await open('?scenario=vlong');
  await p.click('[data-suggest]'); await p.click('.et-send'); const t0 = Date.now();
  await at(p, t0, 21200); await shot(p, 'fL-longwait-21s');
  return errs;
})();
const err = (async () => {
  const { p, errs } = await open('?scenario=error');
  await p.click('[data-suggest]'); await p.click('.et-send'); const t0 = Date.now();
  await at(p, t0, 7700); await shot(p, 'fE-error');
  await p.click('[data-retry]'); await p.waitForTimeout(700); await shot(p, 'fE2-retry');
  return errs;
})();
const rm = (async () => {
  const { p, errs } = await open('?scenario=fast&rm=1');
  await p.click('[data-suggest]'); await p.click('.et-send'); const t0 = Date.now();
  await at(p, t0, 900); await shot(p, 'fR-reduced-motion');
  return errs;
})();
const all = await Promise.all([main, longw, err, rm]);
await browser.close();
console.log('errors:', JSON.stringify(all.flat()));
