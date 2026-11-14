// Общие блоки состояний для двух выбранных направлений (уточнение, долгое ожидание, ошибка, нет знаний,
// длинный ответ, контакт, проверка, сохранение). Тексты — макетный контент.
import { ic, T, bars } from './lib.mjs';

export const Q2 = 'Сколько мы сэкономим, если поставить счётчики на каждую зону?';
export const GAP = 'В базе EnergyTool нет данных, чтобы оценить экономию для вашего склада. Называть цифры наугад не буду.';

export const quick = `<div class="qr"><button class="btn">Только общая сумма</button><button class="btn">Есть по зонам</button><button class="btn">Не знаю</button><span class="cap muted">или ответьте своими словами</span></div>`;

export const longWaitHead = (t = '1:48') => `<div class="row between"><span class="label">${T.label}</span><span class="timer">Жду ответ ${t}</span></div><div class="pend-main">${bars()}<span>Всё ещё готовлю ответ</span></div>
<p class="lw-p">Это дольше, чем хотелось бы. Ваш вопрос сохранён в диалоге и не потеряется.</p>
<div class="lw-acts"><button class="btn sm">Оставить заявку специалисту</button><button class="btn sm ghost">Прервать ожидание</button></div>
<p class="cap muted lw-n">К заявке приложу ваш вопрос. Если прервать, сначала сверю диалог с сервером: ответ мог успеть прийти.</p>`;

export const errorCard = (extra = '') => `<section class="et-error errc"><div class="row errh">${ic('alert', 20)}<h3>Ответ не пришёл</h3></div>
<ul class="facts"><li class="ok">${ic('check', 16)}<span>Ваш вопрос сохранён в диалоге</span></li><li class="unk">${ic('question', 16)}<span>Неизвестно, успел ли консультант его получить</span></li>${extra}</ul>
<p>Сначала сверю диалог с сервером. Если ответа там нет, отправлю вопрос ещё раз — без дубля.</p>
<div class="row erra"><button class="btn primary">Сверить и повторить</button><button class="btn">Оставить заявку специалисту</button></div>
<p class="cap muted">Время ожидания истекло в 14:37. Повторять вручную не нужно.</p></section>`;

export const gapMsg = `<div class="et-message et-assistant"><div class="row gaph"><div class="et-message-label">${T.label}</div><span class="chip soft">${ic('info', 14)}Нет данных в базе</span></div><div class="et-message-body">${GAP}</div></div>`;
export const gapCard = attach => `<section class="et-card next"><h3>Что можно сделать</h3><div class="next-grid">
<div><button class="btn primary wide">Передать вопрос специалисту</button><p class="cap muted">${attach}</p></div>
<div><button class="btn wide">Задать другой вопрос</button><p class="cap muted">Консультация продолжится в этом же диалоге.</p></div>
</div></section>`;

export const longAnswer = `<div class="et-message et-assistant long"><div class="et-message-label">${T.label}</div><div class="et-message-body">
<p>Чтобы понять, откуда рост, идите от простого к сложному.</p>
<ol class="la"><li><b>Сравните счета за два-три сопоставимых периода.</b> Смотрите не только на сумму, но и на объём потребления в кВт·ч: так станет ясно, выросло потребление или изменилась цена.</li>
<li><b>Сверьте показания счётчика с данными в счетах.</b> При ручном съёме раз в месяц легко получить расхождение в датах: показания сняты позже — период в счёте длиннее.</li>
<li><b>Вспомните, что менялось на складе.</b> Режим работы, новое оборудование, отопление, освещение, арендаторы.</li>
<li><b>Оцените, хватает ли общего счётчика.</b> Если по нему не видно, какая зона потребляет больше, стоит обсудить более подробный учёт — по зонам или по крупным потребителям.</li></ol>
<p>Чего я пока не знаю: как менялась площадь склада и когда именно начался рост. Эти данные помогут сузить поиск.</p></div></div>`;
export const jump = `<button class="jump">${ic('arrowDown', 16)}К следующему шагу</button>`;

const field = ({ k, v = '', ph = '', cls = '', err = '' }) => `<label class="et-field ${cls}"><span>${k}</span><b class="${v ? '' : 'ph'}">${v || ph}${cls.includes('is-focus') ? '<i class="caret"></i>' : ''}</b>${err ? `<p class="et-field-error">${err}</p>` : ''}</label>`;
export const contactForm = attach => `<section class="et-card form"><h2>Как с вами связаться?</h2><p class="small muted">Достаточно телефона или email. Имя и компания — по желанию.</p>
<div class="fgrid">${field({ k: 'Телефон или email', v: '+7 999 123-45-67', cls: 'is-focus full' })}${field({ k: 'Имя и фамилия', ph: 'Как к вам обращаться' })}${field({ k: 'Компания', ph: 'Название компании' })}</div>
<div class="cb"><span class="label">Когда вам удобно поговорить?</span><div class="cb-opts"><div class="cb-opt on"><i class="radio on"></i><div><b>Как можно скорее</b><p>Готов поговорить сейчас</p></div></div><div class="cb-opt"><i class="radio"></i><div><b>В удобное время</b><p>Выбрать дату и время</p></div></div></div></div>
<div class="attach">${ic('doc', 18)}<span class="grow">${attach}</span><button class="link u">Посмотреть</button></div>
<div class="row fa"><button class="btn primary">Проверить заявку</button><button class="btn">Продолжить без контакта</button></div></section>`;

const rv = ({ k, v, edit = true }) => `<div class="rv-row"><span class="rv-k">${k}</span><div class="rv-v">${v}</div>${edit ? '<button class="link u">Изменить</button>' : ''}</div>`;
export const contactsV = `<b>Анна Миронова</b><span>+7 999 123-45-67</span><span>Тестовая компания</span>`;
export const review = ({ task, editing = false }) => `<section class="et-card review"><h2>Проверьте заявку</h2><p class="small muted">Пока ничего не сохранено. Заявка сохранится в этом диалоге после подтверждения.</p>
<div class="rv">${editing
    ? `<div class="rv-row editing"><span class="rv-k">Контакты</span><div class="rv-v"><div class="fgrid tight">${field({ k: 'Имя и фамилия', v: 'Анна Миронова' })}${field({ k: 'Компания', v: 'Тестовая компания' })}${field({ k: 'Телефон или email', v: '+7 999 123-45-6', cls: 'is-focus is-invalid full', err: 'Укажите телефон из 10–15 цифр или email, например name@example.ru' })}</div><div class="row"><button class="btn sm primary is-disabled">Сохранить изменения</button><button class="btn sm">Отмена</button></div></div></div>`
    : rv({ k: 'Контакты', v: contactsV })}
${rv({ k: 'Связь', v: '<span>По телефону, как можно скорее</span>' })}
${rv({ k: 'Задача', v: task })}</div>
<div class="row fa"><button class="btn primary ${editing ? 'is-disabled' : ''}">Сохранить заявку</button><button class="btn">Вернуться к разговору</button>${editing ? '<span class="cap muted">Сначала сохраните или отмените изменения</span>' : ''}</div></section>`;

export const saved = ({ task }) => `<section class="et-card saved"><div class="row sh"><span class="okm">${ic('check', 18)}</span><h2>Заявка сохранена</h2></div>
<ul class="facts"><li class="ok">${ic('check', 16)}<span>Сохранена в этом диалоге 14 ноября в 14:52</span></li><li class="unk">${ic('clock', 16)}<span>Передача специалисту пока не подтверждена. Статус появится здесь</span></li></ul>
<div class="rv">${rv({ k: 'Контакты', v: contactsV, edit: false })}${rv({ k: 'Задача', v: task, edit: false })}</div>
<div class="row fa"><button class="btn primary">Продолжить консультацию</button><button class="btn">${ic('download', 18)}Скачать заявку</button><button class="btn">История диалогов</button></div></section>`;

export const prev = `<button class="btn prevb">${ic('chevronUp', 18)}Предыдущая переписка</button>`;
export const slim = (ph = 'Можно продолжить разговор — заявка не обязательна') => `<form class="et-composer v2 slim"><div class="ta ph">${ph}</div><button class="btn primary et-send" disabled>Отправить</button></form>`;
