// Сборка пакета результатов: PNG, галерея, заметки, исходники. node src/pack.mjs "<строка про Figma>"
import fs from 'node:fs';
import path from 'node:path';
import { createRequire } from 'node:module';
import { CONCEPTS, STATES, SELECTED, MOTION, CRIT, total } from './meta.mjs';
import * as X from './text.mjs';
const require = createRequire('/opt/npm-tools/node_modules/');
const sharp = require('sharp');
const root = path.resolve(path.dirname(new URL(import.meta.url).pathname), '..');
const OUT = path.resolve(root, '..', 'out', 'EnergyTool-concepts-2026-11-14');
fs.rmSync(OUT, { recursive: true, force: true });
const mk = d => fs.mkdirSync(path.join(OUT, d), { recursive: true });
const cp = (a, b) => { fs.mkdirSync(path.dirname(path.join(OUT, b)), { recursive: true }); fs.copyFileSync(path.join(root, a), path.join(OUT, b)); };
const FIG = process.argv[2] || '';
const webp = async (src, name, width) => { mk('gallery-assets'); const img = sharp(path.join(root, src)); const m = await img.metadata(); await (m.width > width ? img.resize({ width }) : img).webp({ quality: 86 }).toFile(path.join(OUT, 'gallery-assets', name + '.webp')); return 'gallery-assets/' + name + '.webp'; };
const num = n => String(n).replace('.', ',');
const ST_SLUG = ['01-utochnenie', '02-dolgoe-ozhidanie', '03-oshibka', '04-net-dannyh', '05-dlinnyj-otvet', '06-kontakt', '07-proverka-zayavki', '08-zayavka-sohranena', '09-dlinnyj-kontekst'];
const ST = [...STATES, ['9-context', 'Длинный контекст', 'Списки свёрнуты до двух строк, новое всегда сверху, карточка не выходит за экран. Полный вид открывается отдельно.']];

// ——— изображения
const G = {};
cp('png/boards/comparison.png', 'comparison.png'); G.cmp = await webp('png/boards/comparison.png', 'comparison', 3252);
for (const c of CONCEPTS) {
  const d = `concepts/${c.slug}`;
  const names = ['welcome', 'waiting', 'answer'];
  c.g = { shots: [], mobile: '' };
  for (let i = 0; i < 3; i++) { cp(`png/${c.shots[i]}.png`, `${d}/${names[i]}.png`); c.g.shots.push([await webp(`png/${c.shots[i]}.png`, `${c.id}-${names[i]}`, 2160), `${d}/${names[i]}.png`]); }
  cp(`png/boards/${c.id}-mobile.png`, `${d}/mobile.png`); c.g.mobile = [await webp(`png/boards/${c.id}-mobile.png`, `${c.id}-mobile`, 1900), `${d}/mobile.png`];
  c.ms.forEach((m, i) => cp(`png/${m}.png`, `${d}/mobile-${i + 1}.png`));
}
const selImgs = { A: [], B: [] };
for (const k of ['A', 'B']) {
  const d = `selected/${SELECTED[k].slug}`;
  const ids = fs.readdirSync(path.join(root, 'png')).filter(f => f.startsWith('s' + k + '-')).sort();
  for (const f of ids) { const i = Number(f.split('-')[1]) - 1; cp('png/' + f, `${d}/${ST_SLUG[i]}.png`); selImgs[k].push([await webp('png/' + f, `s${k}-${ST_SLUG[i]}`, 2160), `${d}/${ST_SLUG[i]}.png`, ST[i]]); }
}
const dA = `selected/${SELECTED.A.slug}`;
cp('png/boards/storyboard.png', `${dA}/storyboard.png`); G.story = await webp('png/boards/storyboard.png', 'storyboard', 3624);
for (const f of fs.readdirSync(path.join(root, 'png', 'story'))) cp('png/story/' + f, `${dA}/storyboard-frames/${f}`);
G.resp = [];
for (const [f, cap] of [['c02-b-wait-1280', 'A, ожидание, 1280×800'], ['c02-c-answer-1280', 'A, ответ, 1280×800: карточка выше экрана — отсюда правило сворачивания'], ['c02-c-answer-1920', 'A, ответ, 1920×1080'], ['c03-b-wait-1280', 'B, ожидание, 1280×800'], ['c02-m1-answer-360', 'A, mobile 360×780'], ['c02-m2-sheet-360', 'A, лист задачи, 360×780'], ['c03-m1-wait-360', 'B, ожидание, 360×780']]) { cp(`png/resp/${f}.png`, `selected/responsive-check/${f}.png`); G.resp.push([await webp(`png/resp/${f}.png`, 'resp-' + f, 1920), `selected/responsive-check/${f}.png`, cap, f.includes('-360')]); }
cp('dist/prototype.html', 'selected/prototype.html');

// ——— исходники
const cpDir = (a, b, filt = () => true) => { for (const e of fs.readdirSync(path.join(root, a), { withFileTypes: true })) { if (e.isDirectory()) continue; if (filt(e.name)) cp(`${a}/${e.name}`, `${b}/${e.name}`); } };
cpDir('html', 'source/html', n => n.endsWith('.html')); cpDir('css', 'source/css'); cpDir('fonts', 'source/fonts'); cpDir('src', 'source/src'); cpDir('proto', 'source/proto'); cpDir('canvas/project', 'source/canvas/project');
for (const f of fs.readdirSync(path.join(root, 'canvas/check')).filter(f => f.endsWith('.html'))) { mk('source/static-html'); fs.writeFileSync(path.join(OUT, 'source/static-html', f), fs.readFileSync(path.join(root, 'canvas/check', f), 'utf8').replace(/file:\/\/[^')]*\/fonts\/Inter\.ttf/g, '../fonts/Inter.ttf')); }

// ——— тексты
const fig = FIG || 'Figma: файл не создан.';
const honest = X.HONEST(fig);
const dl = c => [['Гипотеза', c.hyp], ['Главное отличие', c.diff], ['Что получает пользователь', c.win], ['Что сохранено', c.kept], ['Что изменено и зачем', c.changed], ['Ожидание во времени', c.wait], ['Mobile', c.mobile], ['Основной риск', c.risk], ['Сложность внедрения', c.complexity], ['На текущем API', c.apiNow], ['Нужен новый контракт', c.apiNew]];
const ranked = [...CONCEPTS].sort((a, b) => total(b.s) - total(a.s));

// design-notes.md
let md = `# EnergyTool · ИИ-консультант: восемь направлений развития интерфейса

Подготовлено 14 ноября 2026 года по пакету design-agent-handoff-2026-11-14.

## Главное

${X.VERDICT.map(v => v).join('\n\n')}

## Что в пакете

- \`comparison.png\` — обзорная доска: 8 концепций, по 3 экрана и mobile.
- \`gallery.html\` — просмотр всего набора с пояснениями; открывается двойным щелчком.
- \`concepts/NN-название/\` — welcome, waiting, answer (1440×960, 2x) и mobile (два кадра 390×844).
- \`selected/A-zhivaya-zadacha/\`, \`selected/B-ozhidanie-s-polzoy/\` — полные состояния двух направлений.
- \`selected/prototype.html\` — работающий прототип «отправка → ожидание → ответ»; \`storyboard.png\` — кадры с него.
- \`source/\` — редактируемые исходники.

## Формат и ограничения

${honest.map(h => '- ' + h).join('\n')}

## Что сохранено

${X.KEEP.map(k => '- ' + k).join('\n')}

## Пять проблем исходного интерфейса

${X.PROBLEMS.map(([t, d], i) => `${i + 1}. **${t}.** ${d}`).join('\n')}

${X.MINOR}

## Общая основа

Эти решения не зависят от выбора концепции.

${X.BASE.map(k => '- ' + k).join('\n')}

## Матрица концепций

| ${X.MATRIX_HEAD.join(' | ')} |
|${X.MATRIX_HEAD.map(() => '---').join('|')}|
${X.MATRIX.map(r => '| ' + r.join(' | ') + ' |').join('\n')}

## Оценки

Шкала 1–5, веса из задания. Это экспертное мнение, не исследование.

| Концепция | ${Object.values(CRIT).join(' | ')} | Итог |
|---|${Object.keys(CRIT).map(() => '---:').join('|')}|---:|
${ranked.map(c => `| ${c.n} ${c.name} | ${Object.keys(CRIT).map(k => num(c.s[k])).join(' | ')} | **${num(total(c.s).toFixed(2))}** |`).join('\n')}

Веса: ожидание 20%, выразительность 20%, путь и результат 20%, преемственность 15%, mobile и состояния 15%, реалистичность 10%.

## Концепции

${CONCEPTS.map(c => `### ${c.n}. ${c.name}

${dl(c).map(([k, v]) => `- **${k}.** ${v}`).join('\n')}
- **Экраны.** \`concepts/${c.slug}/\``).join('\n\n')}

## Что взять из остальных концепций

${X.BORROW.map(([n, t]) => `- **${n}.** ${t}`).join('\n')}

## Состояния двух выбранных направлений

| Состояние | Что решено |
|---|---|
${ST.map(s => `| ${s[1]} | ${s[2]} |`).join('\n')}

«Длинный контекст» показан только для направления A: в B карточка задачи не растёт.

## Движение

Ожидание разделено на четыре слоя: декоративная активность (только индикатор «три деления»), факты клиента (время отправки, прошедшее время, слова пользователя), подтверждённый сервером результат (ответ) и макетный контент. Серверных этапов и процентов в интерфейсе нет: текущий API отдаёт только итоговый JSON.

| Приём | Триггер | Что движется | Длительность | Easing | Повтор | Влияние на layout | При ошибке | Меньше движения |
|---|---|---|---|---|---|---|---|---|
${MOTION.map(r => '| ' + r.join(' | ') + ' |').join('\n')}

## Поле ввода и кнопки

${X.COMPOSER.map(([k, v]) => `- **${k}.** ${v}`).join('\n')}

${X.BUTTONS}

## Адаптив

| Ширина | Поведение |
|---|---|
${X.RESPONSIVE.map(([k, v]) => `| ${k} | ${v} |`).join('\n')}

## Следующий шаг

| Этап | Условие | Состав |
|---|---|---|
${X.PLAN.map(r => '| ' + r.join(' | ') + ' |').join('\n')}

Что стоит проверить на людях до третьего этапа:

${X.RESEARCH.map(r => '- ' + r).join('\n')}
`;
fs.writeFileSync(path.join(OUT, 'design-notes.md'), md);

// gallery.html
const img = ([w, p], alt, cls = '') => `<a class="shot ${cls}" href="${p}" target="_blank" rel="noopener"><img loading="lazy" src="${w}" alt="${alt}"></a>`;
const html = `<!doctype html>
<html lang="ru"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>EnergyTool · ИИ-консультант — восемь направлений</title>
<style>
@font-face{font-family:ETInter;src:url('source/fonts/Inter.ttf') format('truetype');font-weight:100 900;font-display:swap}
:root{--ink:#17181c;--muted:#5f636c;--border:#e3e5ea;--bg:#f6f7f9;--accent:#d9002b}
*{box-sizing:border-box}html{scroll-behavior:smooth}
body{margin:0;font:400 16px/26px ETInter,Inter,system-ui,sans-serif;color:var(--ink);background:#fff;-webkit-font-smoothing:antialiased}
main{max-width:1240px;margin:0 auto;padding:0 32px 120px}
header.top{max-width:1240px;margin:0 auto;padding:56px 32px 24px}
h1{font-size:40px;line-height:46px;font-weight:600;margin:0;max-width:20em;text-wrap:balance}
.lede{font-size:18px;line-height:28px;color:var(--muted);margin:16px 0 0;max-width:46em}
nav{position:sticky;top:0;background:#ffffffee;backdrop-filter:blur(8px);border-bottom:1px solid var(--border);z-index:5}
nav div{max-width:1240px;margin:0 auto;padding:10px 32px;display:flex;gap:4px 18px;flex-wrap:wrap;font-size:14px;line-height:20px}
nav a{color:var(--muted);text-decoration:none;padding:4px 0}nav a:hover{color:var(--ink)}
h2{font-size:28px;line-height:34px;font-weight:600;margin:72px 0 16px;scroll-margin-top:64px}
h2 .n{color:var(--accent);font-variant-numeric:tabular-nums;margin-right:10px}
h3{font-size:18px;line-height:26px;font-weight:600;margin:32px 0 8px}
p{margin:0 0 12px;max-width:46em}ul,ol{margin:0 0 12px;padding-left:22px;max-width:46em}li{margin:4px 0}
.muted{color:var(--muted)}.small{font-size:14px;line-height:22px}
.shot{display:block;border:1px solid var(--border);border-radius:12px;overflow:hidden;background:var(--bg)}
.shot img{display:block;width:100%;height:auto}
figure{margin:20px 0 0}figcaption{font-size:14px;line-height:22px;color:var(--muted);margin-top:8px;max-width:60em}figcaption b{color:var(--ink);font-weight:600}
.g2{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:28px 24px}
.g3{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:24px}
.mob{max-width:860px}
dl{display:grid;grid-template-columns:220px minmax(0,1fr);gap:10px 24px;margin:24px 0 0;font-size:15px;line-height:24px}
dt{color:var(--muted)}dd{margin:0;max-width:44em}
.scroll{overflow-x:auto;margin:16px 0}
table{border-collapse:collapse;font-size:14px;line-height:21px;min-width:100%}
th,td{text-align:left;vertical-align:top;padding:10px 14px 10px 0;border-bottom:1px solid var(--border)}
th{font-weight:600;color:var(--muted);font-size:13px;white-space:nowrap}td.num,th.num{text-align:right;font-variant-numeric:tabular-nums;white-space:nowrap}
td:first-child{font-weight:500;white-space:nowrap}
.score{display:inline-block;font-size:14px;line-height:20px;font-weight:500;color:var(--muted);margin-left:12px;vertical-align:3px;font-variant-numeric:tabular-nums}
.badge{display:inline-block;padding:2px 9px;border-radius:7px;font-size:13px;line-height:20px;font-weight:500;background:var(--ink);color:#fff;margin-left:10px;vertical-align:4px}
.badge.alt{background:#fff;color:var(--ink);box-shadow:inset 0 0 0 1px var(--ink)}
.callout{background:var(--bg);border-radius:16px;padding:20px 24px;margin:20px 0;max-width:60em}
.callout p:last-child{margin-bottom:0}
.btn{display:inline-block;border:1px solid var(--ink);border-radius:12px;padding:11px 18px;font-size:14px;line-height:20px;font-weight:500;color:var(--ink);text-decoration:none}
.btn:hover{background:var(--bg)}
a{color:inherit}
@media(max-width:820px){.g2,.g3{grid-template-columns:1fr}dl{grid-template-columns:1fr;gap:2px 0}dd{margin-bottom:10px}h1{font-size:30px;line-height:36px}main,header.top,nav div{padding-left:18px;padding-right:18px}}
</style></head><body>
<header class="top"><h1>EnergyTool · ИИ-консультант: восемь направлений развития интерфейса</h1>
<p class="lede">Все экраны построены на текущем дизайне: Inter, светло-серая основа, красный акцент МТС, тот же каркас. На всех экранах одна история — рост счетов на складе. Нажмите на изображение, чтобы открыть PNG в полном размере.</p></header>
<nav><div><a href="#verdict">Вывод</a><a href="#compare">Сравнение</a><a href="#base">Основа</a>${CONCEPTS.map(c => `<a href="#${c.id}">${c.n}</a>`).join('')}<a href="#selA">Направление A</a><a href="#motion">Движение</a><a href="#selB">Направление B</a><a href="#resp">Адаптив</a><a href="#next">Что дальше</a><a href="#format">Формат</a></div></nav>
<main>
<h2 id="verdict">Вывод</h2>
${X.VERDICT.map(v => `<p>${v}</p>`).join('')}
<h3>Что взять из остальных</h3><ul>${X.BORROW.map(([n, t]) => `<li><b>${n}.</b> ${t}</li>`).join('')}</ul>

<h2 id="compare">Сравнение</h2>
<figure>${img([G.cmp, 'comparison.png'], 'Обзорная доска восьми концепций')}<figcaption>Оценки — экспертное мнение по шкале 1–5 с весами из задания, не результаты исследования.</figcaption></figure>
<div class="scroll"><table><thead><tr><th>Концепция</th>${Object.values(CRIT).map(c => `<th class="num">${c}</th>`).join('')}<th class="num">Итог</th></tr></thead><tbody>
${ranked.map(c => `<tr><td>${c.n} ${c.name}</td>${Object.keys(CRIT).map(k => `<td class="num">${num(c.s[k])}</td>`).join('')}<td class="num"><b>${num(total(c.s).toFixed(2))}</b></td></tr>`).join('')}</tbody></table></div>
<p class="small muted">Веса: ожидание 20%, выразительность 20%, путь и результат 20%, преемственность 15%, mobile и состояния 15%, реалистичность 10%.</p>
<h3>Матрица</h3>
<div class="scroll"><table><thead><tr>${X.MATRIX_HEAD.map(h => `<th>${h}</th>`).join('')}</tr></thead><tbody>${X.MATRIX.map(r => `<tr>${r.map(c => `<td>${c}</td>`).join('')}</tr>`).join('')}</tbody></table></div>

<h2 id="base">Основа</h2>
<div class="g2"><div><h3>Что сохранено</h3><ul>${X.KEEP.map(k => `<li>${k}</li>`).join('')}</ul></div>
<div><h3>Пять проблем исходника</h3><ol>${X.PROBLEMS.map(([t, d]) => `<li><b>${t}.</b> ${d}</li>`).join('')}</ol><p class="small muted">${X.MINOR}</p></div></div>
<h3>Общие решения для любой концепции</h3><ul>${X.BASE.map(k => `<li>${k}</li>`).join('')}</ul>

${CONCEPTS.map(c => `<h2 id="${c.id}"><span class="n">${c.n}</span>${c.name}<span class="score">${num(total(c.s).toFixed(2))} из 5</span>${c.id === 'c02' ? '<span class="badge">Основное</span>' : c.id === 'c03' ? '<span class="badge alt">Альтернатива</span>' : ''}</h2>
<p>${c.hyp}</p>
${['Старт', 'Ожидание после первого вопроса', 'Готовый ответ и следующий шаг'].map((t, i) => `<figure>${img(c.g.shots[i], `${c.n} ${c.name}: ${t}`)}<figcaption><b>${t}.</b> 1440×960</figcaption></figure>`).join('')}
<figure class="mob">${img(c.g.mobile, `${c.n} ${c.name}: mobile`)}<figcaption><b>Mobile.</b> ${c.m.join('. ')}. Окно 390×844 зафиксировано.</figcaption></figure>
<dl>${dl(c).slice(1).map(([k, v]) => `<dt>${k}</dt><dd>${v}</dd>`).join('')}</dl>`).join('\n')}

<h2 id="selA"><span class="n">A</span>Живая задача: все состояния<span class="badge">Основное</span></h2>
<p>Направление 02, доведённое до полного пути: от уточнения до сохранённой заявки. Карточка задачи остаётся на месте в каждом состоянии, включая ошибку.</p>
<div class="g2">${selImgs.A.map(([w, p, s]) => `<figure>${img([w, p], 'A: ' + s[1])}<figcaption><b>${s[1]}.</b> ${s[2]}</figcaption></figure>`).join('')}</div>

<h2 id="motion">Движение: отправка → ожидание → ответ</h2>
<div class="callout"><p><b>Работающий прототип.</b> Откройте <a href="selected/prototype.html">selected/prototype.html</a>: в нём четыре сценария (быстрый ответ, долгий, очень долгий, обрыв с повтором) и переключатель «меньше движения». Ответы записаны заранее, задержки — проектные допущения.</p><p><a class="btn" href="selected/prototype.html" target="_blank" rel="noopener">Открыть прототип</a></p></div>
<figure>${img([G.story, `selected/${SELECTED.A.slug}/storyboard.png`], 'Раскадровка')}<figcaption>Кадры сняты с прототипа в указанные моменты. Отдельные кадры лежат в selected/${SELECTED.A.slug}/storyboard-frames.</figcaption></figure>
<p>Ожидание разделено на четыре слоя: декоративная активность — только индикатор «три деления»; факты клиента — время отправки, прошедшее время, слова пользователя; подтверждённый сервером результат — ответ; макетный контент. Серверных этапов и процентов нет: текущий API отдаёт только итоговый JSON.</p>
<div class="scroll"><table><thead><tr>${['Приём', 'Триггер', 'Что движется', 'Длительность', 'Easing', 'Повтор', 'Влияние на layout', 'При ошибке', 'Меньше движения'].map(h => `<th>${h}</th>`).join('')}</tr></thead><tbody>${MOTION.map(r => `<tr>${r.map(c => `<td>${c}</td>`).join('')}</tr>`).join('')}</tbody></table></div>
<h3>Поле ввода</h3><ul>${X.COMPOSER.map(([k, v]) => `<li><b>${k}.</b> ${v}</li>`).join('')}</ul><p class="small muted">${X.BUTTONS}</p>

<h2 id="selB"><span class="n">B</span>Ожидание с пользой: все состояния<span class="badge alt">Альтернатива</span></h2>
<p>Направление 03. В доработке оно получило общее правило «поле ввода следует за лентой», чтобы после ответа экран снова не пустел.</p>
<div class="g2">${selImgs.B.map(([w, p, s]) => `<figure>${img([w, p], 'B: ' + s[1])}<figcaption><b>${s[1]}.</b> ${s[2]}</figcaption></figure>`).join('')}</div>

<h2 id="resp">Адаптив</h2>
<div class="scroll"><table><thead><tr><th>Ширина</th><th>Поведение</th></tr></thead><tbody>${X.RESPONSIVE.map(([k, v]) => `<tr><td>${k}</td><td>${v}</td></tr>`).join('')}</tbody></table></div>
<div class="g2">${G.resp.filter(r => !r[3]).map(([w, p, cap]) => `<figure>${img([w, p], cap)}<figcaption>${cap}</figcaption></figure>`).join('')}</div>
<div class="g3" style="max-width:900px;margin-top:24px">${G.resp.filter(r => r[3]).map(([w, p, cap]) => `<figure>${img([w, p], cap)}<figcaption>${cap}</figcaption></figure>`).join('')}</div>

<h2 id="next">Что дальше</h2>
<div class="scroll"><table><thead><tr><th>Этап</th><th>Условие</th><th>Состав</th></tr></thead><tbody>${X.PLAN.map(r => `<tr>${r.map(c => `<td>${c}</td>`).join('')}</tr>`).join('')}</tbody></table></div>
<h3>Что проверить на людях до третьего этапа</h3><ul>${X.RESEARCH.map(r => `<li>${r}</li>`).join('')}</ul>

<h2 id="format">Формат и ограничения</h2>
<ul>${honest.map(h => `<li>${h}</li>`).join('')}</ul>
</main></body></html>`;
fs.writeFileSync(path.join(OUT, 'gallery.html'), html);

fs.writeFileSync(path.join(OUT, 'README.txt'), `EnergyTool · ИИ-консультант — восемь направлений развития интерфейса
14 ноября 2026

С чего начать
  gallery.html      — весь набор с пояснениями, открывается двойным щелчком
  comparison.png    — обзорная доска
  design-notes.md   — объяснения, оценки, движение, адаптив, план внедрения

Папки
  concepts/NN-название/   welcome.png, waiting.png, answer.png (1440×960, 2x),
                          mobile.png (два кадра 390×844), mobile-1.png, mobile-2.png
  selected/A-zhivaya-zadacha/      основное направление: 9 состояний, storyboard.png, кадры
  selected/B-ozhidanie-s-polzoy/   альтернативное направление: 8 состояний
  selected/prototype.html          работающий прототип «отправка → ожидание → ответ»
  selected/responsive-check/       проверка на 1280, 1920 и 360 px
  gallery-assets/                  уменьшенные копии для галереи

Исходники (source/)
  html/ + css/ + fonts/   каждый экран отдельным HTML на общих стилях; правьте CSS — меняются все экраны
  src/                    генератор экранов (Node.js): build.mjs собирает html, render.mjs снимает PNG
  static-html/            те же экраны одним файлом с inline-стилями — для импорта в Figma и другие редакторы
  canvas/project/         артборды канвы Claude Design (*.dc.html) и её индекс
  proto/                  исходники прототипа

${honest.map(h => '• ' + h).join('\n')}
`);
const count = d => fs.readdirSync(path.join(OUT, d), { recursive: true }).length;
console.log('packed →', OUT, '| files', count('.'));
