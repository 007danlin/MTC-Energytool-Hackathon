// Выбранное направление A — «Живая задача» (02): полные состояния.
import { ic, T, header, user, bot, composer, footer, bars } from './lib.mjs';
import { row02 as row, edit02 as edit, sidebar02 as sidebar, next02 as next, updated02 as updated } from './c02.mjs';
import * as S from './states.mjs';
const C = 'c02';
const G = 'A';

const card = ({ status, dot = true, obj = 'Склад', task = 'Понять, почему выросли счета за электроэнергию', known, ask, foot = true }) => `<section class="et-card task"><h2>Ваша задача<br>в фокусе</h2><p class="tstatus"><span class="dot ${dot ? '' : 'ink'}"></span>${status}</p>
<div class="trows">${row({ icon: 'building', key: 'Объект', val: `<p class="tv">${obj}</p>`, action: edit })}
${row({ icon: 'target', key: 'Задача', val: `<p class="tv">${task}</p>` })}
${known}${ask}</div>${foot ? `<div class="tactions"><button class="btn sm">${ic('plus', 16)}Добавить факт</button><span class="cap muted">Исправить можно любую строку</span></div>` : ''}</section>`;

const knownFull = row({ icon: 'checkCircle', key: 'Что известно', val: '<ul class="tl"><li>Виден только общий счёт</li><li>Показания снимают вручную раз в месяц</li></ul>' });
const askFull = row({ icon: 'question', key: 'Что уточнить', val: '<ul class="tl q"><li>Менялся ли режим работы склада</li><li>Менялся ли состав оборудования</li></ul>' });
const knownEmpty = row({ icon: 'checkCircle', key: 'Что известно', val: '<p class="tv ph">Пока только вопрос</p>', state: 'empty' });
const knownQuote = row({ icon: 'checkCircle', key: 'Что известно', val: `<p class="tv">«${T.a1}»</p>`, state: 'new', meta: '<i class="nw">новое</i> · ваш ответ дословно' });
const askPending = row({ icon: 'question', key: 'Что уточнить', val: '<p class="tv ph">Появится после ответа</p>', state: 'empty' });

const taskHtml = `<b>Понять, почему выросли счета за электроэнергию</b><span class="rk">Объект: склад</span><ul><li>Виден только общий счёт</li><li>Показания снимают вручную раз в месяц</li></ul><ul class="q"><li>Менялся ли режим работы склада</li><li>Менялся ли состав оборудования</li></ul>`;

const lw = `<div class="pend lw">${S.longWaitHead()}</div>`;
const supp = `<div class="supp"><p class="label">Пока жду ответ, можно дополнить задачу</p><p class="cap muted">Добавлю в карточку и учту со следующим сообщением.</p><div class="supp-chips"><button class="chip dash lg">${ic('plus', 16)}Когда выросли счета</button><button class="chip dash lg">${ic('plus', 16)}Что менялось на объекте</button></div></div>`;

export const screens = [
  {
    id: 'sA-1-clarify', concept: C, group: G, title: 'A · Живая задача — уточнение',
    body: `${header()}
${sidebar(card({ status: 'Жду ваш ответ на уточнение', task: `«${T.q1}»`, known: knownEmpty, ask: row({ icon: 'question', key: 'Что уточнить', val: '<ul class="tl q"><li class="n">Показания по зонам или только общая сумма</li></ul>', state: 'new', meta: '<i class="nw">спрашиваю сейчас</i>' }) }))}
<main class="et-workspace"><div class="et-scroll hug">
<div class="et-messages">${user(T.q1)}${bot(T.clar + S.quick)}</div>
</div>
${composer({ cls: 'hug', focus: true, placeholder: 'Ответьте на уточнение своими словами' })}
<div class="below"></div>
${footer()}</main>`,
  },
  {
    id: 'sA-2-longwait', concept: C, group: G, title: 'A · Живая задача — очень долгое ожидание',
    body: `${header()}
${sidebar(card({ status: '<span class="num">Жду ответ уже 1:48. Данные на месте</span>', task: `«${T.q1}»`, known: knownQuote, ask: askPending }))}
<main class="et-workspace"><div class="et-scroll hug">
<div class="et-messages">${user(T.q1)}${bot(T.clar)}${user(T.a1)}${lw}</div>
</div>
${composer({ cls: 'hug', placeholder: 'Можно писать следующее сообщение', hint: 'Отправка откроется, когда придёт ответ. Черновик сохранится.' })}
<div class="below">${supp}</div>
${footer()}</main>`,
  },
  {
    id: 'sA-3-error', concept: C, group: G, title: 'A · Живая задача — ошибка',
    body: `${header()}
${sidebar(card({ status: 'Карточка на месте. Жду сверки с сервером', dot: false, task: `«${T.q1}»`, known: row({ icon: 'checkCircle', key: 'Что известно', val: `<p class="tv">«${T.a1}»</p>`, meta: 'ваш ответ дословно' }), ask: askPending }))}
<main class="et-workspace"><div class="et-scroll hug">
<div class="et-messages">${user(T.q1)}${bot(T.clar)}${user(T.a1)}${S.errorCard(`<li class="ok">${ic('check', 16)}<span>Карточка задачи и черновик на месте</span></li>`)}</div>
</div>
${composer({ cls: 'hug', placeholder: 'Можно писать следующее сообщение', hint: 'Отправка откроется после сверки с сервером.' })}
<div class="below"></div>
${footer()}</main>`,
  },
  {
    id: 'sA-4-gap', concept: C, group: G, title: 'A · Живая задача — нет данных в базе',
    body: `${header()}
${sidebar(card({ status: 'Обновлено: 1 вопрос для специалиста', known: knownFull, ask: row({ icon: 'question', key: 'Что уточнить', val: '<ul class="tl q"><li>Менялся ли режим работы склада</li><li>Менялся ли состав оборудования</li><li class="n">Оценка экономии от учёта по зонам</li></ul>', state: 'new', meta: '<i class="nw">новое</i> · вопрос специалисту' }) }))}
<main class="et-workspace"><div class="et-scroll bottom fade">
<div class="et-messages">${user(T.a1)}${bot(T.ans)}${user(S.Q2)}${S.gapMsg}</div>
<div class="et-flow">${S.gapCard('Приложу вопрос и карточку задачи. Вы проверите заявку перед сохранением.')}</div>
</div>
${composer({})}
${footer()}</main>`,
  },
  {
    id: 'sA-5-long', concept: C, group: G, title: 'A · Живая задача — длинный ответ',
    body: `${header()}
${sidebar(card({ status: 'Обновлено: 2 факта, 2 вопроса', known: knownFull, ask: row({ icon: 'question', key: 'Что уточнить', val: '<ul class="tl q"><li class="n">Как менялась площадь склада</li><li class="n">Когда начался рост счетов</li></ul>', state: 'new', meta: '<i class="nw">новое</i> · из ответа консультанта' }) }))}
<main class="et-workspace"><div class="et-scroll fadeb clip-ok">
<div class="et-messages">${user(T.a1)}${S.longAnswer}${updated}</div><div class="et-flow">${next}</div>
${S.jump}</div>
${composer({})}
${footer()}</main>`,
  },
  {
    id: 'sA-6-contact', concept: C, group: G, title: 'A · Живая задача — контактная форма',
    body: `${header()}
${sidebar(card({ status: 'Приложу к заявке как есть', dot: false, known: knownFull, ask: askFull }))}
<main class="et-workspace"><div class="et-scroll bottom fade">
<div class="et-messages">${bot('Подготовлю заявку. Оставьте контакт — карточку задачи приложу сам.')}</div>
<div class="et-flow">${S.contactForm('Приложу карточку задачи: объект, что известно и что уточнить')}</div>
</div>
${S.slim()}
${footer()}</main>`,
  },
  {
    id: 'sA-7-review', concept: C, group: G, title: 'A · Живая задача — проверка и редактирование заявки',
    body: `${header()}
${sidebar(card({ status: 'Приложу к заявке как есть', dot: false, known: knownFull, ask: askFull }))}
<main class="et-workspace"><div class="et-scroll bottom fade">
<div class="et-flow">${S.review({ task: taskHtml, editing: true })}</div>
</div>
${S.slim()}
${footer()}</main>`,
  },
  {
    id: 'sA-8-saved', concept: C, group: G, title: 'A · Живая задача — заявка сохранена',
    body: `${header()}
${sidebar(card({ status: '<span class="num">Приложена к заявке в 14:52</span>', dot: false, known: knownFull, ask: askFull }))}
<main class="et-workspace"><div class="et-scroll bottom fade">
<div class="et-messages">${S.prev}${bot('Заявка сохранена. Можно продолжить консультацию или вернуться к ней в истории.')}</div>
<div class="et-flow">${S.saved({ task: `<b>Понять, почему выросли счета за электроэнергию</b><span class="rk">Склад · 2 факта · 2 открытых вопроса — как в карточке слева</span>` })}</div>
</div>
${S.slim('Задайте следующий вопрос')}
${footer()}</main>`,
  },
  {
    id: 'sA-9-context', concept: C, group: G, title: 'A · Живая задача — длинный контекст',
    body: `${header()}
${sidebar(`<section class="et-card task"><h2>Ваша задача<br>в фокусе</h2><p class="tstatus"><span class="dot"></span>Обновлено: 1 факт. Всего 7 фактов, 4 вопроса</p>
<div class="trows">${row({ icon: 'building', key: 'Объект', val: '<p class="tv">Склад и офисная часть</p>', action: edit })}
${row({ icon: 'target', key: 'Задача', val: '<p class="tv">Понять, почему выросли счета за электроэнергию</p>' })}
${row({ icon: 'checkCircle', key: 'Что известно · 7', val: `<ul class="tl"><li class="n">Рост начался с сентября</li><li>Виден только общий счёт</li></ul><button class="tmore">Показать ещё 5 ${ic('chevronDown', 14)}</button>`, state: 'new', meta: '<i class="nw">новое</i> · сверху последнее' })}
${row({ icon: 'question', key: 'Что уточнить · 4', val: `<ul class="tl q"><li>Менялся ли режим работы склада</li><li>Менялся ли состав оборудования</li></ul><button class="tmore">Показать ещё 2 ${ic('chevronDown', 14)}</button>` })}
</div><div class="tactions"><button class="btn sm">${ic('plus', 16)}Добавить факт</button><button class="link u tall">Весь список</button></div></section>`).replace(/<div class="et-side-note">.*?<\/div>/s, '')}
<main class="et-workspace"><div class="et-scroll bottom fade">
<div class="et-messages">${user(T.a1)}${bot(T.ans)}${user('Режим не менялся. Но рост начался с сентября, до этого счета были ровные.')}${bot('Понял: рост начался с сентября. Тогда сравнивайте сентябрь и октябрь с теми же месяцами прошлого года — так сезонность не исказит картину.')}${updated.replace('2 факта в «Что известно», 2 вопроса в «Что уточнить»', 'добавлен 1 факт. Длинные списки свёрнуты, новое всегда сверху')}</div>
<div class="et-flow">${next}</div>
</div>
${composer({})}
${footer()}</main>`,
  },
];
