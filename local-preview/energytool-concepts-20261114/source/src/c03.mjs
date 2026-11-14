// 03 «Ожидание с пользой» — центральный блок ожидания со спокойной динамикой и одним необязательным полезным действием.
import { ic, T, header, sideNote, user, bot, composer, mcomposer, footer, bars } from './lib.mjs';
const C = 'c03';
const sidebar = inner => `<aside class="et-sidebar"><p class="et-eyebrow">КОНСУЛЬТАЦИЯ</p><section class="et-card et-focus">${inner}</section>${sideNote()}</aside>`;
const tick = on => `<span class="box ${on ? 'on' : ''}">${on ? ic('check', 14) : ''}</span>`;

const focusStart = `<h2>Ваша задача<br>в фокусе</h2><p>Учёт, расходы и потери электроэнергии</p>`;
const focusWait = `<h2>Ваша задача<br>в фокусе</h2><div class="f-block"><span class="cap muted">Ваш вопрос</span><p class="f-quote">${T.q1}</p></div>
<div class="f-data"><div class="row between"><span class="cap muted">Данные для разговора</span><span class="cap num">1 из 3</span></div><div class="f-meter"><i class="on"></i><i></i><i></i></div></div>`;
const focusAnswer = `<h2>Ваша задача<br>в фокусе</h2><div class="f-block"><span class="cap muted">Задача</span><p class="f-quote">Понять, почему выросли счета на складе</p></div>
<div class="f-data"><div class="row between"><span class="cap muted">Данные для разговора</span><span class="cap num">1 из 3</span></div>
<ul class="f-cks"><li class="on">${tick(true)}Счета за 2–3 месяца</li><li>${tick(false)}Показания за те же месяцы</li><li>${tick(false)}Что менялось на складе</li></ul></div>`;

const checklist = `<ul class="cks">
<li class="on">${tick(true)}<div><b>Счета за последние 2–3 месяца</b><p>Чтобы сравнить суммы и объём потребления</p></div></li>
<li>${tick(false)}<div><b>Показания счётчика за те же месяцы</b><p>Подойдут и ручные записи</p></div></li>
<li>${tick(false)}<div><b>Что менялось в работе склада</b><p>Режим, оборудование, площадь, арендаторы</p></div></li>
</ul>`;

const wait = (m = false) => `<section class="wait">
<div class="wait-head"><div class="row between"><div class="row">${bars()}<b>Готовлю ответ…</b></div><span class="timer">${m ? '0:12' : 'Жду ответ 0:12'}</span></div><p class="et-hint">${T.wait}</p></div>
<div class="wait-body"><p class="label">Пока готовится ответ, отметьте, что есть под рукой</p><p class="cap muted">Необязательно. Отметки не попадут в уже отправленный вопрос — добавите их следующим сообщением.</p>
${checklist}
<div class="row between wait-foot"><button class="btn sm">${ic('arrowDown', 16)}Добавить отмеченное в черновик</button><span class="cap muted num">Отмечено 1 из 3</span></div></div>
</section>`;

const next = `<section class="et-card next"><h3>Что дальше</h3><div class="next-grid">
<div><button class="btn primary wide">Подготовить обращение специалисту</button><p class="cap muted">Соберу описание задачи из нашей беседы. Вы проверите его перед сохранением.</p></div>
<div><button class="btn wide">Продолжить консультацию</button><p class="cap muted">Задайте следующий вопрос. Контакты для этого не&nbsp;нужны.</p></div>
</div></section>`;

const draftLeft = t => `<span class="row draft"><span class="chip soft">Черновик</span>${t}</span>`;

export const screens = [
  {
    id: 'c03-a-start', concept: C, title: '03 Ожидание с пользой — старт',
    body: `${header()}
${sidebar(focusStart)}
<main class="et-workspace"><div class="et-scroll">
<section class="et-welcome"><p class="et-eyebrow">КОНСУЛЬТАЦИЯ ПО ЭЛЕКТРОЭНЕРГИИ</p><h1>Что хотите решить<br>с электроэнергией?</h1><p class="et-intro">Помогу разобраться в расходах, наладить учёт и понять, где искать потери.</p></section>
<section class="topics"><div class="topics-list">
<button class="topic on">${ic('doc', 20)}<span>Снизить расходы</span>${ic('chevronRight', 18)}</button>
<button class="topic">${ic('gauge', 20)}<span>Наладить учёт</span></button>
<button class="topic">${ic('search', 20)}<span>Найти потери</span></button>
</div><div class="topics-pane"><span class="cap muted">Подставлю вопрос</span><p class="tq">У нас выросли счета за электроэнергию. С чего начать?</p>
<span class="cap muted tp">Пригодится в разговоре</span><ul class="tlist"><li>${ic('circleDash', 16)}Счета за последние 2–3 месяца</li><li>${ic('circleDash', 16)}Показания счётчика за те же месяцы</li><li>${ic('circleDash', 16)}Что менялось в работе объекта</li></ul>
<div class="row between tbtn"><button class="btn sm">Подставить вопрос</button><span class="cap muted">Если чего-то нет — начнём без этого</span></div></div></section>
${composer({ cls: 'up', placeholder: 'Или опишите задачу своими словами' })}
<div class="row between under"><p class="et-hint">Вопрос из подсказки можно изменить перед отправкой.</p><button class="link u">Оставить заявку специалисту</button></div>
</div>${footer()}</main>`,
  },
  {
    id: 'c03-b-wait', concept: C, title: '03 Ожидание с пользой — ожидание',
    body: `${header()}
${sidebar(focusWait)}
<main class="et-workspace"><div class="et-scroll">
<div class="et-messages">${user(T.q1)}${wait()}</div>
</div>
${composer({ value: 'Под рукой: счета за последние 2–3 месяца.', left: draftLeft('Отправите, когда придёт ответ') })}
${footer()}</main>`,
  },
  {
    id: 'c03-c-answer', concept: C, title: '03 Ожидание с пользой — ответ',
    body: `${header()}
${sidebar(focusAnswer)}
<main class="et-workspace"><div class="et-scroll bottom fade">
<div class="et-messages">${user(T.q1)}${bot(T.clar)}${user(T.a1)}${bot(T.ans)}</div>
<div class="et-flow">${next}</div>
</div>
${composer({ value: 'Под рукой: счета за последние 2–3 месяца.', can: true, left: draftLeft('Собран, пока вы ждали ответ. Можно отправить или стереть') })}
${footer()}</main>`,
  },
  {
    id: 'c03-m1-wait', concept: C, mobile: true, w: 390, h: 844, title: '03 Ожидание с пользой — mobile, ожидание',
    body: `${header({ mobile: true })}
<main class="et-workspace"><div class="et-scroll">
<div class="et-messages">${user(T.q1)}${wait(true)}</div>
</div>
<div class="m-dock">${mcomposer({ placeholder: 'Следующее сообщение' })}</div></main>`,
  },
  {
    id: 'c03-m2-answer', concept: C, mobile: true, w: 390, h: 844, title: '03 Ожидание с пользой — mobile, ответ',
    body: `${header({ mobile: true })}
<main class="et-workspace"><div class="et-scroll bottom fade">
<div class="et-messages">${user(T.a1)}${bot(T.ans)}</div>
<div class="et-flow">${next}</div>
</div>
<div class="m-dock"><div class="m-draft"><span class="chip soft">Черновик</span><span class="cap muted">собран, пока вы ждали</span></div>${mcomposer({ value: 'Под рукой: счета за последние 2–3 месяца.', can: true })}</div></main>`,
  },
];

export { sidebar as sidebar03, focusAnswer as focusAnswer03, focusWait as focusWait03, checklist as checklist03, next as next03, draftLeft as draftLeft03, tick as tick03 };
