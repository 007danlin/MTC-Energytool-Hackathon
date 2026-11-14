// Доски: mobile по концепциям, раскадровка, сравнение. node src/boards.mjs [scale]
import fs from 'node:fs';
import path from 'node:path';
import { createRequire } from 'node:module';
import { CONCEPTS, CRIT, total } from './meta.mjs';
const require = createRequire('/opt/npm-tools/node_modules/');
const { chromium } = require('playwright');
const root = path.resolve(path.dirname(new URL(import.meta.url).pathname), '..');
const dir = path.join(root, 'html', 'boards'); fs.mkdirSync(dir, { recursive: true });
const outDir = path.join(root, 'png', 'boards'); fs.mkdirSync(outDir, { recursive: true });
const page = (title, body) => `<!doctype html><html lang="ru"><head><meta charset="utf-8"><title>${title}</title><link rel="stylesheet" href="../../css/board.css"></head><body class="board">${body}</body></html>`;
const jobs = [];

for (const c of CONCEPTS) {
  const html = page(`${c.n} ${c.name} — mobile`, `<div class="bh"><span class="n">${c.n}</span><b>${c.name}</b><span class="s">Mobile. Каждый кадр — окно 390×844: то, что видно без прокрутки</span></div>
<div class="phones">${c.ms.map((m, i) => `<figure><div class="shot"><img src="../../png/${m}.png" alt=""></div><figcaption><b>${c.m[i]}</b></figcaption></figure>`).join('')}</div>`);
  fs.writeFileSync(path.join(dir, `${c.id}-mobile.html`), html); jobs.push([`${c.id}-mobile`, 2]);
}

const F = [
  ['f1-ready', '0 мс', 'Вопрос готов', 'Кнопка «Отправить» активна. Нажатие: масштаб 0,98 на 120 мс.'],
  ['f2-sent-110ms', '≈110 мс', 'Отправка', 'Вопрос уже в ленте. Приветствие ушло, поле ввода переезжает вверх: 300 мс, cubic-bezier(.2,.8,.2,1). Строка «Задача» подсвечена.'],
  ['f3-pending-520ms', '≈520 мс', 'Статус', 'Через 350 мс проявляется блок ожидания, 280 мс. «Объект» найден в тексте вопроса и подсвечен.'],
  ['f4-short-1500ms', '1,5 с', 'Короткое ожидание', 'Движется только индикатор, цикл 1,8 с. Высота блоков постоянна. Подсветка строк гаснет за 1,6 с.'],
  ['f5-useful-4600ms', '4,6 с', 'Полезное действие', 'Через 4 с под полем ввода проявляется «дополнить задачу», 280 мс. Ничего не сдвигается.'],
  ['fL-longwait-21s', '21 с', 'Долгое ожидание', 'Через 20 с меняется текст и появляются два действия. Блок растёт вниз, поле ввода переезжает плавно.'],
  ['f6-arrive-90ms', 'ответ +90 мс', 'Ответ пришёл', 'Блок ожидания заменён ответом: появление 280 мс, сдвиг 8 px. Позиция чтения сохраняется.'],
  ['f7-clarify', 'ответ +0,9 с', 'Уточнение', 'Короткие ответы — обычные кнопки. В карточке новая строка «Что уточнить» с пометкой «спрашиваю сейчас».'],
  ['f9-answer-110ms', 'итог +110 мс', 'Итоговый ответ', 'Карточка «Что дальше» идёт с задержкой 120 мс. Строки карточки задачи обновляются по очереди, шаг 140 мс.'],
  ['f10-answer', 'итог +1,2 с', 'Покой', 'Два факта, два открытых вопроса, два равноправных следующих шага.'],
  ['fE-error', 'обрыв', 'Ошибка', 'Карточка ошибки на месте блока ожидания. Видно, что сохранено и что неизвестно. Одно действие: сверить и повторить.'],
  ['fR-reduced-motion', 'меньше движения', 'Тот же момент без движения', 'Смена через прозрачность 100 мс, без сдвигов и подсветки. Новая строка помечена статичной чертой слева.'],
];
fs.writeFileSync(path.join(dir, 'storyboard.html'), page('Раскадровка', `<div class="bh"><span class="n">A</span><b>Живая задача: отправка → ожидание → ответ</b><span class="s">Кадры сняты с работающего прототипа selected/prototype.html</span></div>
<div class="sb">${F.map(([f, t, h, d]) => `<figure><div class="shot"><img src="../../png/story/${f}.png" alt=""></div><figcaption><b><span class="t">${t}</span>${h}</b>${d}</figcaption></figure>`).join('')}</div>
<p class="legend">Пороги 350 мс, 4 с и 20 с — проектные допущения, а не замеренная скорость модели. Сценарий и ответы в прототипе записаны заранее. Декоративная активность здесь одна — индикатор «три деления»; всё остальное на экране либо слова самого пользователя, либо факт, известный клиенту (время отправки, прошедшее время), либо пришедший ответ. Этапов «ищу документы» и процентов нет: сервер их не присылает.</p>`));
jobs.push(['storyboard', 1.5]);

const sel = { c02: ['Основное', ''], c03: ['Альтернатива', 'alt'] };
fs.writeFileSync(path.join(dir, 'comparison.html'), page('Сравнение концепций', `<div class="bh"><b>EnergyTool · ИИ-консультант: восемь направлений развития интерфейса</b></div>
<p class="cmp-intro">Одна история на всех экранах: рост счетов на складе. Столбцы — старт, первое ожидание, готовый ответ и mobile 390 px. Оценки — экспертное мнение по шкале 1–5 с весами из задания; это не результаты исследования. Тексты ответов — макетный контент.</p>
<div class="cmp-head"><span>Концепция</span><span>Старт</span><span>Ожидание</span><span>Ответ</span><span>Mobile 390×844</span></div>
${CONCEPTS.map(c => `<div class="cmp-row"><div><span class="n">${c.n}</span><h3>${c.name}</h3>${sel[c.id] ? `<span class="badge ${sel[c.id][1]}">${sel[c.id][0]}</span>` : ''}<p class="hyp">${c.hyp}</p><p class="risk">Риск: ${c.risk}</p>
<div class="score"><b>${total(c.s).toFixed(2).replace('.', ',')}</b><span>из 5 по весам задания</span></div><div class="sbars">${Object.entries(CRIT).map(([k, l]) => `<span>${l}</span><i><b style="width:${c.s[k] * 20}%"></b></i><em>${String(c.s[k]).replace('.', ',')}</em>`).join('')}</div></div>
${c.shots.map(s => `<div class="shot"><img src="../../png/${s}.png" alt=""></div>`).join('')}
<div class="mpair">${c.ms.map(m => `<div class="shot"><img src="../../png/${m}.png" alt=""></div>`).join('')}</div></div>`).join('')}`));
jobs.push(['comparison', 1.5]);

const only = process.argv[2] || '';
const browser = await chromium.launch({ executablePath: '/usr/bin/google-chrome', args: ['--no-sandbox', '--font-render-hinting=none'] });
for (const [id, scale] of jobs) {
  if (only && !id.includes(only)) continue;
  const ctx = await browser.newContext({ viewport: { width: 2600, height: 1200 }, deviceScaleFactor: scale });
  const p = await ctx.newPage();
  await p.goto('file://' + path.join(dir, id + '.html'));
  await p.evaluate(() => document.fonts.ready);
  await p.waitForLoadState('networkidle');
  await (await p.$('body')).screenshot({ path: path.join(outDir, id + '.png') });
  await ctx.close();
}
await browser.close();
console.log('boards', jobs.length);
