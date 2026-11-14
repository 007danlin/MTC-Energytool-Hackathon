// Общие помощники для сборки экранов EnergyTool.
export const esc = s => String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');

const P = {
  check: '<path d="M4.5 10.5l3.5 3.5 7.5-8"/>',
  plus: '<path d="M10 4.5v11M4.5 10h11"/>',
  close: '<path d="M5.5 5.5l9 9M14.5 5.5l-9 9"/>',
  arrowRight: '<path d="M4 10h12M11 5l5 5-5 5"/>',
  arrowUp: '<path d="M10 16V4M5 9l5-5 5 5"/>',
  arrowDown: '<path d="M10 4v12M5 11l5 5 5-5"/>',
  chevronDown: '<path d="M5 7.5l5 5 5-5"/>',
  chevronUp: '<path d="M5 12.5l5-5 5 5"/>',
  chevronRight: '<path d="M7.5 5l5 5-5 5"/>',
  edit: '<path d="M4 16l.8-3.4 8.8-8.8a1.4 1.4 0 012 0l.6.6a1.4 1.4 0 010 2l-8.8 8.8L4 16z"/><path d="M12.2 5.2l2.6 2.6"/>',
  clock: '<circle cx="10" cy="10" r="7"/><path d="M10 6v4l2.5 2"/>',
  doc: '<path d="M5.75 2.75h5.75l4 4V16c0 .7-.55 1.25-1.25 1.25h-8.5c-.7 0-1.25-.55-1.25-1.25V4c0-.7.55-1.25 1.25-1.25z"/><path d="M11.5 2.75v4h4M7.5 10.5h5M7.5 13.5h5"/>',
  copy: '<rect x="7" y="7" width="9.5" height="9.5" rx="2"/><path d="M4.5 13V5.5c0-.8.7-1.5 1.5-1.5H13"/>',
  download: '<path d="M10 3.5v9M6 9l4 4 4-4M4 16.5h12"/>',
  phone: '<path d="M6.2 3.5h2l1 3.2-1.5 1.1a8 8 0 004.5 4.5l1.1-1.5 3.2 1v2c0 .9-.8 1.7-1.7 1.7A11.3 11.3 0 014.5 5.2c0-.9.8-1.7 1.7-1.7z"/>',
  user: '<circle cx="10" cy="7" r="3"/><path d="M4 16.5c.6-3 3-4.5 6-4.5s5.4 1.5 6 4.5"/>',
  info: '<circle cx="10" cy="10" r="7"/><path d="M10 9.25v4.25"/><path d="M10 6.6v.01" stroke-width="2"/>',
  alert: '<path d="M10 3.5l7 12.5H3L10 3.5z"/><path d="M10 8.5v3.25"/><path d="M10 13.9v.01" stroke-width="2"/>',
  refresh: '<path d="M16 10a6 6 0 11-1.8-4.3"/><path d="M16.2 3.6v3.2H13"/>',
  history: '<path d="M4 10a6 6 0 101.8-4.3"/><path d="M3.8 3.6v3.2H7M10 7v3.2l2 1.3"/>',
  menu: '<path d="M4 6h12M4 10h12M4 14h12"/>',
  building: '<path d="M4 16.5V5.5l6-2.5v13.5M10 7.5l6 2v7M2.75 16.5h14.5"/><path d="M7 7.6v.01M7 10.6v.01M7 13.6v.01M13 11.6v.01M13 14.1v.01" stroke-width="1.8"/>',
  gauge: '<path d="M3.5 13.5a6.5 6.5 0 0113 0"/><path d="M10 13.5l3.2-4.2"/><circle cx="10" cy="13.5" r="1.1"/>',
  target: '<circle cx="10" cy="10" r="7"/><circle cx="10" cy="10" r="3.2"/><path d="M10 9.99v.02" stroke-width="2"/>',
  flag: '<path d="M5 17V3.5M5 4h9.5L13 7l1.5 3H5"/>',
  question: '<circle cx="10" cy="10" r="7"/><path d="M8 8.1a2 2 0 113.1 1.7c-.6.4-1.1.8-1.1 1.6"/><path d="M10 13.9v.01" stroke-width="2"/>',
  chat: '<path d="M4 5.5C4 4.7 4.7 4 5.5 4h9c.8 0 1.5.7 1.5 1.5v6c0 .8-.7 1.5-1.5 1.5H9l-3.5 3v-3C4.7 13 4 12.3 4 11.5v-6z"/>',
  list: '<path d="M7.5 5.5H16M7.5 10H16M7.5 14.5H16"/><path d="M4 5.5h.01M4 10h.01M4 14.5h.01" stroke-width="2"/>',
  bolt: '<path d="M11 2.5L4.5 11.5h5l-1 6 7-9h-5l.5-6z"/>',
  dots: '<path d="M5 10h.01M10 10h.01M15 10h.01" stroke-width="2.2"/>',
  calendar: '<rect x="3.5" y="4.5" width="13" height="12" rx="2"/><path d="M3.5 8.5h13M7 3v3M13 3v3"/>',
  mail: '<rect x="3" y="4.5" width="14" height="11" rx="2"/><path d="M3.5 6l6.5 5 6.5-5"/>',
  quote: '<path d="M4.5 13.5v-3A3.5 3.5 0 018 7M11.5 13.5v-3A3.5 3.5 0 0115 7"/>',
  circle: '<circle cx="10" cy="10" r="6.5"/>',
  circleDash: '<circle cx="10" cy="10" r="6.5" stroke-dasharray="2.6 3"/>',
  checkCircle: '<circle cx="10" cy="10" r="7"/><path d="M6.8 10.2l2.2 2.2 4.2-4.6"/>',
  lock: '<rect x="4.5" y="9" width="11" height="8" rx="2"/><path d="M7 9V6.5a3 3 0 016 0V9"/>',
  panel: '<rect x="3" y="4" width="14" height="12" rx="2"/><path d="M12 4v12"/>',
  pin: '<path d="M10 17.5s5-4.6 5-8.5a5 5 0 00-10 0c0 3.900 5 8.500 5 8.500z"/><circle cx="10" cy="9" r="1.8"/>',
  layers: '<path d="M10 3l7 3.800-7 3.800-7-3.800L10 3z"/><path d="M3.500 10.500l6.500 3.500 6.500-3.500M3.500 13.800L10 17.300l6.500-3.500"/>',
  send: '<path d="M10 15.500V4.500M5.500 9l4.500-4.500L14.500 9"/>',
  sliders: '<path d="M4 6h7M15 6h1M4 14h1M9 14h7"/><circle cx="13" cy="6" r="1.800"/><circle cx="7" cy="14" r="1.800"/>',
  eye: '<path d="M2.500 10S5.200 5 10 5s7.500 5 7.500 5-2.700 5-7.500 5-7.500-5-7.500-5z"/><circle cx="10" cy="10" r="2.200"/>',
  search: '<circle cx="9" cy="9" r="5.5"/><path d="M13.2 13.2L17 17"/>',
  undo: '<path d="M7 5L3.500 8.500 7 12"/><path d="M4 8.500h7.500a4.500 4.500 0 010 9H9"/>',
};
export const ic = (name, size = 20, cls = '') => {
  if (!P[name]) throw new Error('no icon ' + name);
  return `<svg class="ic ${cls}" width="${size}" height="${size}" viewBox="0 0 20 20" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${P[name]}</svg>`;
};

// ——— демо-сценарий (общий для всех концепций; это макетный контент, не ответ действующей модели)
export const T = {
  q1: 'У нас выросли счета за электроэнергию на складе. С чего начать?',
  clar: 'У вас есть показания по отдельным зонам или только общая сумма?',
  a1: 'Только общая сумма. Показания снимаем вручную раз в месяц.',
  ans: 'Начните со сравнения счетов и показаний за сопоставимые периоды. Уточните, менялись ли режим работы склада и состав оборудования. Затем можно обсудить, нужен ли более подробный учёт.',
  ansParts: [
    'Начните со сравнения счетов и показаний за сопоставимые периоды.',
    'Уточните, менялись ли режим работы склада и состав оборудования.',
    'Затем можно обсудить, нужен ли более подробный учёт.',
  ],
  label: 'EnergyTool · ИИ-консультант',
  foot: 'ИИ может ошибаться. Не отправляйте конфиденциальные данные.',
  wait: 'Первый ответ может занять больше времени, пока запускается модель.',
};

export const header = ({ busy = false, mobile = false, extra = '', cls = '' } = {}) => mobile
  ? `<header class="et-header ${cls}"><a class="et-brand"><strong>МТС</strong><span>EnergyTool<span class="et-brand-divider"> / </span><span class="et-brand-subtitle">ИИ-консультант</span></span></a>${extra}<button class="btn" ${busy ? 'disabled' : ''}>Меню</button></header>`
  : `<header class="et-header ${cls}"><a class="et-brand"><strong>МТС</strong><span>EnergyTool<span class="et-brand-divider"> / </span><span class="et-brand-subtitle">ИИ-консультант</span></span></a><button class="btn" ${busy ? 'disabled' : ''}>Новый диалог</button><button class="btn" ${busy ? 'disabled' : ''}>История диалогов</button><button class="btn" ${busy ? 'disabled' : ''}>Меню</button>${extra}</header>`;

export const sideNote = () => `<div class="et-side-note"><p>Не передавайте пароли и платёжные данные.</p><p>ИИ может ошибаться. Проверяйте важные решения со специалистом.</p></div>`;

export const user = (text, cls = '') => `<div class="et-message et-user ${cls}">${text}</div>`;
export const bot = (html, { label = T.label, cls = '' } = {}) => `<div class="et-message et-assistant ${cls}"><div class="et-message-label">${label}</div><div class="et-message-body">${html}</div></div>`;

// Поле ввода: v2 — кнопка справа, подсказка слева (геометрия оболочки как в chat.css)
export const composer = ({ value = '', placeholder = 'Опишите вашу задачу', hint = 'Enter — отправить · Shift+Enter — новая строка', send = 'Отправить', can = false, focus = false, cls = '', left = '', extra = '' } = {}) =>
  `<form class="et-composer v2 ${focus ? 'is-focus' : ''} ${cls}">${extra}<div class="ta ${value ? '' : 'ph'}">${focus && !value ? '<i class="caret lead"></i>' : ''}${value || placeholder}${focus && value ? '<i class="caret"></i>' : ''}</div><div class="et-compose-actions">${left || `<span>${hint}</span>`}<button class="btn primary et-send" ${can ? '' : 'disabled'}>${send}</button></div></form>`;

// мобильное поле ввода в одну строку
export const mcomposer = ({ value = '', placeholder = 'Опишите вашу задачу', can = false, cls = '', note = '' } = {}) =>
  `<form class="m-composer ${cls}"><div class="ta ${value ? '' : 'ph'}">${value || placeholder}</div><button class="m-send ${can ? '' : 'is-disabled'}" aria-label="Отправить">${ic('send', 20)}</button></form>${note ? `<p class="m-note">${note}</p>` : ''}`;

export const footer = (t = T.foot) => `<footer class="et-footer">${t}</footer>`;

export const bars = (cls = '') => `<span class="bars ${cls}" aria-hidden="true"><i></i><i></i><i></i></span>`;

export const page = ({ id, title, concept, w = 1440, h = 960, mobile = false, body, bodyCls = '' }) =>
  `<!doctype html>
<html lang="ru"><head><meta charset="utf-8"><meta name="viewport" content="width=${w}">
<title>${esc(title)}</title>
<link rel="stylesheet" href="../css/base.css"><link rel="stylesheet" href="../css/kit.css"><link rel="stylesheet" href="../css/${concept}.css">
</head>
<body class="et-app ${concept} ${mobile ? 'm' : 'd'} ${bodyCls}" data-screen="${id}" style="width:${w}px;height:${h}px">
${body}
</body></html>
`;
