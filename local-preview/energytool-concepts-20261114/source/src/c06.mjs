// 06 «Старт с характером» — три направления консультации становятся тактильными карточками, связанными с полем ввода.
import { ic, T, header, sideNote, user, bot, composer, mcomposer, footer, bars } from './lib.mjs';
const C = 'c06';
const svg = (inner, w = 120, h = 80) => `<svg viewBox="0 0 120 80" width="${w}" height="${h}" fill="none" stroke="#17181c" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${inner}</svg>`;
export const ILL = {
  cost: `<path d="M28 10h38v58l-6.300-4.500-6.400 4.500-6.300-4.500-6.300 4.500-6.400-4.500L28 68V10z" fill="#fff"/><path d="M37 23h20M37 31h20M37 39h11"/><path d="M37 52h20" stroke="#d9002b" stroke-width="2.200"/><path d="M76 60l11-11 6.500 6.500L107 40" stroke="#d9002b"/><path d="M99 40h8v8" stroke="#d9002b"/>`,
  meter: `<rect x="33" y="9" width="54" height="56" rx="9" fill="#fff"/><rect x="42" y="19" width="36" height="14" rx="3"/><path d="M51 19v14M60 19v14"/><rect x="69" y="19" width="9" height="14" rx="1" fill="#d9002b" stroke="#d9002b"/><circle cx="60" cy="48" r="8"/><path d="M60 48l4.500-4.500"/><path d="M60 48v.01" stroke-width="2.400"/><path d="M47 65v8M73 65v8"/>`,
  loss: `<circle cx="16" cy="34" r="6" fill="#fff"/><circle cx="104" cy="34" r="6" fill="#fff"/><path d="M22 34h28M70 34h28"/><circle cx="60" cy="34" r="17" fill="#fff"/><path d="M72.500 46.500L84 58" stroke-width="2.200"/><path d="M47 34h7M66 34h7"/><path d="M57 39l-2.500 9M60 40v10M63 39l2.500 9" stroke="#d9002b" stroke-dasharray="1.500 4"/>`,
  doc: `<path d="M40 10h27l13 13v45H40V10z" fill="#fff"/><path d="M67 10v13h13"/><path d="M48 36h22M48 44h22M48 52h12"/><circle cx="82" cy="60" r="11" fill="#fff" stroke="#d9002b"/><path d="M77 60l3.500 3.500 6.500-7.500" stroke="#d9002b"/>`,
  chat: `<path d="M26 14h46a7 7 0 017 7v20a7 7 0 01-7 7H48L36 58V48h-10a7 7 0 01-7-7V21a7 7 0 017-7z" fill="#fff"/><path d="M34 27h30M34 35h18"/><path d="M88 38h6a7 7 0 017 7v14a7 7 0 01-7 7h-5v8l-9-8H66a7 7 0 01-7-7v-3" /><path d="M70 55h.01M80 55h.01M90 55h.01" stroke="#d9002b" stroke-width="2.600"/>`,
};

const card = ({ ill, t, d, on = false, go = 'Подставить вопрос' }) => `<button class="tcard ${on ? 'on' : ''}"><span class="till">${svg(ILL[ill])}</span><b>${t}</b><p>${d}</p><span class="tgo">${on ? ic('check', 16) + 'Вопрос подставлен' : go + ic('arrowDown', 16)}</span></button>`;
const cards = on => `<div class="tcards">
${card({ ill: 'cost', t: 'Снизить расходы', d: 'Счета растут или кажутся завышенными', on: on === 0 })}
${card({ ill: 'meter', t: 'Наладить учёт', d: 'Непонятно, где и сколько расходуется', on: on === 1 })}
${card({ ill: 'loss', t: 'Найти потери', d: 'Платите больше, чем потребляете по факту', on: on === 2 })}</div>`;

const sidebar = inner => `<aside class="et-sidebar"><p class="et-eyebrow">КОНСУЛЬТАЦИЯ</p><section class="et-card et-focus">${inner}</section>${sideNote()}</aside>`;
const focusStart = `<h2>Ваша задача<br>в фокусе</h2><p>Учёт, расходы и потери электроэнергии</p>`;
const focusTopic = extra => `<h2>Ваша задача<br>в фокусе</h2><div class="f-topic"><span class="f-ill">${svg(ILL.cost, 60, 40)}</span><div><span class="cap muted">Тема</span><b>Снизить расходы</b></div></div>${extra}`;
const fQuote = `<div class="f-block"><span class="cap muted">Ваш вопрос</span><p class="f-quote">${T.q1}</p></div>`;
const fTask = `<div class="f-block"><span class="cap muted">Задача</span><p class="f-quote">Понять, почему выросли счета на складе</p></div>`;

const tag = `<div class="ttag">${svg(ILL.cost, 36, 24)}<span>Снизить расходы</span></div>`;
const pend = (m = false) => `<section class="pend6"><div class="p6-top"><span class="p6-ill">${svg(ILL.cost, 96, 64)}<i class="scan"></i></span><div class="grow"><div class="row between"><span class="label">${T.label}</span><span class="timer">${m ? '0:12' : 'Жду ответ 0:12'}</span></div><div class="row p6-main">${bars()}<span>Готовлю ответ…</span></div><p class="et-hint">${T.wait}</p></div></div>
<div class="p6-more"><p class="label">О чём обычно разговор по этой теме</p><div class="p6-tiles">
<div><b>Что изменилось</b><p>Режим работы, оборудование, площадь</p></div>
<div><b>Как ведётся учёт</b><p>Общий счётчик или по зонам</p></div>
<div><b>С чем сравнивать</b><p>Соседние месяцы и тот же месяц год назад</p></div></div></div></section>`;

const nextCards = `<div class="ncards">
<div class="ncard"><span class="till">${svg(ILL.doc, 84, 56)}</span><div class="grow"><b>Передать задачу специалисту</b><p>Соберу обращение из нашей беседы. Вы проверите его перед сохранением.</p><button class="btn primary">Подготовить обращение</button></div></div>
<div class="ncard"><span class="till">${svg(ILL.chat, 84, 56)}</span><div class="grow"><b>Продолжить консультацию</b><p>Задайте следующий вопрос. Контакты для этого не&nbsp;нужны.</p><button class="btn">Задать вопрос</button></div></div></div>`;

const qSuggest = 'У нас выросли счета за электроэнергию. С чего начать?';

export const screens = [
  {
    id: 'c06-a-start', concept: C, title: '06 Старт с характером — старт',
    body: `${header()}
${sidebar(focusStart)}
<main class="et-workspace"><div class="et-scroll">
<section class="et-welcome"><p class="et-eyebrow">КОНСУЛЬТАЦИЯ ПО ЭЛЕКТРОЭНЕРГИИ</p><h1>Что хотите решить<br>с электроэнергией?</h1><p class="et-intro">Помогу разобраться в расходах, наладить учёт и понять, где искать потери.</p></section>
${cards(0)}
${composer({ cls: 'up', value: qSuggest, can: true, focus: true, hint: 'Вопрос подставлен из карточки. Допишите детали или отправьте как есть.' })}
<div class="row between under"><p class="et-hint">Можно не выбирать карточку и сразу описать задачу своими словами.</p><button class="link u">Оставить заявку специалисту</button></div>
</div>${footer()}</main>`,
  },
  {
    id: 'c06-b-wait', concept: C, title: '06 Старт с характером — ожидание',
    body: `${header()}
${sidebar(focusTopic(fQuote))}
<main class="et-workspace"><div class="et-scroll">
<div class="et-messages">${user(T.q1)}${pend()}</div>
</div>
${composer({ placeholder: 'Можно писать следующее сообщение', hint: 'Отправка откроется, когда придёт ответ. Черновик сохранится.' })}
${footer()}</main>`,
  },
  {
    id: 'c06-c-answer', concept: C, title: '06 Старт с характером — ответ',
    body: `${header()}
${sidebar(focusTopic(fTask))}
<main class="et-workspace"><div class="et-scroll bottom fade">
<div class="et-messages">${user(T.q1)}${bot(T.clar)}${user(T.a1)}${bot(T.ans)}</div>
<div class="et-flow"><p class="label nlabel">Что дальше</p>${nextCards}</div>
</div>
${composer({})}
${footer()}</main>`,
  },
  {
    id: 'c06-m1-start', concept: C, mobile: true, w: 390, h: 844, title: '06 Старт с характером — mobile, старт',
    body: `${header({ mobile: true })}
<main class="et-workspace"><div class="et-scroll">
<section class="et-welcome"><h1>Что хотите решить с&nbsp;электроэнергией?</h1><p class="et-intro">Выберите задачу или опишите свою.</p></section>
${cards(0)}
</div>
<div class="m-dock">${mcomposer({ value: qSuggest, can: true })}<p class="m-note">Вопрос из карточки можно изменить перед отправкой</p></div></main>`,
  },
  {
    id: 'c06-m2-wait', concept: C, mobile: true, w: 390, h: 844, title: '06 Старт с характером — mobile, ожидание',
    body: `${header({ mobile: true })}
<main class="et-workspace"><div class="et-scroll">
<div class="et-messages">${user(T.q1)}${pend(true)}</div>
</div>
<div class="m-dock">${mcomposer({ placeholder: 'Следующее сообщение' })}</div></main>`,
  },
];
