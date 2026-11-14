// Конвертер экранов в артборды Design-канвы (.dc.html): правила классов переносятся в inline-стили,
// псевдоэлементы становятся настоящими элементами. node src/dc.mjs [фильтр] [fontUrl]
import fs from 'node:fs';
import path from 'node:path';
import { createRequire } from 'node:module';
const require = createRequire('/opt/npm-tools/node_modules/');
const { chromium } = require('playwright');
const root = path.resolve(path.dirname(new URL(import.meta.url).pathname), '..');
const filter = process.argv[2] || '';
const fontUrl = process.argv[3] || '../../fonts/Inter.ttf';
const index = JSON.parse(fs.readFileSync(path.join(root, 'tmp', 'index.json'), 'utf8')).filter(s => !filter || s.id.includes(filter));
const outDir = path.join(root, 'canvas', 'project'); fs.mkdirSync(outDir, { recursive: true });
const chkDir = path.join(root, 'canvas', 'check'); fs.mkdirSync(chkDir, { recursive: true });

const RESET = `*{box-sizing:border-box}body{margin:0}h1,h2,h3,h4,p,ul,ol,figure{margin:0;padding:0}ul,ol{list-style:none}button,input,textarea{font:inherit;color:inherit}svg{display:block;flex-shrink:0}`;

const inPage = ({ W, H }) => {
  const INH = new Set(['color', 'cursor', 'direction', 'letter-spacing', 'line-height', 'list-style-image', 'list-style-position', 'list-style-type', 'text-align', 'text-indent', 'text-transform', 'visibility', 'white-space', 'word-spacing', 'overflow-wrap', 'text-rendering', 'font-family', 'font-size', 'font-style', 'font-weight', 'font-stretch', 'font-variant-numeric', 'font-variant-caps', 'font-variant-ligatures', 'font-variant-east-asian', 'font-variant-alternates', 'font-variant-position', 'font-variant-emoji', 'font-kerning', 'font-optical-sizing', 'font-feature-settings', 'font-variation-settings', 'font-size-adjust', 'font-synthesis-weight', 'font-synthesis-style', 'font-synthesis-small-caps', 'font-language-override', '-webkit-font-smoothing', 'white-space-collapse', 'text-wrap-mode', 'text-wrap-style']);
  const spec = sel => {
    let s = sel.replace(/::?(before|after)/g, '').replace(/:(not|has|is|where)\(/g, '(');
    const a = (s.match(/#[\w-]+/g) || []).length;
    const b = (s.match(/\.[\w-]+|\[[^\]]+\]|:[\w-]+(\([^)]*\))?/g) || []).length;
    const c = (s.replace(/#[\w-]+|\.[\w-]+|\[[^\]]+\]|:[\w-]+(\([^)]*\))?/g, ' ').match(/[a-zA-Z][\w-]*/g) || []).length;
    return a * 10000 + b * 100 + c;
  };
  const splitSel = t => { const out = []; let d = 0, cur = ''; for (const ch of t) { if (ch === '(') d++; if (ch === ')') d--; if (ch === ',' && d === 0) { out.push(cur.trim()); cur = ''; } else cur += ch; } if (cur.trim()) out.push(cur.trim()); return out; };
  const entries = []; let order = 0; const basics = [];
  for (const sheet of document.styleSheets) for (const rule of sheet.cssRules) {
    if (!(rule instanceof CSSStyleRule)) continue;
    const plain = splitSel(rule.selectorText).filter(x => spec(x) < 100 && !/::?(before|after)$/.test(x));
    if (plain.length) basics.push(plain.join(',') + '{' + rule.style.cssText + '}');
    for (const sel of splitSel(rule.selectorText)) {
      if (/body\.live|:hover|:focus|:active/.test(sel)) continue;
      const pm = sel.match(/::?(before|after)$/);
      const base = pm ? sel.slice(0, pm.index) || '*' : sel;
      const sp = spec(sel);
      if (sp < 100 && !pm) { order++; continue; } // правила без классов остаются в <helmet> как основа страницы
      const decls = [];
      for (let i = 0; i < rule.style.length; i++) { const p = rule.style[i]; decls.push([p, rule.style.getPropertyValue(p), rule.style.getPropertyPriority(p) === 'important']); }
      entries.push({ base, pseudo: pm ? pm[1] : null, sp, order: order++, decls });
    }
  }
  const fix = v => v.replace(/100vh/g, H + 'px').replace(/100vw/g, W + 'px');
  const collect = (el, pseudo) => {
    const hit = entries.filter(e => e.pseudo === pseudo && el.matches(e.base));
    const flat = [];
    for (const e of hit) for (const [p, v, imp] of e.decls) flat.push({ p, v, w: (imp ? 1e7 : 0) + e.sp, o: e.order });
    flat.sort((a, b) => a.w - b.w || a.o - b.o);
    const m = new Map();
    for (const d of flat) { m.delete(d.p); m.set(d.p, fix(d.v)); }
    return m;
  };
  const sides = ['top', 'right', 'bottom', 'left'];
  const compress = m => {
    for (const [p, v] of [...m]) { if (v === 'initial' || v === '' || (v === 'inherit' && INH.has(p)) || p.startsWith('animation') || p.startsWith('transition') || p === 'cursor' || p === '-webkit-font-smoothing' || p === 'text-rendering') m.delete(p); }
    const box = (name, keys, short) => { if (keys.every(k => m.has(k))) { const v = keys.map(k => m.get(k)); let out; if (v.every(x => x === v[0])) out = v[0]; else if (v[0] === v[2] && v[1] === v[3]) out = v[0] + ' ' + v[1]; else out = v.join(' '); const pos = [...m.keys()].indexOf(keys[0]); const arr = [...m]; keys.forEach(k => m.delete(k)); const rest = [...m]; m.clear(); let ins = false; for (const [k, val] of arr) { if (keys.includes(k)) { if (!ins) { m.set(name, out); ins = true; } } else m.set(k, val); } } };
    box('padding', sides.map(s => 'padding-' + s)); box('margin', sides.map(s => 'margin-' + s));
    box('border-radius', ['border-top-left-radius', 'border-top-right-radius', 'border-bottom-right-radius', 'border-bottom-left-radius']);
    for (const s of sides) { const k = ['width', 'style', 'color'].map(x => `border-${s}-${x}`); if (k.every(x => m.has(x))) { const v = k.map(x => m.get(x)).join(' '); const arr = [...m]; m.clear(); let ins = false; for (const [kk, val] of arr) { if (k.includes(kk)) { if (!ins) { m.set('border-' + s, v); ins = true; } } else m.set(kk, val); } } }
    const b = sides.map(s => 'border-' + s); if (b.every(k => m.has(k)) && b.every(k => m.get(k) === m.get(b[0]))) { const v = m.get(b[0]); const arr = [...m]; m.clear(); let ins = false; for (const [kk, val] of arr) { if (b.includes(kk)) { if (!ins) { m.set('border', v); ins = true; } } else m.set(kk, val); } }
    for (const p of ['border-image-source', 'border-image-slice', 'border-image-width', 'border-image-outset', 'border-image-repeat']) m.delete(p);
    if (m.has('row-gap') && m.get('row-gap') === m.get('column-gap')) { const v = m.get('row-gap'); const arr = [...m]; m.clear(); for (const [k, val] of arr) { if (k === 'row-gap') m.set('gap', v); else if (k !== 'column-gap') m.set(k, val); } }
    if (m.has('overflow-x') && m.get('overflow-x') === m.get('overflow-y')) { const v = m.get('overflow-x'); const arr = [...m]; m.clear(); for (const [k, val] of arr) { if (k === 'overflow-x') m.set('overflow', v); else if (k !== 'overflow-y') m.set(k, val); } }
    if (m.has('flex-grow') && m.has('flex-shrink') && m.has('flex-basis')) { const v = [m.get('flex-grow'), m.get('flex-shrink'), m.get('flex-basis')].join(' '); const arr = [...m]; m.clear(); for (const [k, val] of arr) { if (k === 'flex-grow') m.set('flex', v); else if (k !== 'flex-shrink' && k !== 'flex-basis') m.set(k, val); } }
    return m;
  };
  const css = m => [...compress(m)].map(([p, v]) => `${p}: ${v}`).join('; ');
  const all = [...document.body.querySelectorAll('*')].filter(e => !(e.closest('svg') && e.tagName.toLowerCase() !== 'svg'));
  const plan = [];
  for (const el of [document.body, ...all]) {
    const own = collect(el, null);
    const inline = el.getAttribute('style');
    const before = collect(el, 'before'), after = collect(el, 'after');
    plan.push({ el, own, inline, before, after });
  }
  for (const { el, own, inline, before, after } of plan) {
    const mk = (m) => { if (!m.has('content') || m.get('content') === 'none') return null; const c = m.get('content'); m.delete('content'); const s = document.createElement('span'); s.setAttribute('aria-hidden', 'true'); if (/counter\(/.test(c)) s.textContent = String([...el.parentElement.children].filter(x => x.tagName === el.tagName).indexOf(el) + 1); else { const t = c.replace(/^"|"$/g, ''); if (t) s.textContent = t; } const st = css(m); if (st) s.setAttribute('style', st); return s; };
    const b = mk(before), a = mk(after);
    let st = css(own);
    if (el !== document.body && inline) st = st ? st + '; ' + inline : inline;
    if (el !== document.body) { if (st) el.setAttribute('style', st); else el.removeAttribute('style'); }
    else el.dataset.rootStyle = st;
    if (b) el.insertBefore(b, el.firstChild); if (a) el.appendChild(a);
  }
  for (const el of all) {
    if (el.tagName.toLowerCase() !== 'svg') el.removeAttribute('class'); else el.removeAttribute('class');
    if (el.hasAttribute('disabled')) { el.removeAttribute('disabled'); el.setAttribute('aria-disabled', 'true'); }
    if (el.tagName === 'FORM') { const d = document.createElement('div'); for (const at of el.attributes) d.setAttribute(at.name, at.value); while (el.firstChild) d.appendChild(el.firstChild); el.replaceWith(d); }
  }
  const rootStyle = document.body.dataset.rootStyle || '';
  return { rootStyle, basics: basics.join('\n'), html: document.body.innerHTML.trim() };
};

const browser = await chromium.launch({ executablePath: '/usr/bin/google-chrome', args: ['--no-sandbox', '--font-render-hinting=none'] });
const vars = {}; fs.readFileSync(path.join(root, 'css/base.css'), 'utf8').match(/:root\{([^}]*)\}/s)[1].replace(/\/\*.*?\*\//gs, '').split(';').forEach(d => { const m = d.match(/^\s*(--[\w-]+)\s*:\s*(.+)$/s); if (m) vars[m[1]] = m[2].trim(); });
const done = [];
for (const s of index) {
  const ctx = await browser.newContext({ viewport: { width: s.w, height: s.h }, deviceScaleFactor: 1 });
  const p = await ctx.newPage();
  // подставляем значения переменных, чтобы шортхенды раскладывались на конкретные свойства
  let css = ['base', 'kit', s.concept].map(f => fs.readFileSync(path.join(root, 'css', f + '.css'), 'utf8')).join('\n').replace(/\/\*[\s\S]*?\*\//g, '');
  css = css.replace(/var\((--[\w-]+)\)/g, (_, n) => vars[n] ?? 'initial').replace(/:root\{[^}]*\}/s, '').replace(/@font-face\{[^}]*\}/s, '');
  const src = fs.readFileSync(path.join(root, 'html', s.id + '.html'), 'utf8').replace(/<link rel="stylesheet"[^>]*>/g, '').replace('</head>', `<style>@font-face{font-family:ETInter;src:url('file://${root}/fonts/Inter.ttf') format('truetype');font-weight:100 900}</style><style>${css}</style></head>`);
  await p.setContent(src); await p.evaluate(() => document.fonts.ready);
  const { rootStyle, html, basics } = await p.evaluate(inPage, { W: s.w, H: s.h });
  await ctx.close();
  const rs = `${rootStyle}; position: relative; width: ${s.w}px; height: ${s.h}px; overflow: hidden`;
  const body = `<div style="${rs.replace(/"/g, '&quot;')}">\n${html}\n</div>`;
  const helmet = f => `@font-face{font-family:ETInter;src:url('${f}') format('truetype');font-weight:100 900;font-display:block}\n${basics.replace(/html,\s*body\{[^}]*\}/, 'body{margin:0}')}\nbody{-webkit-font-smoothing:antialiased}`;
  const dc = `<!doctype html>
<html lang="ru">
<head>
<meta charset="utf-8">
<title>${s.title}</title>
<script src="./support.js"></script>
</head>
<body>
<x-dc>
<helmet>
<style>
${helmet(fontUrl)}
</style>
</helmet>
${body}
</x-dc>
<script type="text/x-dc" data-dc-script data-props='{"$preview":{"width":${s.w},"height":${s.h}}}'>
class Component extends DCLogic {
renderVals() {
return {};
}
}
</script>
</body>
</html>
`;
  if (/\{\{|\}\}/.test(body + helmet(fontUrl))) throw new Error('double braces in ' + s.id);
  fs.writeFileSync(path.join(outDir, s.id + '.dc.html'), dc);
  fs.writeFileSync(path.join(chkDir, s.id + '.html'), `<!doctype html><html lang="ru"><head><meta charset="utf-8"><style>${helmet('file://' + root + '/fonts/Inter.ttf')}</style></head><body>${body}</body></html>`);
  done.push({ id: s.id, kb: (dc.length / 1024).toFixed(1) });
}
// рендер проверочных копий
for (const s of index) {
  const ctx = await browser.newContext({ viewport: { width: s.w, height: s.h }, deviceScaleFactor: 1 });
  const p = await ctx.newPage();
  await p.goto('file://' + path.join(chkDir, s.id + '.html')); await p.evaluate(() => document.fonts.ready);
  await p.screenshot({ path: path.join(chkDir, s.id + '.png') });
  await ctx.close();
}
await browser.close();
console.log(done.map(d => d.id + ' ' + d.kb + 'KB').join('\n'));
