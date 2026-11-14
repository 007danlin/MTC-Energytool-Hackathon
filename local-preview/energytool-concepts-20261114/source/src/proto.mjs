// Сборка автономного прототипа: node src/proto.mjs
import fs from 'node:fs';
import path from 'node:path';
const root = path.resolve(path.dirname(new URL(import.meta.url).pathname), '..');
const rd = f => fs.readFileSync(path.join(root, f), 'utf8');
const font = fs.readFileSync(path.join(root, 'fonts/Inter.ttf')).toString('base64');
const lib = rd('src/lib.mjs');
const icons = lib.slice(lib.indexOf('const P = {') + 10, lib.indexOf('};', lib.indexOf('const P = {')) + 1);
let css = [rd('css/base.css'), rd('css/kit.css'), rd('css/c02.css'), rd('proto/proto.css')].join('\n');
css = css.replace("url('../fonts/Inter.ttf') format('truetype')", `url(data:font/ttf;base64,${font}) format('truetype')`);
const html = `<!doctype html>
<html lang="ru"><head><meta charset="utf-8"><meta name="viewport" content="width=1440">
<title>EnergyTool — прототип «Живая задача»: отправка → ожидание → ответ</title>
<style>${css}</style></head>
<body class="et-app c02 d live">
<div class="pbar"><b>Демонстрационный прототип</b><span class="muted">Направление A «Живая задача». Ответы записаны заранее, задержки — проектные допущения</span><span class="sp"></span>
<label>Сценарий <select id="scenario"><option value="fast">быстрый ответ, ~3 с</option><option value="long" selected>долгий ответ, 14 с</option><option value="vlong">очень долгий, 34 с</option><option value="error">обрыв и повтор</option></select></label>
<label><input type="checkbox" id="rm"> меньше движения</label><button id="restart" type="button">Сначала</button></div>
<div class="stage">
<header class="et-header"><a class="et-brand"><strong>МТС</strong><span>EnergyTool<span class="et-brand-divider"> / </span><span class="et-brand-subtitle">ИИ-консультант</span></span></a><button class="btn" id="restart2" type="button" onclick="document.getElementById('restart').click()">Новый диалог</button><button class="btn" type="button" data-toast="История в прототипе не подключена">История диалогов</button><button class="btn" type="button" data-toast="Меню в прототипе не подключено">Меню</button></header>
<aside class="et-sidebar"><p class="et-eyebrow">КОНСУЛЬТАЦИЯ</p><section class="et-card task"><h2>Ваша задача<br>в фокусе</h2><p class="tstatus" id="tstatus"></p><div class="trows" id="trows"></div><p class="tfoot cap muted">Соберу карточку из ваших слов. Любую строку можно будет исправить.</p></section><div class="et-side-note"><p>Не передавайте пароли и платёжные данные.</p><p>ИИ может ошибаться. Проверяйте важные решения со специалистом.</p></div></aside>
<main class="et-workspace" id="ws"><div class="pad"></div><div class="et-messages" id="thread" role="log" aria-live="polite"></div>
<div class="dockwrap"><form class="et-composer v2" id="composer"><label class="et-sr-only" for="q" style="position:absolute;width:1px;height:1px;overflow:hidden;clip:rect(0,0,0,0)">Ваш вопрос</label><textarea id="q" rows="1" maxlength="10000" placeholder="Опишите вашу задачу своими словами"></textarea><div class="et-compose-actions"><span id="hint">Enter — отправить · Shift+Enter — новая строка</span><button type="submit" class="btn primary et-send" disabled>Отправить</button></div></form></div>
<div id="below"></div><footer class="et-footer">ИИ может ошибаться. Не отправляйте конфиденциальные данные.</footer></main>
</div>
<script>window.__IC=${icons};</script>
<script>${rd('proto/proto.js')}</script>
</body></html>`;
fs.mkdirSync(path.join(root, 'dist'), { recursive: true });
fs.writeFileSync(path.join(root, 'dist/prototype.html'), html);
console.log('prototype', (html.length / 1024 | 0) + ' KB');
