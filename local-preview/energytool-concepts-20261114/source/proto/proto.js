// Демонстрационный прототип направления A «Живая задача».
// Ответы — заранее записанный макетный контент; задержки — проектные допущения, а не скорость модели.
(() => {
  const $ = (s, r = document) => r.querySelector(s);
  const el = html => { const t = document.createElement('template'); t.innerHTML = html.trim(); return t.content.firstElementChild; };
  const IC = window.__IC;
  const ic = (n, s = 20) => `<svg class="ic" width="${s}" height="${s}" viewBox="0 0 20 20" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${IC[n]}</svg>`;
  const bars = '<span class="bars" aria-hidden="true"><i></i><i></i><i></i></span>';
  const LABEL = 'EnergyTool · ИИ-консультант';
  const SC = { fast: { d1: 2600, d2: 3200 }, long: { d1: 14000, d2: 5200 }, vlong: { d1: 34000, d2: 5200 }, error: { d1: 7000, d2: 3200, err: true } };
  const T_PENDING = 350, T_SUPP = 4000, T_LONG = 20000;
  const Q = 'У нас выросли счета за электроэнергию на складе. С чего начать?';
  const CLAR = 'У вас есть показания по отдельным зонам или только общая сумма?';
  const ANS = 'Начните со сравнения счетов и показаний за сопоставимые периоды. Уточните, менялись ли режим работы склада и состав оборудования. Затем можно обсудить, нужен ли более подробный учёт.';
  const OBJECTS = [['склад', 'Склад'], ['офис', 'Офис'], ['магазин', 'Магазин'], ['цех', 'Цех'], ['производств', 'Производство']];

  const ws = $('#ws'), thread = $('#thread'), form = $('#composer'), ta = $('#q'), sendBtn = $('.et-send'), hint = $('#hint'), below = $('#below');
  let step = 0, busy = false, timers = [], tick = null, t0 = 0, pendingEl = null, errored = false;
  const scenario = () => $('#scenario').value;
  const later = (fn, ms) => { const id = setTimeout(fn, ms); timers.push(id); return id; };
  const clearAll = () => { timers.forEach(clearTimeout); timers = []; clearInterval(tick); };
  const fmt = ms => { const s = Math.floor(ms / 1000); return Math.floor(s / 60) + ':' + String(s % 60).padStart(2, '0'); };
  const esc = s => s.replace(/&/g, '&amp;').replace(/</g, '&lt;');

  // FLIP: поле ввода и блоки под ним переезжают плавно, без скачка
  const flip = (els, mutate) => {
    const first = els.map(e => e.getBoundingClientRect().top);
    mutate();
    if (document.body.classList.contains('rm') || matchMedia('(prefers-reduced-motion:reduce)').matches) return;
    els.forEach((e, i) => { const d = first[i] - e.getBoundingClientRect().top; if (Math.abs(d) < 1) return; e.animate([{ transform: `translateY(${d}px)` }, { transform: 'none' }], { duration: 300, easing: 'cubic-bezier(.2,.8,.2,1)' }); });
  };
  const stayPinned = () => { ws.scrollTop = ws.scrollHeight; };

  // ——— карточка задачи
  const rowHTML = (icon, key, val, meta, cls = '') => `<div class="trow ${cls}" data-k="${key}"><span class="ti">${ic(icon, 18)}</span><div class="tb"><span class="tk">${key}</span>${val}${meta ? `<span class="tm">${meta}</span>` : ''}</div></div>`;
  const setRow = (icon, key, val, meta, isNew = true) => {
    const old = $(`.trow[data-k="${key}"]`);
    const n = el(rowHTML(icon, key, val, meta, isNew ? 'new flash' : ''));
    old.replaceWith(n);
  };
  const setStatus = (t, on = true) => { $('#tstatus').innerHTML = `<span class="dot ${on ? '' : 'off'}"></span>${t}`; };
  const resetCard = () => {
    $('#trows').innerHTML = rowHTML('building', 'Объект', '<p class="tv ph">Склад, офис, магазин, цех</p>', '', 'empty') + rowHTML('target', 'Задача', '<p class="tv ph">Что хотите решить</p>', '', 'empty') + rowHTML('checkCircle', 'Что известно', '<p class="tv ph">Факты из ваших ответов</p>', '', 'empty') + rowHTML('question', 'Что уточнить', '<p class="tv ph">Открытые вопросы</p>', '', 'empty');
    setStatus('Заполняется по ходу разговора', false);
  };

  const userMsg = t => el(`<div class="et-message et-user enter">${esc(t)}</div>`);
  const botMsg = html => el(`<div class="et-message et-assistant enter"><div class="et-message-label">${LABEL}</div><div class="et-message-body">${html}</div></div>`);
  const pendHTML = () => `<div class="pend fadein" role="status"><div class="row between"><span class="label">${LABEL}</span><span class="timer" id="timer">Жду ответ 0:00</span></div><div class="pend-main">${bars}<span id="ptext">Готовлю ответ…</span></div><p class="et-hint" id="phint">Первый ответ может занять больше времени, пока запускается модель.</p><div class="lw-extra" id="lw"></div></div>`;

  const setBusy = b => {
    busy = b;
    sendBtn.disabled = b || !ta.value.trim();
    ta.placeholder = b ? 'Можно писать следующее сообщение' : (step === 0 ? 'Опишите вашу задачу своими словами' : 'Напишите сообщение');
    hint.textContent = b ? 'Отправка откроется, когда придёт ответ. Черновик сохранится.' : 'Enter — отправить · Shift+Enter — новая строка';
  };

  function send(text) {
    if (busy || !text.trim()) return;
    const sc = SC[scenario()];
    const welcome = $('#welcome');
    $('.qr')?.remove();
    flip([$('.dockwrap'), below], () => {
      if (welcome) welcome.remove();
      below.innerHTML = '';
      thread.append(userMsg(text));
    });
    ta.value = ''; autosize(); step += 1; setBusy(true); t0 = performance.now(); errored = false;
    // карточка: только то, что известно клиенту сразу
    if (step === 1) {
      setRow('target', 'Задача', `<p class="tv">«${esc(text)}»</p>`, 'ваш вопрос дословно');
      const hit = OBJECTS.find(([k]) => text.toLowerCase().includes(k));
      if (hit) later(() => setRow('building', 'Объект', `<p class="tv">${hit[1]}</p>`, 'из вашего вопроса'), 160);
      setStatus('Записал вопрос. Остальное — после ответа');
    } else {
      setRow('checkCircle', 'Что известно', `<p class="tv">«${esc(text)}»</p>`, '<i class="nw">новое</i> · ваш ответ дословно');
      $('.trow[data-k="Что уточнить"]').replaceWith(el(rowHTML('question', 'Что уточнить', '<p class="tv ph">Появится после ответа</p>', '', 'empty')));
      setStatus('Записал ответ. Жду консультанта');
    }
    stayPinned();
    later(() => {
      flip([$('.dockwrap'), below], () => { pendingEl = el(pendHTML()); thread.append(pendingEl); });
      stayPinned();
      tick = setInterval(() => { const t = $('#timer'); if (t) t.textContent = 'Жду ответ ' + fmt(performance.now() - t0); }, 250);
    }, T_PENDING);
    later(() => {
      if (!busy) return;
      below.innerHTML = `<div class="supp fadein"><p class="label">Пока жду ответ, можно дополнить задачу</p><p class="cap muted">Добавлю в карточку и учту со следующим сообщением. В уже отправленный вопрос это не попадёт.</p><div class="supp-chips"><button type="button" class="chip dash lg" data-add="Счета выросли с ">${ic('plus', 16)}Когда выросли счета</button><button type="button" class="chip dash lg" data-add="На объекте менялось: ">${ic('plus', 16)}Что менялось на объекте</button><button type="button" class="chip dash lg" data-add="Показания снимаем ">${ic('plus', 16)}Как снимаете показания</button></div></div>`;
    }, T_SUPP);
    later(() => {
      if (!busy || !pendingEl) return;
      $('#ptext').textContent = 'Всё ещё готовлю ответ';
      $('#phint').textContent = 'Это дольше, чем хотелось бы. Ваш вопрос сохранён в диалоге и не потеряется.';
      const lw = $('#lw');
      flip([$('.dockwrap'), below], () => { lw.innerHTML = `<div class="fadein"><div class="lw-acts"><button type="button" class="btn sm" data-toast="Путь к заявке показан на статичных экранах состояний">Оставить заявку специалисту</button><button type="button" class="btn sm ghost" data-abort>Прервать ожидание</button></div><p class="cap muted lw-n">К заявке приложу ваш вопрос. Если прервать, сначала сверю диалог с сервером: ответ мог успеть прийти.</p></div>`; });
    }, T_LONG);
    later(respond, step === 1 ? sc.d1 : sc.d2);
  }

  function respond() {
    const sc = SC[scenario()];
    clearAll();
    const old = pendingEl; pendingEl = null;
    const swap = node => {
      // ответ занимает место блока ожидания: позиция чтения сохраняется, страница не прыгает
      const pinned = ws.scrollHeight - ws.scrollTop - ws.clientHeight < 4;
      flip([$('.dockwrap'), below], () => { old?.remove(); below.innerHTML = ''; thread.append(...[].concat(node)); });
      if (pinned) stayPinned();
    };
    if (sc.err && step === 1 && !errored) {
      errored = true;
      const e = el(`<section class="et-error errc enter"><div class="row errh">${ic('alert', 20)}<h3>Ответ не пришёл</h3></div><ul class="facts"><li class="ok">${ic('check', 16)}<span>Ваш вопрос сохранён в диалоге</span></li><li class="unk">${ic('question', 16)}<span>Неизвестно, успел ли консультант его получить</span></li><li class="ok">${ic('check', 16)}<span>Карточка задачи и черновик на месте</span></li></ul><p>Сначала сверю диалог с сервером. Если ответа там нет, отправлю вопрос ещё раз — без дубля.</p><div class="row erra"><button type="button" class="btn primary" data-retry>Сверить и повторить</button><button type="button" class="btn" data-toast="Путь к заявке показан на статичных экранах состояний">Оставить заявку специалисту</button></div></section>`);
      swap(e); setStatus('Карточка на месте. Жду сверки с сервером', false);
      hint.textContent = 'Отправка откроется после сверки с сервером.';
      return;
    }
    if (step === 1) {
      const m = botMsg(esc(CLAR) + `<div class="qr"><button type="button" class="btn" data-reply="Только общая сумма. Показания снимаем вручную раз в месяц.">Только общая сумма</button><button type="button" class="btn" data-reply="Есть показания по отдельным зонам.">Есть по зонам</button><button type="button" class="btn" data-reply="Не знаю, нужно уточнить.">Не знаю</button><span class="cap muted">или ответьте своими словами</span></div>`);
      swap(m);
      later(() => setRow('question', 'Что уточнить', '<ul class="tl q"><li class="n">Показания по зонам или только общая сумма</li></ul>', '<i class="nw">спрашиваю сейчас</i>'), 180);
      setStatus('Жду ваш ответ на уточнение');
    } else {
      const m = botMsg(esc(ANS));
      const upd = el(`<div class="upd fadein">${ic('refresh', 16)}<span>Карточка задачи обновлена: 2 факта в «Что известно», 2 вопроса в «Что уточнить»</span></div>`);
      const nx = el(`<section class="et-card next enter" style="animation-delay:120ms"><h3>Что дальше</h3><div class="next-grid"><div><button type="button" class="btn primary wide" data-toast="Путь к заявке показан на статичных экранах состояний">Подготовить обращение специалисту</button><p class="cap muted">В обращение попадёт карточка задачи. Вы проверите её перед сохранением.</p></div><div><button type="button" class="btn wide" data-focus>Продолжить консультацию</button><p class="cap muted">Ответьте на открытые вопросы или задайте свой. Контакты не нужны.</p></div></div></section>`);
      swap([m, upd, nx]);
      later(() => setRow('target', 'Задача', '<p class="tv">Понять, почему выросли счета за электроэнергию</p>', '', false), 0);
      later(() => setRow('checkCircle', 'Что известно', '<ul class="tl"><li class="n">Виден только общий счёт</li><li class="n">Показания снимают вручную раз в месяц</li></ul>', '<i class="nw">новое</i> · из ваших ответов'), 140);
      later(() => setRow('question', 'Что уточнить', '<ul class="tl q"><li>Менялся ли режим работы склада</li><li>Менялся ли состав оборудования</li></ul>', '<i class="nw">новое</i> · из ответа консультанта'), 280);
      setStatus('Обновлено: 2 факта, 2 вопроса');
    }
    setBusy(false);
  }

  function reset() {
    clearAll(); step = 0; busy = false; pendingEl = null; errored = false;
    thread.innerHTML = ''; below.innerHTML = `<div class="row between under"><p class="et-hint">Подсказка подставит вопрос. Его можно изменить перед отправкой.</p></div>`;
    $('#welcome')?.remove();
    thread.before(el(`<section class="et-welcome" id="welcome"><p class="et-eyebrow">КОНСУЛЬТАЦИЯ ПО ЭЛЕКТРОЭНЕРГИИ</p><h1>Что хотите решить<br>с электроэнергией?</h1><p class="et-intro">Помогу разобраться в расходах, наладить учёт и понять, где искать потери.</p><div class="et-suggestions"><button type="button" class="btn" data-suggest="${Q}">Снизить расходы</button><button type="button" class="btn" data-suggest="Хочу наладить учёт электроэнергии на складе. С чего начать?">Наладить учёт</button><button type="button" class="btn" data-suggest="Хочу понять, где возникают потери электроэнергии. С чего начать?">Найти потери</button></div><div style="height:24px"></div></section>`));
    ta.value = ''; autosize(); resetCard(); setBusy(false); ws.scrollTop = 0;
  }

  const autosize = () => { ta.style.height = 'auto'; ta.style.height = Math.min(ta.scrollHeight, 120) + 'px'; sendBtn.disabled = busy || !ta.value.trim(); };
  const toast = t => { $('.toast')?.remove(); const n = el(`<div class="toast fadein" role="status">${t}</div>`); $('.stage').append(n); setTimeout(() => n.remove(), 3200); };

  ta.addEventListener('input', autosize);
  ta.addEventListener('keydown', e => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); send(ta.value); } });
  form.addEventListener('submit', e => { e.preventDefault(); send(ta.value); });
  document.addEventListener('click', e => {
    const b = e.target.closest('button'); if (!b) return;
    if (b.dataset.suggest) { ta.value = b.dataset.suggest; autosize(); ta.focus(); }
    else if (b.dataset.reply) send(b.dataset.reply);
    else if (b.dataset.add) { ta.value = (ta.value ? ta.value.replace(/\s*$/, ' ') : '') + b.dataset.add; autosize(); ta.focus(); }
    else if (b.dataset.toast) toast(b.dataset.toast);
    else if ('focus' in b.dataset) ta.focus();
    else if ('retry' in b.dataset) { b.closest('.errc').remove(); setBusy(true); t0 = performance.now(); pendingEl = el(pendHTML()); thread.append(pendingEl); $('#ptext').textContent = 'Сверяю диалог и отправляю вопрос ещё раз…'; $('#phint').textContent = 'Дубля не будет: сначала проверю, не пришёл ли ответ.'; tick = setInterval(() => { const t = $('#timer'); if (t) t.textContent = 'Жду ответ ' + fmt(performance.now() - t0); }, 250); later(respond, 2600); }
    else if ('abort' in b.dataset) { clearAll(); pendingEl?.remove(); pendingEl = null; below.innerHTML = ''; setBusy(false); step -= 1; toast('Ожидание прервано. Сверил диалог: ответа не было, вопрос остался в ленте — его можно отправить ещё раз.'); }
    else if (b.id === 'restart') reset();
  });
  $('#rm').addEventListener('change', e => document.body.classList.toggle('rm', e.target.checked));
  const p = new URLSearchParams(location.search);
  if (p.get('scenario')) $('#scenario').value = p.get('scenario');
  if (p.get('rm')) { $('#rm').checked = true; document.body.classList.add('rm'); }
  window.__proto = { send, reset, Q };
  reset();
})();
