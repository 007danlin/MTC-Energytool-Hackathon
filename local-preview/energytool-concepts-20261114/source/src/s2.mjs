// Выбранное направление B — «Ожидание с пользой» (03): полные состояния.
import { ic, T, header, user, bot, composer, footer, bars } from './lib.mjs';
import { sidebar03 as sidebar, focusAnswer03 as focusAnswer, focusWait03 as focusWait, next03 as next, draftLeft03 as draftLeft, tick03 as tick } from './c03.mjs';
import * as S from './states.mjs';
const C = 'c03';
const G = 'B';
const draft = 'Под рукой: счета за последние 2–3 месяца.';
const recap = `<div class="recap">${ic('checkCircle', 16)}<span>Пока вы ждали, отмечено: счета за последние 2–3 месяца</span><button class="link u">Изменить</button></div>`;
const lw = `<section class="wait"><div class="wait-head lwh">${S.longWaitHead()}</div>
<div class="wait-body"><p class="label">Пока ждёте — что ещё есть под рукой</p>
<ul class="cks"><li class="on">${tick(true)}<div><b>Счета за последние 2–3 месяца</b></div></li><li>${tick(false)}<div><b>Показания счётчика за те же месяцы</b></div></li><li>${tick(false)}<div><b>Что менялось в работе склада</b></div></li></ul></div></section>`;
const taskB = `<b>Понять, почему выросли счета на складе</b><span class="rk">Общий счёт, показания вручную раз в месяц. Под рукой: счета за последние 2–3 месяца</span>`;

export const screens = [
  {
    id: 'sB-1-clarify', concept: C, group: G, title: 'B · Ожидание с пользой — уточнение',
    body: `${header()}
${sidebar(focusWait)}
<main class="et-workspace"><div class="et-scroll hug">
<div class="et-messages">${user(T.q1)}${recap}${bot(T.clar + S.quick)}</div>
</div>
${composer({ cls: 'hug', value: draft, can: true, left: draftLeft('Собран, пока вы ждали. Допишите ответ на уточнение') })}
<div class="below"></div>
${footer()}</main>`,
  },
  {
    id: 'sB-2-longwait', concept: C, group: G, title: 'B · Ожидание с пользой — очень долгое ожидание',
    body: `${header()}
${sidebar(focusWait)}
<main class="et-workspace"><div class="et-scroll bottom fade">
<div class="et-messages">${user(T.q1)}${bot(T.clar)}${user(T.a1)}${lw}</div>
</div>
${composer({ value: draft, left: draftLeft('Отправите, когда придёт ответ') })}
${footer()}</main>`,
  },
  {
    id: 'sB-3-error', concept: C, group: G, title: 'B · Ожидание с пользой — ошибка',
    body: `${header()}
${sidebar(focusWait)}
<main class="et-workspace"><div class="et-scroll hug">
<div class="et-messages">${user(T.q1)}${bot(T.clar)}${user(T.a1)}${S.errorCard(`<li class="ok">${ic('check', 16)}<span>Черновик и отметки на месте</span></li>`)}</div>
</div>
${composer({ cls: 'hug', value: draft, left: draftLeft('Отправка откроется после сверки с сервером') })}
<div class="below"></div>
${footer()}</main>`,
  },
  {
    id: 'sB-4-gap', concept: C, group: G, title: 'B · Ожидание с пользой — нет данных в базе',
    body: `${header()}
${sidebar(focusAnswer)}
<main class="et-workspace"><div class="et-scroll bottom fade">
<div class="et-messages">${user(T.a1)}${bot(T.ans)}${user(S.Q2)}${S.gapMsg}</div>
<div class="et-flow">${S.gapCard('Приложу вопрос и краткое описание задачи. Вы проверите заявку перед сохранением.')}</div>
</div>
${composer({})}
${footer()}</main>`,
  },
  {
    id: 'sB-5-long', concept: C, group: G, title: 'B · Ожидание с пользой — длинный ответ',
    body: `${header()}
${sidebar(focusAnswer)}
<main class="et-workspace"><div class="et-scroll fadeb clip-ok">
<div class="et-messages">${user(T.a1)}${S.longAnswer}</div><div class="et-flow">${next}</div>
${S.jump}</div>
${composer({ value: draft, can: true, left: draftLeft('Собран, пока вы ждали ответ') })}
${footer()}</main>`,
  },
  {
    id: 'sB-6-contact', concept: C, group: G, title: 'B · Ожидание с пользой — контактная форма',
    body: `${header()}
${sidebar(focusAnswer)}
<main class="et-workspace"><div class="et-scroll bottom fade">
<div class="et-messages">${bot('Подготовлю заявку. Оставьте контакт — описание задачи соберу из нашей беседы.')}</div>
<div class="et-flow">${S.contactForm('Приложу описание задачи и то, что вы отметили: счета за 2–3 месяца')}</div>
</div>
${S.slim()}
${footer()}</main>`,
  },
  {
    id: 'sB-7-review', concept: C, group: G, title: 'B · Ожидание с пользой — проверка заявки',
    body: `${header()}
${sidebar(focusAnswer)}
<main class="et-workspace"><div class="et-scroll bottom fade">
<div class="et-messages">${S.prev}${bot('Собрал контакты и описание задачи. Всё верно?')}</div>
<div class="et-flow">${S.review({ task: taskB })}</div>
</div>
${S.slim()}
${footer()}</main>`,
  },
  {
    id: 'sB-8-saved', concept: C, group: G, title: 'B · Ожидание с пользой — заявка сохранена',
    body: `${header()}
${sidebar(focusAnswer)}
<main class="et-workspace"><div class="et-scroll bottom fade">
<div class="et-messages">${S.prev}${bot('Заявка сохранена. Можно продолжить консультацию или вернуться к ней в истории.')}</div>
<div class="et-flow">${S.saved({ task: taskB })}</div>
</div>
${S.slim('Задайте следующий вопрос')}
${footer()}</main>`,
  },
];
