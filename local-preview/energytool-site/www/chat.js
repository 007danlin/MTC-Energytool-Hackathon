(() => {
  'use strict';
  // Keep the original MTS application. Add a separate entry point below its CTA.
  if (!document.body.classList.contains('et-app')) {
    const install = () => {
      document.querySelectorAll('#root button').forEach(button => {
        if (button.textContent.trim() !== 'Заказать консультацию') return;
        const parent = button.parentElement;
        if (parent.querySelector('.et-online-link')) return;
        parent.classList.add('et-entry-stack');
        if (parent.parentElement.textContent.includes('Войти в кабинет')) parent.classList.add('et-entry-hero');
        const link = document.createElement('a');
        link.className = 'et-online-link';
        link.href = '/consultation.html?start=new&return=' + encodeURIComponent(location.pathname + location.search + location.hash);
        link.innerHTML = '<span>Онлайн-консультация</span><span class="et-new-badge">new</span>';
        link.setAttribute('aria-label','Онлайн-консультация');
        button.after(link);
        const fit = () => { if (innerWidth > 760) parent.style.setProperty('--et-original-width',button.getBoundingClientRect().width+'px'); };
        fit();new ResizeObserver(fit).observe(button);
      });
    };
    install();
    new MutationObserver(install).observe(document.getElementById('root') || document.body, {childList:true,subtree:true});
    return;
  }
  const host = document.getElementById('energytool-chat');
  const $ = s => host.querySelector(s);
  const messages = $('.et-messages'), flow = $('.et-flow'), scroll = $('.et-scroll');
  const input = $('#et-question'), modal = $('.et-modal'), modalBody = $('.et-modal-body');
  const escape = value => String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const button = (label, action, primary = false) => `<button type="button" data-action="${action}"${primary ? ' class="et-primary"' : ''}>${label}</button>`;
  let current = null, busy = false, needsSync = false, debug = false, draft = null, stage = 'chat', notice = '', modalFocus = null, selectedSource = null, archived = null, noPhone = false, collapsedAt = 0, pending = false;
  let savedID;
  try { savedID = localStorage.getItem('energytool-session'); } catch (_) {}
  let returnPath = '/';
  const candidate = new URLSearchParams(location.search).get('return');
  if (candidate) { try { const url = new URL(candidate, location.origin); if (url.origin === location.origin && url.pathname !== '/consultation.html') returnPath = url.pathname + url.search + url.hash; } catch (_) {} }
  $('.et-brand').href = returnPath;
  let knownIDs = new Set();
  try { knownIDs = new Set(JSON.parse(localStorage.getItem('energytool-session-ids') || '[]')); } catch (_) {}
  if(savedID) knownIDs.add(savedID);
  const remember = id => { if(id) { knownIDs.add(id); try { localStorage.setItem('energytool-session-ids',JSON.stringify([...knownIDs])); } catch (_) {} } savedID = id; try { id ? localStorage.setItem('energytool-session',id) : localStorage.removeItem('energytool-session'); } catch (_) {} };
  const card = (title, body, actions, cls = '') => `<section class="et-card ${cls}"><h2>${title}</h2>${body}<div class="et-stack">${actions}</div></section>`;
  const assistant = text => messageHTML({role:'assistant',content:text});
  const previous = () => button('Предыдущая переписка','transcript');
  const isClosed = () => current?.status === 'closed';
  function status(text, retry = false) {
    notice = text;
    $('.et-status').hidden = !text;
    $('.et-status').innerHTML = escape(text) + (retry ? button('Обновить историю', 'refresh') : '');
  }
  function controls() {
    host.querySelectorAll('[data-action], [data-prompt], [data-session], [data-reply], [data-source-message], [data-fragment], .et-flow input, .et-flow textarea, .et-contact-form button, .et-edit-form input, .et-edit-form textarea, .et-edit-form button').forEach(el => {
      el.disabled = busy && el.dataset.action !== 'dismiss';
    });
    input.disabled = busy || !current || isClosed() || needsSync;
    $('.et-send').disabled = input.disabled || !input.value.trim();
    $('.et-send').textContent = busy ? 'Подождите…' : 'Отправить';
  }
  async function api(path, body) {
    const response = await fetch('/api/v1' + path, {method:body === undefined ? 'GET':'POST',
      headers:body == null ? {} : {'Content-Type':'application/json'},
      body:body == null ? undefined:JSON.stringify(body), signal:AbortSignal.timeout(275000)});
    let data; try { data = await response.json(); } catch (_) { throw new Error('Сервис вернул некорректный ответ.'); }
    if (!response.ok) {
      const labels = {not_found:'Диалог не найден.',session_closed:'Диалог завершён. Начните новый.', history_limit:'Достигнут лимит диалога. Начните новый — история сохранена.', invalid_application:'Проверьте телефон и описание задачи.', message_too_long:'Сообщение слишком длинное.',empty_message:'Введите вопрос.'};
      const error = new Error(labels[data.code] || data.message || 'Сервис временно недоступен.'); error.code = data.code; throw error;
    }
    return data;
  }
  async function run(fn) {
    if (busy) return;
    busy = true; controls();
    try { await fn(); } catch (error) { status(error.name === 'TimeoutError' ? 'Ответ занимает больше времени. Обновите историю перед повторной отправкой.' : error.message || 'Не удалось подключиться к сервису.', true); if (modal.open) { let alert = modalBody.querySelector('.et-modal-error'); if (!alert) { alert = document.createElement('p'); alert.className = 'et-error et-modal-error'; alert.setAttribute('role','alert'); modalBody.append(alert); } alert.textContent = notice; } }
    finally { busy = false; controls(); }
  }
  function adopt(session) {
    current = session; remember(session.id);
    needsSync = session.status === 'active' && session.messages.at(-1)?.role === 'user';
    if (needsSync) status('Ответ ещё не сохранён. Обновите историю через некоторое время.', true);
  }
  function metadata(message, index) {
    return message.response || (index === current?.messages.length - 1 ? current.last_result : null);
  }
  function messageHTML(message) {
    return `<article class="et-message ${message.role === 'user' ? 'et-user' : 'et-assistant'}">${message.role === 'user' ? '' : '<div class="et-message-label">EnergyTool · ИИ-консультант</div>'}<div class="et-message-body">${escape(message.content)}</div></article>`;
  }
  function debugCard(result, index) {
    return `<section class="et-card et-debug"><p class="et-hint">Отладка включена · данные этого ответа</p><div class="et-stack"><button data-source-message="${index}">${escape((result.elapsed_ms/1000).toLocaleString('ru-RU',{maximumFractionDigits:1}))} с · ${result.sources?.length || 0} источников · Подробнее</button>${button('Выключить отладку','debug')}</div></section>`;
  }
  function chatMessages() {
    return (current?.messages || []).slice(collapsedAt).map((m, offset) => {
      const index = offset + collapsedAt, result = metadata(m,index);
      if(m.role==='user' && index>1 && metadata(current.messages[index-1],index-1)?.status==='technical_error' && current.messages[index-2]?.content===m.content)return '';
      if (m.role === 'assistant' && result?.status === 'technical_error') {
        return index === current.messages.length - 1 ? '' : '<p class="et-hint">Не удалось получить ответ. Вопрос сохранён.</p>';
      }
      return messageHTML(m) + (m.role === 'assistant' && debug && result ? (index === current.messages.length-1 ? debugCard(result,index) : `<button class="et-debug-link" data-source-message="${index}">Источники этого ответа</button>`) : '');
    }).join('');
  }
  function clarificationChoices(answer) {
    // Only offer the design's shortcuts when they actually answer this question.
    if (/показани|сч[её]тчик/i.test(answer) && /общ|кажд|отдельн/i.test(answer)) return ['Вижу только общую сумму','Есть показания по каждому'];
    if (/есть ли.*прибор|есть.*прибор.*уч[её]т/i.test(answer)) return ['Есть приборы учёта','Пока нет приборов учёта'];
    return [];
  }
  function render() {
    const empty = !current?.messages.length;
    $('.et-welcome').hidden = !empty || stage !== 'chat' || pending;
    messages.hidden = stage !== 'chat';
    messages.innerHTML = (collapsedAt && stage === 'chat' ? previous() : '') + chatMessages();
    flow.replaceChildren();
    if (stage === 'contacts') renderContacts();
    else if (stage === 'review') renderReview(draft,false);
    else if (stage === 'saved') renderReview(current.application,true);
    else if (stage === 'declined') {
      flow.innerHTML = previous() + messageHTML({role:'user',content:'Продолжить без телефона'}) + assistant('Хорошо, можем продолжить без телефона. Хотите разобраться, какие данные собрать по вашей задаче?') + `<div class="et-stack"><button data-reply="Какие данные нужно собрать по моей задаче?">Какие данные собрать?</button>${button('Вернуться к заявке','contacts')}</div>`;
    } else if (pending) {
      flow.innerHTML = `<div class="et-pending" role="status">${assistant('Готовлю ответ…')}<p class="et-hint">Локальная модель обычно отвечает за 1–2 минуты. Первый ответ может занять дольше.</p></div>`;
    } else if (isClosed()) {
      flow.innerHTML = card('Диалог сохранён','<p>Эта переписка доступна для чтения в истории.</p>',button('Начать новый диалог','new',true));
    } else {
      const result = current?.last_result;
      const state = result?.status;
      host.dataset.screen = empty ? 'welcome' : state || 'conversation';
      if (state === 'technical_error') {
        flow.innerHTML = card('Не удалось получить ответ','<p>Ваш вопрос сохранён. Попробуйте ещё раз.</p>',button('Повторить','retry',true),'et-error');
      } else if (state === 'out_of_scope') {
        flow.innerHTML = `<div class="et-stack">${button('Задать другой вопрос','continue')}</div>`;
      } else if (state === 'knowledge_gap') {
        flow.innerHTML = `<div class="et-stack">${button('Подготовить заявку','contacts',true)}${button('Задать другой вопрос','continue')}</div>`;
      } else if (noPhone && state !== 'technical_error') {
        flow.innerHTML = `<div class="et-stack">${button('Вернуться к заявке','contacts')}</div>`;
      } else if (state === 'clarification') {
        const choices = clarificationChoices(result.answer || current.messages.at(-1)?.content || '');
        flow.innerHTML = `<div class="et-stack et-replies">${choices.map((text,i)=>`<button class="${i===0?'et-primary':''}" data-reply="${escape(text)}">${escape(text)}</button>`).join('')}</div>`;
      } else if (state === 'answered' && !current?.application) {
        flow.innerHTML = card('Разобраться вместе со специалистом','<p>Могу подготовить заявку с описанием вашей ситуации.</p>',button('Подготовить заявку','contacts',true)+button('Продолжить консультацию','continue'));
      } else if (current?.application && !empty) {
        flow.innerHTML = `<div class="et-stack">${button('Сохранённая заявка','application')}</div>`;
      }
    }
    if (stage !== 'chat') host.dataset.screen = stage;
    if (pending) host.dataset.screen = 'waiting';
    controls();
  }
  function summaryText() {
    const summary = current?.last_result?.summary || {};
    const parts = ['task','object','parameters','constraints'].flatMap(k => Array.isArray(summary[k]) ? summary[k] : []).map(v => typeof v === 'string' ? v : v?.value || v?.text || v?.quote || '').filter(Boolean);
    return (parts.join(' ') || current?.messages.find(m => m.role === 'user')?.content || '').slice(0,2000);
  }
  function startContacts() {
    if (!current || isClosed()) return;
    const fields = current.lead?.fields || {};
    draft = draft || (current.application ? {...current.application} : {full_name:fields.full_name || '',phone:fields.phone || '',company:fields.company || '',summary:summaryText()});
    stage = 'contacts'; render(); scroll.scrollTop = 0; flow.querySelector('input')?.focus();
  }
  function contactFields(value, includeSummary = false) {
    const field = (name,label,placeholder,extra='') => `<label class="et-field"><span>${label}</span><input aria-label="${label}" name="${name}" value="${escape(value[name])}" placeholder="${placeholder}" ${extra}></label>`;
    return `<div class="et-fields">${field('full_name','Имя и фамилия','Как к вам обращаться','autocomplete="name" maxlength="200"')}${field('phone','Телефон','+7 (___) ___-__-__','type="tel" inputmode="tel" autocomplete="tel" maxlength="40" required')}${field('company','Название компании','Ваша компания','autocomplete="organization" maxlength="200"')}${includeSummary ? `<label class="et-field"><span>Кратко о вашей задаче</span><textarea name="summary" maxlength="2000" required>${escape(value.summary)}</textarea></label>` : ''}</div>`;
  }
  function validForm(form) {
    const phone = form.elements.phone.value.trim(), count = phone.replace(/\D/g,'').length;
    form.elements.phone.setCustomValidity(!/^\+?[0-9 ()-]+$/.test(phone) || count < 10 || count > 15 ? 'Проверьте номер телефона' : '');
    const error = form.querySelector('.et-phone-error');
    if (error) error.remove();
    if (!form.elements.phone.validity.valid) {
      const note = document.createElement('span');note.className='et-phone-error';note.textContent='Проверьте номер телефона';form.elements.phone.parentElement.append(note);form.elements.phone.parentElement.classList.add('et-invalid');
    }
    return form.reportValidity();
  }
  function bindForm(form, save) {
    form.addEventListener('input',()=>{form.elements.phone.setCustomValidity('');form.elements.phone.parentElement.classList.remove('et-invalid');form.querySelector('.et-phone-error')?.remove();});
    form.onsubmit = e=>{e.preventDefault();if(busy||!validForm(form))return;save(Object.fromEntries(new FormData(form)));};
  }
  function renderContacts() {
    flow.innerHTML = previous() + assistant('Подготовлю заявку. Проверьте контакты — их можно будет изменить перед подтверждением.') + `<section class="et-card"><h2>Как с вами связаться?</h2><p class="et-hint">Достаточно телефона. Имя и компания — по желанию.</p><form class="et-contact-form">${contactFields(draft,!draft.summary)}<div class="et-stack"><button type="submit" class="et-primary">Проверить заявку</button>${button('Продолжить без телефона','decline')}</div></form></section>`;
    const form=$('.et-contact-form');
    form.addEventListener('input',()=>{draft={...draft,...Object.fromEntries(new FormData(form))};});
    bindForm(form,fields=>{draft={...draft,...fields};noPhone=false;stage='review';render();scroll.scrollTop=0;});
  }
  function reviewHTML(application) {
    return `<p class="et-eyebrow">КОНТАКТЫ</p>${[application.full_name,application.phone,application.company].filter(Boolean).map(v=>`<p>${escape(v)}</p>`).join('')}<p class="et-eyebrow">РЕЗЮМЕ</p><p>${escape(application.summary)}</p>`;
  }
  function renderReview(application,saved) {
    flow.innerHTML = previous() + assistant(saved ? 'Заявка сохранена. Вы можете продолжить консультацию или вернуться к ней в истории.' : 'Собрал контакты и резюме нашей беседы. Всё верно?') + card(saved ? 'Заявка сформирована' : 'Проверьте заявку',`<p class="${saved?'et-success':'et-muted'}">${saved?'Сохранено в диалоге':'Заявка сохранится в этом диалоге'}</p>${reviewHTML(application)}`,saved ? button('Продолжить консультацию','continue',true)+button('История диалогов','history') : button('Изменить данные','edit')+button('Сформировать заявку','save',true),'et-review');
  }
  function editContacts() {
    const saved = stage==='saved';
    const value = saved ? current.application : draft;
    openModal('Изменить контакты',`<p>Данные сохранятся только после нажатия «Сохранить».</p><form class="et-edit-form">${contactFields(value,false)}<details class="et-summary-edit"><summary>Изменить описание задачи</summary><label class="et-field"><span>Кратко о вашей задаче</span><textarea name="summary" maxlength="2000" required>${escape(value.summary)}</textarea></label></details><div class="et-stack"><button type="submit" class="et-primary">Сохранить</button>${button('Отмена','dismiss')}</div></form>`,'edit');
    bindForm(modalBody.querySelector('form'),fields=>{
      if(saved)run(async()=>{adopt(await api('/sessions/'+current.id+'/application',fields));dismiss();render();});
      else {draft={...draft,...fields};dismiss();render();}
    });
  }
  function openModal(title,html,kind='') {
    modalFocus = document.activeElement;
    $('#et-modal-title').textContent = title;
    modalBody.innerHTML = html;
    modal.className = 'et-modal ' + kind;
    if (!modal.open) modal.showModal();
    modal.scrollTop = 0; controls();
  }
  function dismiss() { modal.close(); if (modalFocus?.isConnected) modalFocus.focus(); }
  modal.addEventListener('click',e=> { if (e.target === modal) { const r=modal.getBoundingClientRect();if(e.clientX<r.left||e.clientX>r.right||e.clientY<r.top||e.clientY>r.bottom)dismiss(); } });
  function menu() {
    openModal('Действия чата',`<div class="et-stack">${button('Новый диалог','new')}${button('История диалогов','history')}${button(debug ? 'Выключить режим отладки' : 'Включить режим отладки','debug')}${button('Закрыть чат','close')}${current?.application ? button('Сохранённая заявка','application')+button('Изменить контакты','edit-saved')+button('Скачать заявку','download') : button('Подготовить заявку','contacts')}${button('Вернуться на сайт','site')}</div>`,'menu');
  }
  async function history() {
    const {sessions} = await api('/sessions');
    const entries = sessions.filter(s => knownIDs.has(s.id) && (s.messages.length || s.application)).sort((a,b)=>b.updated_at.localeCompare(a.updated_at));
    openModal('История диалогов',`<p class="et-hint">Сохранено на время демонстрации</p>${entries.length ? entries.map(s=>`<section class="et-card"><h2>${escape(s.messages.find(m=>m.role==='user')?.content.slice(0,100) || s.application?.summary.slice(0,100) || 'Консультация')}</h2><p class="et-hint">${escape(new Date(s.updated_at).toLocaleString('ru-RU',{timeZone:'Europe/Moscow',dateStyle:'medium',timeStyle:'short'}))}</p><p class="${s.application ? 'et-success':'et-muted'}">${s.application ? 'Заявка сформирована':'Без заявки'}</p><button data-session="${escape(s.id)}">${s.application?'Открыть диалог':'Посмотреть переписку'}</button></section>`).join('') : '<section class="et-empty-history"><h2>Здесь пока нет диалогов</h2><p>Сохранённые разговоры появятся в истории после консультации.</p></section>'}`,'drawer');
  }
  function transcriptHTML(session) {
    return session.messages.map(m=>`<article class="et-transcript-message"><p class="et-hint">${m.role==='user'?'Клиент':'EnergyTool'}</p><p>${escape(m.content)}</p></article>`).join('') || '<p>Переписка пока пуста.</p>';
  }
  async function archive(id) {
    archived=await api('/sessions/'+id);
    const title=archived.messages.find(m=>m.role==='user')?.content || archived.application?.summary || 'Консультация';
    openModal('Сохранённый диалог',`${button('Назад к истории','history')}<h2 class="et-archive-title">${escape(title)}</h2><div class="et-transcript">${transcriptHTML(archived)}</div>${archived.application ? card('Заявка сформирована','<p class="et-success">Сохранено в диалоге</p>'+reviewHTML(archived.application),'','et-review') : '<p class="et-muted">Без заявки · только просмотр</p>'}<div class="et-stack">${button('Начать новый диалог','new',true)}</div>`,'archive');
  }
  function sources(result = selectedSource || current?.last_result) {
    selectedSource=result;
    const seconds = ((result?.elapsed_ms||0)/1000).toLocaleString('ru-RU',{maximumFractionDigits:1});
    openModal('Источники и время',!result?.sources?.length ? `<h2>Для этого ответа источники не указаны</h2><p class="et-muted">Время ответа: ${seconds} с</p>` : `<p class="et-hint">Выбранный ответ</p><section class="et-card"><div class="et-source-time">${seconds} с</div><p class="et-hint">Время ответа</p></section><h2 class="et-source-count">${result.sources.length} источников базы знаний</h2><div class="et-stack">${result.sources.map((source,index)=>`<button data-fragment="${index}">${escape(source.document_id || source.source_id || 'Источник')}</button>`).join('')}</div><p class="et-hint et-source-note">Это источники конкретного ответа, а не всей беседы.</p>`,'drawer sources');
  }
  function fragment(index) {
    const source=selectedSource?.sources?.[index];if(!source)return;
    openModal(source.document_id || source.source_id || 'Фрагмент документа',`${button('Назад к источникам','sources')}<p class="et-muted et-source-note">Фрагмент базы знаний</p><section class="et-card"><p class="et-source-quote">${escape(source.quote||'')}</p></section><p class="et-hint et-source-note">Использован для выбранного ответа.</p>`,'drawer sources');
  }
  function confirm(kind) {
    const isNew = kind === 'new';
    if (isNew && stage === 'chat' && !draft && current && !current.messages.length && !current.application) { dismiss(); input.focus();return; }
    openModal(isNew ? 'Начать новый диалог?' : 'Закрыть чат?',`<p>${isNew ? 'Текущий разговор сохранится в истории. В новом диалоге консультант не будет учитывать его сообщения.' : 'Разговор сохранится в истории. При следующем открытии начнётся новый диалог.'}</p>${draft && stage !== 'saved' ? '<p class="et-muted">Неподтверждённые изменения формы не сохранятся.</p>' : ''}<div class="et-stack">${button(isNew ? 'Начать новый' : 'Закрыть чат',isNew ? 'confirm-new' : 'confirm-close',true)}${button('Вернуться в чат','dismiss')}</div>`);
  }
  async function newSession() {
    const fresh = await api('/sessions',null);
    adopt(fresh); draft=null;noPhone=false;collapsedAt=0;stage='chat';input.value='';status('');render();scroll.scrollTop=0;
  }
  async function refresh() {
    if (current) adopt(await api('/sessions/'+current.id));
    else if (savedID) {
      try { adopt(await api('/sessions/'+savedID)); }
      catch(e) { if (e.code !== 'not_found') throw e;remember(null); }
    }
    if (!current || isClosed()) {
      if (!current) await newSession();
      else render();
    } else render();
    if (!needsSync) status('');
  }
  async function send(text, retry = false) {
    if (!text.trim() || !current || isClosed() || needsSync || busy) return;
    await run(async()=> {
      stage='chat';status('');pending=true;render();
      if (!retry) messages.insertAdjacentHTML('beforeend',messageHTML({role:'user',content:text}));
      $('.et-welcome').hidden=true;scroll.scrollTop=scroll.scrollHeight;
      try {
        await api('/sessions/'+current.id+'/messages',{content:text});
        input.value='';input.style.height='';
        adopt(await api('/sessions/'+current.id));pending=false;render();
        scroll.scrollTop=Math.max(0,scroll.scrollHeight-scroll.clientHeight);
      } catch(e) {
        pending=false;needsSync=true;flow.replaceChildren();
        status((e.name === 'TimeoutError' ? 'Время ожидания истекло.' : e.message)+' Обновите историю перед повторной отправкой.',true);
      }
    });
  }
  function download() {
    const a=current?.application;if(!a)return;
    const text=['Заявка EnergyTool','Сохранено: '+new Date(a.saved_at).toLocaleString('ru-RU',{timeZone:'Europe/Moscow'}),'Имя: '+(a.full_name||'Не указано'),'Телефон: '+a.phone,'Компания: '+(a.company||'Не указана'),'','Задача:',a.summary,'','Сохранено локально. Передача менеджеру не подключена.'].join('\n');
    const url=URL.createObjectURL(new Blob([text],{type:'text/plain;charset=utf-8'}));const link=document.createElement('a');link.href=url;link.download='energytool-application.txt';link.click();setTimeout(()=>URL.revokeObjectURL(url),1000);
  }
  host.addEventListener('click',e=> {
    const el=e.target.closest('button');if(!el||el.disabled)return;
    if (el.dataset.session) return run(()=>archive(el.dataset.session));
    if (el.dataset.sourceMessage !== undefined) return sources(metadata(current.messages[Number(el.dataset.sourceMessage)],Number(el.dataset.sourceMessage)));
    if (el.dataset.fragment !== undefined) return fragment(Number(el.dataset.fragment));
    if (el.dataset.reply) { if(stage==='declined') collapsedAt=current.messages.length; return send(el.dataset.reply); }
    if (el.dataset.prompt) {
      input.value={cost:'У нас выросли счета за электроэнергию. С чего начать?',meter:'Хочу наладить учёт электроэнергии. С чего начать?',loss:'Хочу понять, где возникают потери электроэнергии. С чего начать?'}[el.dataset.prompt];input.focus();input.dispatchEvent(new Event('input'));return;
    }
    switch(el.dataset.action) {
      case 'dismiss':dismiss();break;
      case 'menu':menu();break;
      case 'history':run(history);break;
      case 'sources':sources();break;
      case 'debug':debug=!debug;dismiss();render();break;
      case 'new':confirm('new');break;
      case 'close':confirm('close');break;
      case 'site':location.href=returnPath;break;
      case 'confirm-new':run(async()=>{if(current&&!isClosed())await api('/sessions/'+current.id+'/close',null);await newSession();dismiss();});break;
      case 'confirm-close':run(async()=>{if(current&&!isClosed())await api('/sessions/'+current.id+'/close',null);remember(null);location.href=returnPath;});break;
      case 'refresh':run(refresh);break;
      case 'contacts':if(modal.open)dismiss();startContacts();break;
      case 'edit':editContacts();break;
      case 'edit-saved':stage='saved';render();editContacts();break;
      case 'decline':noPhone=true;stage='declined';render();scroll.scrollTop=0;break;
      case 'application':if(modal.open)dismiss();if(current?.application){stage='saved';render();scroll.scrollTop=0;}break;
      case 'continue':stage='chat';render();scroll.scrollTop=scroll.scrollHeight;input.focus();break;
      case 'transcript':openModal('Предыдущая переписка',`<div class="et-transcript">${transcriptHTML(current)}</div>`,'archive');break;
      case 'save':run(async()=>{const payload={full_name:draft.full_name,phone:draft.phone,company:draft.company,summary:draft.summary};adopt(await api('/sessions/'+current.id+'/application',payload));stage='saved';draft=null;status('');render();scroll.scrollTop=0;});break;
      case 'download':download();break;
      case 'retry':send(current.messages.findLast(m=>m.role==='user')?.content || input.value,true);break;
    }
  });
  $('.et-composer').onsubmit=e=> {e.preventDefault();send(input.value.trim());};
  input.addEventListener('input',()=>{input.style.height='24px';input.style.height=Math.min(input.scrollHeight,120)+'px';controls();});
  input.addEventListener('keydown',e=>{if(e.key==='Enter'&&!e.shiftKey&&!e.isComposing){e.preventDefault();if(!$('.et-send').disabled)$('.et-composer').requestSubmit();}});
  controls();
  run(async()=>{
    const params=new URLSearchParams(location.search);
    if(params.get('start')==='new') { await newSession();params.delete('start');window.history.replaceState(null,'',location.pathname+(params.size?'?'+params.toString():'')); }
    else { await refresh();if(isClosed())await newSession(); }
  });
})();
