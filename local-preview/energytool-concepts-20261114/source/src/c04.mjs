// 04 «Карта консультации» — лёгкая схема «объект → учёт → задача → следующий шаг», растёт из подтверждённых слов пользователя.
import { ic, T, header, sideNote, user, bot, composer, mcomposer, footer, bars } from './lib.mjs';
const C = 'c04';

const st = ({ k, v, s = '', cls = '', a = '' }) => `<li class="st ${cls}"><span class="st-k">${k}</span><span class="st-m"><i></i></span><b class="st-v">${v}</b>${s ? `<span class="st-s">${s}</span>` : ''}${a ? `<button class="st-a">${a}</button>` : ''}</li>`;

const stationsEmpty = `<ol class="stations">
${st({ k: 'Объект', v: 'Склад, офис, цех', cls: 'empty dash' })}
${st({ k: 'Учёт', v: 'Как снимаете показания', cls: 'empty dash' })}
${st({ k: 'Задача', v: 'Что хотите решить', cls: 'empty dash' })}
${st({ k: 'Следующий шаг', v: 'Предложу в ответе', cls: 'empty' })}</ol>`;
const stationsWait = `<ol class="stations">
${st({ k: 'Объект', v: 'Склад', s: 'из вашего вопроса', cls: 'new dash' })}
${st({ k: 'Учёт', v: 'Не указано', cls: 'empty dash', a: 'Указать' })}
${st({ k: 'Задача', v: 'Выросли счета за электроэнергию', s: 'из вашего вопроса', cls: 'new dash' })}
${st({ k: 'Следующий шаг', v: 'Жду ответа консультанта', cls: 'await' })}</ol>`;
const stationsFull = `<ol class="stations">
${st({ k: 'Объект', v: 'Склад', cls: 'known' })}
${st({ k: 'Учёт', v: 'Общий счёт, вручную раз в месяц', cls: 'new' })}
${st({ k: 'Задача', v: 'Рост счетов за электроэнергию', cls: 'known' })}
${st({ k: 'Следующий шаг', v: 'Сравнить счета и показания', cls: 'prop' })}</ol>`;

const mapCard = (head, sub, stations, btn = '', extra = '') => `<section class="map"><div class="row between top"><div><b class="label">${head}</b><p class="cap muted">${sub}</p></div>${btn}</div>${stations}${extra}</section>`;
const gap = `<div class="gap"><div><b class="label">Учёт пока не указан</b><p class="cap muted">Если знаете — отметьте. Учту со следующим сообщением.</p></div><div class="gap-opts"><button class="chip lg">Общий счётчик</button><button class="chip lg">По зонам или цехам</button><button class="chip lg dash">Не знаю</button></div></div>`;
const stationsShort = `<ol class="stations">
${st({ k: 'Объект', v: 'Склад', cls: 'known' })}
${st({ k: 'Учёт', v: 'Общий счёт, вручную', cls: 'new' })}
${st({ k: 'Задача', v: 'Рост счетов', cls: 'known' })}
${st({ k: 'Следующий шаг', v: 'Сравнить периоды', cls: 'prop' })}</ol>`;
const mapCompact = `<section class="map compact">${stationsShort}<button class="map-toggle" aria-label="Развернуть карту">${ic('chevronDown', 18)}</button></section>`;

const dots = n => `<span class="mdots">${[0, 1, 2, 3].map(i => `<i class="${i < n ? 'on' : ''}"></i>`).join('')}</span>`;
const sidebar = (n, note) => `<aside class="et-sidebar"><p class="et-eyebrow">КОНСУЛЬТАЦИЯ</p><section class="et-card et-focus"><h2>Ваша задача<br>в фокусе</h2><p>Учёт, расходы и потери электроэнергии</p><div class="f-map"><div class="row between"><span class="cap muted">Карта консультации</span>${dots(n)}</div><p class="cap">${note}</p></div></section>${sideNote()}</aside>`;

const pendingLine = `<div class="et-message et-assistant"><div class="row between plh"><div class="et-message-label">${T.label}</div><span class="timer">Жду ответ 0:12</span></div><div class="row pl">${bars()}<span>Готовлю ответ…</span></div><p class="et-hint">${T.wait}</p></div>`;

const next = `<section class="et-card next"><h3>Что дальше</h3><div class="next-grid">
<div><button class="btn primary wide">Подготовить обращение специалисту</button><p class="cap muted">К обращению приложу карту: объект, учёт, задачу и предложенный шаг.</p></div>
<div><button class="btn wide">Продолжить консультацию</button><p class="cap muted">Задайте следующий вопрос. Контакты для этого не&nbsp;нужны.</p></div>
</div></section>`;
const mapNote = `<div class="upd">${ic('refresh', 16)}<span>Карта обновлена: «Учёт» — из вашего ответа, «Следующий шаг» — предложение консультанта</span></div>`;

export const screens = [
  {
    id: 'c04-a-start', concept: C, title: '04 Карта консультации — старт',
    body: `${header()}
${sidebar(0, 'Соберу из ваших слов по ходу разговора')}
<main class="et-workspace"><div class="et-scroll">
<section class="et-welcome"><p class="et-eyebrow">КОНСУЛЬТАЦИЯ ПО ЭЛЕКТРОЭНЕРГИИ</p><h1>Что хотите решить<br>с электроэнергией?</h1><p class="et-intro">Помогу разобраться в расходах, наладить учёт и понять, где искать потери.</p>
<div class="et-suggestions"><button class="btn">Снизить расходы</button><button class="btn">Наладить учёт</button><button class="btn">Найти потери</button></div></section>
${composer({ cls: 'up', placeholder: 'Опишите вашу задачу своими словами' })}
<div class="row between under"><p class="et-hint">Подсказка подставит вопрос. Его можно изменить перед отправкой.</p><button class="link u">Оставить заявку специалисту</button></div>
${mapCard('По ходу разговора соберу карту задачи', 'Четыре опоры, по которым специалисту и вам будет проще понять ситуацию.', stationsEmpty)}
</div>${footer()}</main>`,
  },
  {
    id: 'c04-b-wait', concept: C, title: '04 Карта консультации — ожидание',
    body: `${header()}
${sidebar(2, 'Заполнено 2 из 4. Неизвестное можно указать')}
<main class="et-workspace"><div class="et-scroll">
<div class="et-messages">${user(T.q1)}${pendingLine}
${mapCard('Пока жду ответ — вот что я записал', 'Неизвестное можно указать самому. Учту со следующим сообщением.', stationsWait, `<button class="btn sm">${ic('edit', 16)}Изменить</button>`, gap)}</div>
</div>
${composer({ placeholder: 'Можно писать следующее сообщение', hint: 'Отправка откроется, когда придёт ответ. Черновик сохранится.' })}
${footer()}</main>`,
  },
  {
    id: 'c04-c-answer', concept: C, title: '04 Карта консультации — ответ',
    body: `${header()}
${sidebar(4, 'Заполнено 4 из 4. Шаг предложен консультантом')}
<main class="et-workspace">${mapCompact}<div class="et-scroll bottom fade">
<div class="et-messages">${user(T.q1)}${bot(T.clar)}${user(T.a1)}${bot(T.ans)}${mapNote}</div>
<div class="et-flow">${next}</div>
</div>
${composer({})}
${footer()}</main>`,
  },
  {
    id: 'c04-m1-wait', concept: C, mobile: true, w: 390, h: 844, title: '04 Карта консультации — mobile, ожидание',
    body: `${header({ mobile: true })}
<main class="et-workspace"><div class="et-scroll">
<div class="et-messages">${user(T.q1)}${pendingLine.replace('Жду ответ 0:12', '0:12')}
${mapCard('Вот что я записал', 'Неизвестное можно указать самому.', stationsWait)}</div>
</div>
<div class="m-dock">${mcomposer({ placeholder: 'Следующее сообщение' })}</div></main>`,
  },
  {
    id: 'c04-m2-answer', concept: C, mobile: true, w: 390, h: 844, title: '04 Карта консультации — mobile, ответ',
    body: `${header({ mobile: true })}
<main class="et-workspace"><div class="mstrip clip-ok">${stationsShort}</div><div class="et-scroll bottom fade">
<div class="et-messages">${user(T.a1)}${bot(T.ans)}</div>
<div class="et-flow">${next}</div>
</div>
<div class="m-dock">${mcomposer({})}</div></main>`,
  },
];
