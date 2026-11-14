// 08 «Энергия в деталях» — небольшой фирменный мотив: линия, узлы и контакт, который замыкается, когда приходит ответ.
import { ic, T, header, sideNote, user, bot, composer, mcomposer, footer, bars } from './lib.mjs';
const C = 'c08';

// Мини-схема в тёмной карточке: вопрос —— контакт —— ответ. state: idle | wait | done | saved
const diagram = (state, w = 180) => {
  const dim = '#5d616c', on = '#ffffff', red = '#ff2d55';
  const aFill = state === 'idle' ? '#17181c' : on;
  const l1 = state === 'idle' ? dim : on;
  const closed = state === 'done' || state === 'saved';
  const l2 = closed ? on : dim;
  const blade = closed ? 'M74 26H106' : 'M74 26L101 9';
  const pulse = state === 'wait' ? `<g class="pulse"><circle cx="46" cy="26" r="9" fill="${red}" opacity=".22"/><circle cx="46" cy="26" r="4" fill="${red}"/></g>` : '';
  const b = closed ? `<circle cx="172" cy="26" r="6" fill="${red}"/>` : `<circle cx="172" cy="26" r="5.250" stroke="${dim}" fill="#17181c"/>`;
  return `<svg class="dg dg-${state}" viewBox="0 0 180 40" width="${w}" height="${w * 40 / 180}" fill="none" stroke-width="1.5" stroke-linecap="round" aria-hidden="true">
<path d="M8 26H74" stroke="${l1}"/><path d="M106 26H172" stroke="${l2}"/>
<path d="${blade}" stroke="${on}" stroke-width="2" class="blade"/><circle cx="74" cy="26" r="3" fill="${on}"/><circle cx="106" cy="26" r="3" fill="${closed ? on : dim}"/>
<circle cx="8" cy="26" r="5.250" stroke="${on}" fill="${aFill}"/>${pulse}${b}</svg>`;
};

const dark = ({ state, cap, extra = '' }) => `<aside class="et-sidebar"><p class="et-eyebrow">КОНСУЛЬТАЦИЯ</p><section class="et-card et-focus dark"><h2>Ваша задача<br>в фокусе</h2>${extra || '<p>Учёт, расходы и потери электроэнергии</p>'}
<div class="dgw">${diagram(state)}<div class="dgl"><span>вопрос</span><span>ответ</span></div></div><p class="dgc">${cap}</p></section>${sideNote()}</aside>`;

// узлы на линии ленты
const nUser = `<i class="nd nu"></i>`;
const nBot = `<i class="nd nb"></i>`;
const nNew = `<i class="nd nn"></i>`;
const nWait = `<svg class="nd nw" viewBox="0 0 32 46" width="32" height="46" fill="none" stroke="#17181c" stroke-width="1.5" stroke-linecap="round"><path d="M16 0v12"/><path d="M16 12l11 17" stroke-width="2"/><circle cx="16" cy="12" r="3" fill="#17181c"/><circle cx="16" cy="32" r="3" fill="#f6f7f9"/><path d="M16 35v11" stroke="#c3c7cf" stroke-dasharray="2 4"/><g class="rp"><circle cx="16" cy="4" r="7" fill="#d9002b" stroke="none" opacity=".18"/><circle cx="16" cy="4" r="3.500" fill="#d9002b" stroke="none"/></g></svg>`;
const u = t => `<div class="et-message et-user">${nUser}${t}</div>`;
const b = (html, n = nBot) => `<div class="et-message et-assistant">${n}<div class="et-message-label">${T.label}</div><div class="et-message-body">${html}</div></div>`;

const pending = (m = false) => `<div class="et-message et-assistant pend8">${nWait}<div class="row between"><div class="et-message-label">${T.label}</div><span class="timer">${m ? '0:12' : 'Жду ответ 0:12'}</span></div><div class="et-message-body">Готовлю ответ…</div><i class="trace"><b></b></i><p class="et-hint">${T.wait}</p></div>`;

const next = `<section class="et-card next"><i class="nd nf"></i><h3>Что дальше</h3><div class="next-grid">
<div><button class="btn primary wide">Подготовить обращение специалисту</button><p class="cap muted">Соберу описание задачи из нашей беседы. Вы проверите его перед сохранением.</p></div>
<div><button class="btn wide">Продолжить консультацию</button><p class="cap muted">Задайте следующий вопрос. Контакты для этого не&nbsp;нужны.</p></div>
</div></section>`;
const end = `<i class="nd ne"></i>`;

export const screens = [
  {
    id: 'c08-a-start', concept: C, title: '08 Энергия в деталях — старт',
    body: `${header()}
${dark({ state: 'idle', cap: 'Цепь разомкнута: жду вашего вопроса' })}
<main class="et-workspace"><div class="et-scroll hug">
<section class="et-welcome rail0"><i class="nd nu"></i><p class="et-eyebrow">КОНСУЛЬТАЦИЯ ПО ЭЛЕКТРОЭНЕРГИИ</p><h1>Что хотите решить<br>с электроэнергией?</h1><p class="et-intro">Помогу разобраться в расходах, наладить учёт и понять, где искать потери.</p>
<div class="et-suggestions"><button class="btn">Снизить расходы</button><button class="btn">Наладить учёт</button><button class="btn">Найти потери</button></div></section>
</div>
${composer({ cls: 'hug up', placeholder: 'Опишите вашу задачу своими словами', extra: end })}
<div class="below"><div class="row between under"><p class="et-hint">Подсказка подставит вопрос. Его можно изменить перед отправкой.</p><button class="link u">Оставить заявку специалисту</button></div></div>
${footer()}</main>`,
  },
  {
    id: 'c08-b-wait', concept: C, title: '08 Энергия в деталях — ожидание',
    body: `${header()}
${dark({ state: 'wait', cap: '<span class="num">Вопрос у консультанта · 0:12</span>', extra: `<div class="f-block"><span class="cap">Ваш вопрос</span><p class="f-quote">${T.q1}</p></div>` })}
<main class="et-workspace"><div class="et-scroll hug">
<div class="et-messages rail">${u(T.q1)}${pending()}</div>
</div>
${composer({ cls: 'hug', placeholder: 'Можно писать следующее сообщение', hint: 'Отправка откроется, когда придёт ответ. Черновик сохранится.', extra: end })}
<div class="below"></div>
${footer()}</main>`,
  },
  {
    id: 'c08-c-answer', concept: C, title: '08 Энергия в деталях — ответ',
    body: `${header()}
${dark({ state: 'done', cap: 'Цепь замкнута: ответ получен', extra: `<div class="f-block"><span class="cap">Задача</span><p class="f-quote">Понять, почему выросли счета на складе</p></div>` })}
<main class="et-workspace"><div class="et-scroll">
<div class="et-messages rail">${u(T.q1)}${b(T.clar)}${u(T.a1)}${b(T.ans, nNew)}${next}</div>
</div>
${composer({ extra: end })}
${footer()}</main>`,
  },
  {
    id: 'c08-m1-wait', concept: C, mobile: true, w: 390, h: 844, title: '08 Энергия в деталях — mobile, ожидание',
    body: `${header({ mobile: true })}
<main class="et-workspace"><div class="m-dark"><div class="grow"><b>Ваша задача в фокусе</b><p class="num">Вопрос у консультанта · 0:12</p></div>${diagram('wait', 120)}</div><div class="et-scroll">
<div class="et-messages rail">${u(T.q1)}${pending(true)}</div>
</div>
<div class="m-dock">${mcomposer({ placeholder: 'Следующее сообщение' })}</div></main>`,
  },
  {
    id: 'c08-m2-answer', concept: C, mobile: true, w: 390, h: 844, title: '08 Энергия в деталях — mobile, ответ',
    body: `${header({ mobile: true })}
<main class="et-workspace"><div class="m-dark"><div class="grow"><b>Ваша задача в фокусе</b><p>Ответ получен</p></div>${diagram('done', 120)}</div><div class="et-scroll bottom fade">
<div class="et-messages rail">${u(T.a1)}${b(T.ans, nNew)}${next}</div>
</div>
<div class="m-dock">${mcomposer({})}</div></main>`,
  },
];
export { diagram };
