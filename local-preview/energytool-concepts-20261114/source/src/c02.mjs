// 02 «Живая задача» — левая карточка собирает факты разговора; новое подсвечивается, любую строку можно исправить.
import { ic, T, header, sideNote, user, bot, composer, mcomposer, footer, bars } from './lib.mjs';
const C = 'c02';

const row = ({ icon, key, val, state = '', meta = '', action = '' }) =>
  `<div class="trow ${state}"><span class="ti">${ic(icon, 18)}</span><div class="tb"><span class="tk">${key}</span>${val}${meta ? `<span class="tm">${meta}</span>` : ''}</div>${action}</div>`;
const edit = `<button class="tedit" aria-label="Исправить">${ic('edit', 16)}</button>`;

const taskEmpty = `<section class="et-card task"><h2>Ваша задача<br>в фокусе</h2><p class="tstatus"><span class="dot off"></span>Заполняется по ходу разговора</p>
<div class="trows">
${row({ icon: 'building', key: 'Объект', val: '<p class="tv ph">Склад, офис, магазин, цех</p>', state: 'empty' })}
${row({ icon: 'target', key: 'Задача', val: '<p class="tv ph">Что хотите решить</p>', state: 'empty' })}
${row({ icon: 'checkCircle', key: 'Что известно', val: '<p class="tv ph">Факты из ваших ответов</p>', state: 'empty' })}
${row({ icon: 'question', key: 'Что уточнить', val: '<p class="tv ph">Открытые вопросы</p>', state: 'empty' })}
</div><p class="tfoot cap muted">Соберу карточку из ваших слов. Любую строку можно будет исправить.</p></section>`;

const taskWait = `<section class="et-card task"><h2>Ваша задача<br>в фокусе</h2><p class="tstatus"><span class="dot"></span>Записал вопрос. Остальное — после ответа</p>
<div class="trows">
${row({ icon: 'building', key: 'Объект', val: '<p class="tv">Склад</p>', state: 'new', meta: 'из вашего вопроса', action: edit })}
${row({ icon: 'target', key: 'Задача', val: `<p class="tv">«${T.q1}»</p>`, state: 'new', meta: 'ваш вопрос дословно' })}
${row({ icon: 'checkCircle', key: 'Что известно', val: '<p class="tv ph">Пока только вопрос</p>', state: 'empty' })}
${row({ icon: 'question', key: 'Что уточнить', val: '<p class="tv ph">Появится после ответа</p>', state: 'empty' })}
</div><div class="tactions"><button class="btn sm">${ic('plus', 16)}Добавить факт</button></div></section>`;

const taskFull = (hover = true) => `<section class="et-card task"><h2>Ваша задача<br>в фокусе</h2><p class="tstatus"><span class="dot"></span>Обновлено: 2 факта, 2 вопроса</p>
<div class="trows">
${row({ icon: 'building', key: 'Объект', val: '<p class="tv">Склад</p>', state: hover ? 'hover' : '', action: edit })}
${row({ icon: 'target', key: 'Задача', val: '<p class="tv">Понять, почему выросли счета за электроэнергию</p>' })}
${row({ icon: 'checkCircle', key: 'Что известно', val: '<ul class="tl"><li class="n">Виден только общий счёт</li><li class="n">Показания снимают вручную раз в месяц</li></ul>', state: 'new', meta: '<i class="nw">новое</i> · из ваших ответов' })}
${row({ icon: 'question', key: 'Что уточнить', val: '<ul class="tl q"><li>Менялся ли режим работы склада</li><li>Менялся ли состав оборудования</li></ul>', state: 'new', meta: '<i class="nw">новое</i> · из ответа консультанта' })}
</div><div class="tactions"><button class="btn sm">${ic('plus', 16)}Добавить факт</button><span class="cap muted">Исправить можно любую строку</span></div></section>`;

const sidebar = card => `<aside class="et-sidebar"><p class="et-eyebrow">КОНСУЛЬТАЦИЯ</p>${card}${sideNote()}</aside>`;

const pending = `<div class="pend"><div class="row between"><span class="label">${T.label}</span><span class="timer">Жду ответ 0:12</span></div><div class="pend-main">${bars()}<span>Готовлю ответ…</span></div><p class="et-hint">${T.wait}</p></div>`;

const next = `<section class="et-card next"><h3>Что дальше</h3><div class="next-grid">
<div><button class="btn primary wide">Подготовить обращение специалисту</button><p class="cap muted">В обращение попадёт карточка задачи. Вы проверите её перед сохранением.</p></div>
<div><button class="btn wide">Продолжить консультацию</button><p class="cap muted">Ответьте на открытые вопросы или задайте свой. Контакты не&nbsp;нужны.</p></div>
</div></section>`;

const updated = `<div class="upd">${ic('refresh', 16)}<span>Карточка задачи обновлена: 2 факта в «Что известно», 2 вопроса в «Что уточнить»</span></div>`;

export const screens = [
  {
    id: 'c02-a-start', concept: C, title: '02 Живая задача — старт',
    body: `${header()}
${sidebar(taskEmpty)}
<main class="et-workspace"><div class="et-scroll center">
<section class="et-welcome"><p class="et-eyebrow">КОНСУЛЬТАЦИЯ ПО ЭЛЕКТРОЭНЕРГИИ</p><h1>Что хотите решить<br>с электроэнергией?</h1><p class="et-intro">Помогу разобраться в расходах, наладить учёт и понять, где искать потери.</p>
<div class="et-suggestions"><button class="btn">Снизить расходы</button><button class="btn">Наладить учёт</button><button class="btn">Найти потери</button></div></section>
${composer({ cls: 'up', placeholder: 'Опишите вашу задачу своими словами' })}
<div class="row between under"><p class="et-hint">Подсказка подставит вопрос. Его можно изменить перед отправкой.</p><button class="link u">Оставить заявку специалисту</button></div>
</div>${footer()}</main>`,
  },
  {
    id: 'c02-b-wait', concept: C, title: '02 Живая задача — ожидание',
    body: `${header()}
${sidebar(taskWait)}
<main class="et-workspace"><div class="et-scroll hug">
<div class="et-messages">${user('У нас выросли счета за электроэнергию <mark>на складе</mark>. С чего начать?')}${pending}</div>
</div>
${composer({ cls: 'hug', placeholder: 'Можно писать следующее сообщение', hint: 'Отправка откроется, когда придёт ответ. Черновик сохранится.' })}
<div class="below"><div class="supp"><p class="label">Пока жду ответ, можно дополнить задачу</p><p class="cap muted">Добавлю в карточку и учту со следующим сообщением. В уже отправленный вопрос это не попадёт.</p>
<div class="supp-chips"><button class="chip dash lg">${ic('plus', 16)}Когда выросли счета</button><button class="chip dash lg">${ic('plus', 16)}Что менялось на объекте</button><button class="chip dash lg">${ic('plus', 16)}Как снимаете показания</button></div></div></div>
${footer()}</main>`,
  },
  {
    id: 'c02-c-answer', concept: C, title: '02 Живая задача — ответ',
    body: `${header()}
${sidebar(taskFull())}
<main class="et-workspace"><div class="et-scroll bottom fade">
<div class="et-messages">${user(T.q1)}${bot(T.clar)}${user(T.a1)}${bot(T.ans)}${updated}</div>
<div class="et-flow">${next}</div>
</div>
${composer({})}
${footer()}</main>`,
  },
  {
    id: 'c02-m1-answer', concept: C, mobile: true, w: 390, h: 844, title: '02 Живая задача — mobile, ответ',
    body: `${header({ mobile: true })}
<main class="et-workspace"><button class="m-task">${ic('target', 18)}<span class="grow">Задача: рост счетов на складе</span><span class="chip new">2 новых</span>${ic('chevronDown', 18)}</button><div class="et-scroll bottom fade">
<div class="et-messages">${user(T.a1)}${bot(T.ans)}${updated}</div>
<div class="et-flow">${next}</div>
</div>
<div class="m-dock">${mcomposer({})}</div></main>`,
  },
  {
    id: 'c02-m2-sheet', concept: C, mobile: true, w: 390, h: 844, title: '02 Живая задача — mobile, карточка задачи',
    body: `${header({ mobile: true })}
<main class="et-workspace"><button class="m-task">${ic('target', 18)}<span class="grow">Задача: рост счетов на складе</span>${ic('chevronUp', 18)}</button><div class="et-scroll">
<div class="et-messages">${user(T.a1)}${bot(T.ans)}</div>
</div></main>
<div class="sheet-scrim"></div>
<div class="sheet"><div class="grab"></div>
<div class="task in-sheet"><div class="row between"><h3>Ваша задача в фокусе</h3><button class="btn sm ghost" aria-label="Закрыть">${ic('close', 18)}</button></div>
<div class="trows">
${row({ icon: 'building', key: 'Объект', val: '<div class="tinput"><span>Склад и офисная часть</span><i class="caret"></i></div><div class="row tsave"><button class="btn sm primary">Сохранить</button><button class="btn sm">Отмена</button></div>', state: 'editing' })}
${row({ icon: 'target', key: 'Задача', val: '<p class="tv">Понять, почему выросли счета за электроэнергию</p>', action: edit })}
${row({ icon: 'checkCircle', key: 'Что известно', val: '<ul class="tl"><li class="n">Виден только общий счёт</li><li class="n">Показания снимают вручную раз в месяц</li></ul>', action: edit })}
${row({ icon: 'question', key: 'Что уточнить', val: '<ul class="tl q"><li>Менялся ли режим работы склада</li><li>Менялся ли состав оборудования</li></ul>', action: edit })}
</div></div></div>`,
  },
];

export { row as row02, edit as edit02, taskFull as taskFull02, sidebar as sidebar02, pending as pending02, next as next02, updated as updated02 };
