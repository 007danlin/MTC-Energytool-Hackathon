// 07 «Диалог и план» — рядом с беседой собирается предварительный план действий; после консультации он становится итогом.
import { ic, T, header, sideNote, user, bot, composer, mcomposer, footer, bars } from './lib.mjs';
const C = 'c07';

const pstep = ({ n, t, m = '', cls = '', right = '' }) => `<li class="ps ${cls}"><span class="pn num">${cls.includes('done') ? ic('check', 14) : n}</span><div class="grow"><b>${t}</b>${m ? `<p>${m}</p>` : ''}</div>${right}</li>`;
const ghost = n => `<li class="ps ghost"><span class="pn num">${n}</span><div class="grow"><i></i><i class="s"></i></div></li>`;
const cb = `<span class="box" aria-hidden="true"></span>`;

const planStart = `<aside class="plan"><p class="et-eyebrow">КОНСУЛЬТАЦИЯ</p><h2>Ваша задача<br>в фокусе</h2><p class="plan-sub">Учёт, расходы и потери электроэнергии</p>
<div class="plan-sec"><div class="row between"><h3>План действий</h3><span class="chip dash">пока пуст</span></div>
<ol class="psteps">${ghost(1)}${ghost(2)}${ghost(3)}</ol>
<p class="cap muted plan-note">Соберу план из ответов консультанта: шаги, что известно и что стоит уточнить. Шаги можно будет отмечать, а план — скачать или передать специалисту.</p></div>
<div class="plan-foot">${sideNote()}</div></aside>`;

const planWait = `<aside class="plan"><p class="et-eyebrow">КОНСУЛЬТАЦИЯ</p><h2>Ваша задача<br>в фокусе</h2><div class="plan-q"><span class="cap muted">Ваш вопрос</span><p>${T.q1}</p></div>
<div class="plan-sec"><div class="row between"><h3>План действий</h3><span class="chip dash">собирается</span></div>
<ol class="psteps">${pstep({ n: '', t: 'Описать ситуацию', m: 'Вопрос отправлен в 14:32', cls: 'done' })}
<li class="ps wait"><span class="pn">${bars()}</span><div class="grow"><b>Жду ответ консультанта</b><p>Шаги появятся здесь, когда он их предложит</p></div></li>
${ghost(2)}</ol></div>
<div class="plan-foot">${sideNote()}</div></aside>`;

const planFull = `<aside class="plan"><p class="et-eyebrow">КОНСУЛЬТАЦИЯ</p><h2>Ваша задача<br>в фокусе</h2><p class="plan-sub ink">Понять, почему выросли счета за электроэнергию на складе</p>
<div class="plan-sec"><div class="row between"><h3>План действий</h3><span class="chip new">3 новых шага</span></div>
<ol class="psteps">
${pstep({ n: '', t: 'Описать ситуацию', m: 'Склад. Общий счёт, показания вручную раз в месяц', cls: 'done' })}
${pstep({ n: 1, t: 'Сравнить счета и показания за сопоставимые периоды', m: 'С этого стоит начать', cls: 'now', right: cb })}
${pstep({ n: 2, t: 'Выяснить, менялись ли режим работы склада и состав оборудования', cls: '', right: cb })}
${pstep({ n: 3, t: 'Обсудить, нужен ли более подробный учёт', m: 'После шагов 1 и 2', cls: '', right: cb })}
</ol>
<p class="cap muted plan-note">Предварительный план по ответам консультанта. Он меняется по ходу разговора.</p></div>
<div class="plan-acts"><button class="btn primary wide">Подготовить обращение специалисту</button><div class="row"><button class="btn grow">${ic('download', 18)}Скачать план</button><button class="btn grow">${ic('edit', 18)}Изменить</button></div><p class="cap muted">План приложу к обращению. Вы проверите его перед сохранением.</p></div></aside>`;

const pending = `<div class="pend"><div class="row between"><span class="label">${T.label}</span><span class="timer">Жду ответ 0:12</span></div><div class="pend-main">${bars()}<span>Готовлю ответ…</span></div><p class="et-hint">${T.wait}</p></div>`;
const added = `<div class="upd">${ic('list', 16)}<span>В план справа добавлены 3 шага</span></div>`;

export const screens = [
  {
    id: 'c07-a-start', concept: C, title: '07 Диалог и план — старт',
    body: `${header()}
${planStart}
<main class="et-workspace"><div class="et-scroll hug">
<section class="et-welcome"><p class="et-eyebrow">КОНСУЛЬТАЦИЯ ПО ЭЛЕКТРОЭНЕРГИИ</p><h1>Что хотите решить<br>с электроэнергией?</h1><p class="et-intro">Помогу разобраться в расходах, наладить учёт и понять, где искать потери.</p>
<div class="et-suggestions"><button class="btn">Снизить расходы</button><button class="btn">Наладить учёт</button><button class="btn">Найти потери</button></div></section>
</div>
${composer({ cls: 'hug up', placeholder: 'Опишите вашу задачу своими словами' })}
<div class="below"><div class="row between under"><p class="et-hint">Подсказка подставит вопрос. Его можно изменить перед отправкой.</p><button class="link u">Оставить заявку специалисту</button></div></div>
${footer()}</main>`,
  },
  {
    id: 'c07-b-wait', concept: C, title: '07 Диалог и план — ожидание',
    body: `${header()}
${planWait}
<main class="et-workspace"><div class="et-scroll hug">
<div class="et-messages">${user(T.q1)}${pending}</div>
</div>
${composer({ cls: 'hug', placeholder: 'Можно писать следующее сообщение', hint: 'Отправка откроется, когда придёт ответ. Черновик сохранится.' })}
<div class="below"></div>
${footer()}</main>`,
  },
  {
    id: 'c07-c-answer', concept: C, title: '07 Диалог и план — ответ',
    body: `${header()}
${planFull}
<main class="et-workspace"><div class="et-scroll hug">
<div class="et-messages">${user(T.q1)}${bot(T.clar)}${user(T.a1)}${bot(T.ans)}${added}</div>
</div>
${composer({ cls: 'hug', placeholder: 'Задайте следующий вопрос или расскажите, что выяснили' })}
<div class="below"></div>
${footer()}</main>`,
  },
  {
    id: 'c07-m1-answer', concept: C, mobile: true, w: 390, h: 844, title: '07 Диалог и план — mobile, ответ',
    body: `${header({ mobile: true })}
<main class="et-workspace"><div class="et-scroll bottom fade">
<div class="et-messages">${user(T.q1)}${bot(T.clar)}${user(T.a1)}${bot(T.ans)}</div>
</div>
<div class="m-dock"><button class="m-plan">${ic('list', 18)}<span class="grow">План действий</span><span class="chip new">3 новых шага</span>${ic('chevronUp', 18)}</button>${mcomposer({ placeholder: 'Следующий вопрос' })}</div></main>`,
  },
  {
    id: 'c07-m2-plan', concept: C, mobile: true, w: 390, h: 844, title: '07 Диалог и план — mobile, план',
    body: `${header({ mobile: true })}
<main class="et-workspace"><div class="et-scroll">
<div class="et-messages">${user(T.q1)}${bot(T.clar)}</div>
</div></main>
<div class="sheet-scrim"></div>
<div class="sheet plan-sheet"><div class="grab"></div>
<div class="row between"><h3>План действий</h3><button class="btn sm ghost" aria-label="Закрыть">${ic('close', 18)}</button></div>
<p class="cap muted">Понять, почему выросли счета за электроэнергию на складе</p>
<ol class="psteps">
${pstep({ n: '', t: 'Описать ситуацию', m: 'Склад. Общий счёт, показания вручную раз в месяц', cls: 'done' })}
${pstep({ n: 1, t: 'Сравнить счета и показания за сопоставимые периоды', m: 'С этого стоит начать', cls: 'now', right: cb })}
${pstep({ n: 2, t: 'Выяснить, менялись ли режим работы склада и состав оборудования', right: cb })}
${pstep({ n: 3, t: 'Обсудить, нужен ли более подробный учёт', m: 'После шагов 1 и 2', right: cb })}
</ol>
<div class="plan-acts"><button class="btn primary wide">Подготовить обращение специалисту</button><button class="btn wide">${ic('download', 18)}Скачать план</button></div></div>`,
  },
];
