// 05 «Ответ как рабочий материал» — результат оформлен в короткий вывод, проверочные пункты и следующий шаг.
import { ic, T, header, sideNote, user, bot, composer, mcomposer, footer, bars } from './lib.mjs';
const C = 'c05';
const sidebar = inner => `<aside class="et-sidebar"><p class="et-eyebrow">КОНСУЛЬТАЦИЯ</p><section class="et-card et-focus">${inner}</section>${sideNote()}</aside>`;
const focusStart = `<h2>Ваша задача<br>в фокусе</h2><p>Учёт, расходы и потери электроэнергии</p>`;
const focusWait = `<h2>Ваша задача<br>в фокусе</h2><div class="f-block"><span class="cap muted">Ваш вопрос</span><p class="f-quote">${T.q1}</p></div>`;
const focusAnswer = `<h2>Ваша задача<br>в фокусе</h2><div class="f-block"><span class="cap muted">Задача</span><p class="f-quote">Понять, почему выросли счета на складе</p></div><div class="f-block f-out"><span class="cap muted">В последнем ответе</span><ul><li>${ic('target', 16)}Вывод</li><li>${ic('checkCircle', 16)}2 пункта на проверку</li><li>${ic('arrowRight', 16)}Следующий шаг</li></ul></div>`;

const fmt = `<section class="fmt"><div class="fmt-head"><b class="label">Каким будет ответ</b><span class="cap muted">Рабочий материал, а не сплошной текст</span></div><div class="fmt-grid">
<div><span class="fi">${ic('target', 18)}</span><b>Короткий вывод</b><p>Главное — в одной-двух фразах</p></div>
<div><span class="fi">${ic('checkCircle', 18)}</span><b>Что проверить</b><p>Пункты, которые можно отметить или обсудить</p></div>
<div><span class="fi">${ic('arrowRight', 18)}</span><b>Следующий шаг</b><p>Продолжить разговор или передать задачу специалисту</p></div>
</div></section>`;

const prep = (m = false) => `<section class="sheet-a prep"><i class="runline"><b></b></i>
<div class="row between"><span class="label">${T.label}</span><span class="row st">${bars()}<span>Готовлю ответ…</span><span class="timer">0:12</span></span></div>
<p class="et-hint">${T.wait}</p>
<div class="kinds-wrap"><p class="label">Ответ придёт в одном из трёх видов</p><ul class="kinds">
<li><span class="fi">${ic('question', 18)}</span><b>Уточняющий вопрос</b><p>Если для ответа пока не хватает данных</p></li>
<li><span class="fi">${ic('checkCircle', 18)}</span><b>Рекомендации</b><p>Вывод, что проверить и следующий шаг</p></li>
<li><span class="fi">${ic('info', 18)}</span><b>«В базе нет данных»</b><p>Скажу прямо и предложу специалиста</p></li>
</ul></div>
<p class="cap muted prep-foot">Вопрос остаётся в диалоге. Следующее сообщение можно писать уже сейчас.</p></section>`;

const sheet = (m = false) => `<section class="sheet-a">
<div class="row between"><span class="label">${T.label}</span><span class="row"><span class="chip soft">Рекомендации</span><button class="iconbtn" aria-label="Скопировать">${ic('copy', 18)}</button></span></div>
<p class="lead">Начните со сравнения счетов и показаний за сопоставимые периоды.</p>
<div class="sec"><span class="sec-k">Что проверить</span><ul class="checks">
<li><span class="box"></span><span class="grow">Менялся ли режим работы склада</span><button class="link u">Ответить</button></li>
<li><span class="box"></span><span class="grow">Менялся ли состав оборудования</span><button class="link u">Ответить</button></li></ul></div>
<div class="sec"><span class="sec-k">Следующий шаг</span><p>Обсудить, нужен ли более подробный учёт.</p>
<div class="acts"><button class="btn primary">Подготовить обращение специалисту</button><button class="btn">Продолжить консультацию</button></div></div>
<div class="basis"><span class="cap muted">Опирался на ваши слова</span><span class="chip soft">«Только общая сумма»</span><span class="chip soft">«Показания вручную раз в месяц»</span></div>
</section>`;

export const screens = [
  {
    id: 'c05-a-start', concept: C, title: '05 Ответ как рабочий материал — старт',
    body: `${header()}
${sidebar(focusStart)}
<main class="et-workspace"><div class="et-scroll">
<section class="et-welcome"><p class="et-eyebrow">КОНСУЛЬТАЦИЯ ПО ЭЛЕКТРОЭНЕРГИИ</p><h1>Что хотите решить<br>с электроэнергией?</h1><p class="et-intro">Помогу разобраться в расходах, наладить учёт и понять, где искать потери.</p>
<div class="et-suggestions"><button class="btn">Снизить расходы</button><button class="btn">Наладить учёт</button><button class="btn">Найти потери</button></div></section>
${composer({ cls: 'up', placeholder: 'Опишите вашу задачу своими словами' })}
<div class="row between under"><p class="et-hint">Подсказка подставит вопрос. Его можно изменить перед отправкой.</p><button class="link u">Оставить заявку специалисту</button></div>
${fmt}
</div>${footer()}</main>`,
  },
  {
    id: 'c05-b-wait', concept: C, title: '05 Ответ как рабочий материал — ожидание',
    body: `${header()}
${sidebar(focusWait)}
<main class="et-workspace"><div class="et-scroll">
<div class="et-messages">${user(T.q1)}${prep()}</div>
</div>
${composer({ placeholder: 'Можно писать следующее сообщение', hint: 'Отправка откроется, когда придёт ответ. Черновик сохранится.' })}
${footer()}</main>`,
  },
  {
    id: 'c05-c-answer', concept: C, title: '05 Ответ как рабочий материал — ответ',
    body: `${header()}
${sidebar(focusAnswer)}
<main class="et-workspace"><div class="et-scroll bottom fade">
<div class="et-messages">${user(T.q1)}${bot(T.clar)}${user(T.a1)}${sheet()}</div>
</div>
${composer({ placeholder: 'Ответьте на пункты или задайте свой вопрос' })}
${footer()}</main>`,
  },
  {
    id: 'c05-m1-answer', concept: C, mobile: true, w: 390, h: 844, title: '05 Ответ как рабочий материал — mobile, ответ',
    body: `${header({ mobile: true })}
<main class="et-workspace"><div class="et-scroll bottom fade">
<div class="et-messages">${user(T.a1)}${sheet(true)}</div>
</div>
<div class="m-dock">${mcomposer({ placeholder: 'Ответьте на пункты' })}</div></main>`,
  },
  {
    id: 'c05-m2-wait', concept: C, mobile: true, w: 390, h: 844, title: '05 Ответ как рабочий материал — mobile, ожидание',
    body: `${header({ mobile: true })}
<main class="et-workspace"><div class="et-scroll">
<div class="et-messages">${user(T.q1)}${prep(true)}</div>
</div>
<div class="m-dock">${mcomposer({ placeholder: 'Следующее сообщение' })}</div></main>`,
  },
];
