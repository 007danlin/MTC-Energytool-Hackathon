// Контрольное воспроизведение исходного экрана 01-welcome.png на общих токенах (для сверки каркаса).
import { T, header, sideNote, footer } from './lib.mjs';
export const screens = [{
  id: 'b00-baseline', concept: 'c01', title: 'Исходный экран — контрольное воспроизведение',
  body: `${header()}
<aside class="et-sidebar"><p class="et-eyebrow">КОНСУЛЬТАЦИЯ</p><section class="et-card et-focus"><h2>Ваша задача<br>в фокусе</h2><p>Учёт, расходы и потери электроэнергии</p></section><button class="et-side-link">Новый диалог</button><button class="et-side-link">История диалогов</button>${sideNote()}</aside>
<main class="et-workspace"><div class="et-scroll"><section class="et-welcome"><p class="et-eyebrow">КОНСУЛЬТАЦИЯ ПО ЭЛЕКТРОЭНЕРГИИ</p><h1>Что хотите решить<br>с электроэнергией?</h1><p class="et-intro">Помогу разобраться в расходах, наладить учёт и понять, где искать потери.</p><div class="et-suggestions"><button class="btn">Снизить расходы</button><button class="btn">Наладить учёт</button><button class="btn">Найти потери</button></div><p class="et-hint">Подсказка подставит вопрос. Его можно изменить перед отправкой.</p></section></div>
<form class="et-composer"><div class="ta ph">Опишите вашу задачу</div><div class="et-compose-actions"><span>Enter — отправить · Shift+Enter — новая строка</span><button class="btn primary et-send" disabled>Отправить</button></div></form>${footer()}</main>`,
}];
