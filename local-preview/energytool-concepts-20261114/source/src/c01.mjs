// 01 «Точная эволюция» — прежний каркас, собранный старт, устойчивый блок ожидания, полезная левая карточка.
import { ic, T, header, sideNote, user, bot, composer, mcomposer, footer, bars } from './lib.mjs';

const C = 'c01';
const sidebar = inner => `<aside class="et-sidebar"><p class="et-eyebrow">КОНСУЛЬТАЦИЯ</p><section class="et-card et-focus">${inner}</section>${sideNote()}</aside>`;

const focusEmpty = `<h2>Ваша задача<br>в фокусе</h2><p>Учёт, расходы и потери электроэнергии</p><div class="f-empty"><span class="dot off"></span><span>Здесь появится краткое описание задачи — после первого вопроса</span></div>`;
const focusQuestion = `<h2>Ваша задача<br>в фокусе</h2><div class="f-block"><span class="cap muted">Ваш вопрос</span><p class="f-quote">${T.q1}</p></div><div class="f-tags"><span class="chip soft">Снизить расходы</span></div>`;
const focusSummary = `<h2>Ваша задача<br>в фокусе</h2><div class="f-block"><span class="cap muted">Задача</span><p class="f-quote">Понять, почему выросли счета за электроэнергию на складе</p></div><div class="f-block"><span class="cap muted">Известно</span><ul class="f-list"><li>Виден только общий счёт</li><li>Показания снимают вручную раз в месяц</li></ul></div>`;

const steps = `<section class="steps"><p class="cap muted">Как пройдёт консультация</p><ol>
<li><span class="n num">1</span><b>Опишите ситуацию</b><p>Своими словами. Знать термины не&nbsp;нужно.</p></li>
<li><span class="n num">2</span><b>Отвечу и уточню детали</b><p>С опорой на базу знаний EnergyTool.</p></li>
<li><span class="n num">3</span><b>Решите, что дальше</b><p>Продолжить разговор или передать задачу специалисту.</p></li>
</ol></section>`;

const progress = `<ol class="prog">
<li class="done"><span class="m">${ic('check', 14)}</span><div><b>Вопрос отправлен</b><p class="num">в 14:32</p></div></li>
<li class="now"><span class="m"><i></i></span><div><b>Ответ консультанта</b><p>Уточняющий вопрос или первые шаги</p></div></li>
<li class="next"><span class="m"></span><div><b>Дальше решите вы</b><p>Продолжить или передать специалисту</p></div></li>
</ol>`;

const pending = `<div class="pend"><div class="row between"><span class="label">${T.label}</span><span class="timer">Жду ответ 0:12</span></div><div class="pend-main">${bars()}<span>Готовлю ответ…</span></div><p class="et-hint">${T.wait}</p></div>`;
const pendingM = `<div class="pend"><div class="row between"><span class="label">${T.label}</span><span class="timer">0:12</span></div><div class="pend-main">${bars()}<span>Готовлю ответ…</span></div><p class="et-hint">${T.wait}</p><hr class="hr">${progress}</div>`;
const stepsProgress = `<section class="steps live"><p class="cap muted">Как идёт консультация</p><ol>
<li class="done"><span class="n">${ic('check', 14)}Вопрос отправлен в 14:32</span><b>Опишите ситуацию</b><p>Вопрос у консультанта. Он останется в диалоге.</p></li>
<li class="now"><span class="n"><i class="dot"></i>Сейчас</span><b>Отвечу и уточню детали</b><p>Придёт уточняющий вопрос или первые шаги.</p></li>
<li><span class="n num">3</span><b>Решите, что дальше</b><p>Продолжить разговор или передать задачу специалисту.</p></li>
</ol></section>`;

const next = `<section class="et-card next"><h3>Что дальше</h3><div class="next-grid">
<div><button class="btn primary wide">Подготовить обращение специалисту</button><p class="cap muted">Соберу описание задачи из нашей беседы. Вы проверите его перед сохранением.</p></div>
<div><button class="btn wide">Продолжить консультацию</button><p class="cap muted">Задайте следующий вопрос. Контакты для этого не&nbsp;нужны.</p></div>
</div></section>`;

export const screens = [
  {
    id: 'c01-a-start', concept: C, title: '01 Точная эволюция — старт',
    body: `${header()}
${sidebar(focusEmpty)}
<main class="et-workspace"><div class="et-scroll">
<section class="et-welcome"><p class="et-eyebrow">КОНСУЛЬТАЦИЯ ПО ЭЛЕКТРОЭНЕРГИИ</p><h1>Что хотите решить<br>с электроэнергией?</h1><p class="et-intro">Помогу разобраться в расходах, наладить учёт и понять, где искать потери.</p></section>
${composer({ cls: 'up', placeholder: 'Опишите вашу задачу своими словами' })}
<div class="quick"><span>Или начните с частой задачи</span><button class="btn">Снизить расходы</button><button class="btn">Наладить учёт</button><button class="btn">Найти потери</button></div>
<p class="et-hint quick-hint">Подсказка подставит вопрос. Его можно изменить перед отправкой.</p>
${steps}
<div class="assist"><div><b>Нужен специалист, а не консультация?</b><p class="cap muted">Заявку можно оставить сразу, без вопросов консультанту.</p></div><button class="btn">Оставить заявку специалисту</button></div>
</div>${footer()}</main>`,
  },
  {
    id: 'c01-b-wait', concept: C, title: '01 Точная эволюция — ожидание',
    body: `${header({ busy: true })}
${sidebar(focusQuestion)}
<main class="et-workspace"><div class="et-scroll hug">
<div class="et-messages">${user(T.q1)}${pending}</div>
</div>
${composer({ cls: 'hug', placeholder: 'Можно писать следующее сообщение', hint: 'Отправка откроется, когда придёт ответ. Черновик сохранится.' })}
<div class="below">${stepsProgress}</div>
${footer()}</main>`,
  },
  {
    id: 'c01-c-answer', concept: C, title: '01 Точная эволюция — ответ',
    body: `${header()}
${sidebar(focusSummary)}
<main class="et-workspace"><div class="et-scroll">
<div class="et-messages">${user(T.q1)}${bot(T.clar)}${user(T.a1)}${bot(T.ans)}</div>
<div class="et-flow">${next}</div>
</div>
${composer({})}
${footer()}</main>`,
  },
  {
    id: 'c01-m1-wait', concept: C, mobile: true, w: 390, h: 844, title: '01 Точная эволюция — mobile, ожидание',
    body: `${header({ mobile: true, busy: true })}
<main class="et-workspace"><div class="et-scroll">
<button class="m-task">${ic('target', 18)}<span class="grow">Ваш вопрос: выросли счета на складе</span>${ic('chevronDown', 18)}</button>
<div class="et-messages">${user(T.q1)}${pendingM}</div>
</div>
<div class="m-dock">${mcomposer({ placeholder: 'Следующее сообщение' })}</div></main>`,
  },
  {
    id: 'c01-m2-answer', concept: C, mobile: true, w: 390, h: 844, title: '01 Точная эволюция — mobile, ответ',
    body: `${header({ mobile: true })}
<main class="et-workspace"><button class="m-task pinned">${ic('target', 18)}<span class="grow">Задача: рост счетов на складе</span>${ic('chevronDown', 18)}</button><div class="et-scroll bottom fade">
<div class="et-messages">${user(T.a1)}${bot(T.ans)}</div>
<div class="et-flow">${next}</div>
</div>
<div class="m-dock">${mcomposer({})}</div></main>`,
  },
];
