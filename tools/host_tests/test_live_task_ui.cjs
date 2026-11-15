// End-to-end frontend regression for the real UI; API results below are explicit test fixtures.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const {chromium} = require(process.env.PLAYWRIGHT_MODULE || 'playwright');
const base = process.env.WEB_TEST_URL || 'http://127.0.0.1:8775';
const shots = process.env.WEB_TEST_SHOTS;

(async () => {
  const browser = await chromium.launch({headless:true});
  try {
    const page = await browser.newPage({viewport:{width:1440,height:960}});
    const errors=[];
    page.on('pageerror', e=>errors.push(e.message));
    let counter=0, posts=0, gate=null;
    const sessions={}, responses=[];
    const unsafe = 'Режим <img src=x onerror="window.injected=true">';
    const summary = {
      task:[{value:'Нужен раздельный учёт офиса',message_index:0}],
      object:[{value:'Офис, корпус Б',message_index:0}],
      parameters:[{value:'Два арендатора',message_index:0},{value:unsafe,message_index:0}],
      constraints:[{value:'Без остановки работы',message_index:0}],
      manager_questions:['Есть ли отдельные счётчики?'],
      products:[{name:'Решение из тестовой базы',source_id:'fixture.md#1'}],
    };
    await page.route('**/api/v1/**', async route=>{
      const req=route.request(), parts=new URL(req.url()).pathname.split('/').filter(Boolean);
      let value;
      if(parts.length===3 && req.method()==='POST') {
        const id='live-task-'+(++counter);
        value=sessions[id]={id,status:'active',messages:[],lead:{fields:{}},updated_at:new Date().toISOString()};
      } else if(parts.length===3) value={sessions:Object.values(sessions)};
      else {
        const session=sessions[parts[3]];
        assert.ok(session,'unexpected session '+parts[3]);
        if(parts[4]==='messages') {
          posts++;
          const {content}=req.postDataJSON();
          session.messages.push({role:'user',content});
          if(gate) await new Promise(resolve=>{gate.release=resolve});
          const next=responses.shift()||{};
          const response={status:'answered',answer:'Сначала уточните точки учёта для каждого арендатора.',summary:structuredClone(summary),sources:[{document_id:'Документ тестовой базы',quote:'Тестовая цитата для проверки карточки.'}],elapsed_ms:1250,lead:{session_id:session.id,fields:{}},...next};
          session.last_result=response;
          session.messages.push({role:'assistant',content:response.answer,response});
          value=response;
        } else if(parts[4]==='application') {
          session.application={id:'ET-live-task',...req.postDataJSON(),saved_at:new Date().toISOString()};value=session;
        } else if(parts[4]==='close') {session.status='closed';value=session;}
        else value=session;
      }
      await route.fulfill({json:value});
    });
    const ready=()=>page.waitForFunction(()=>{
      const h=document.querySelector('#energytool-chat'),q=document.querySelector('#et-question');
      return h && h.dataset.screen!=='waiting' && h.dataset.screen!=='sync' && q && !q.disabled;
    });
    const field=key=>page.locator(`.et-sidebar .et-task-row[data-task-key="${key}"]`);
    const send=async text=>{
      await page.locator('#et-question').fill(text);
      await page.locator('.et-send').click();
      await ready();
    };
    const close=()=>page.locator('dialog').getByRole('button',{name:'Закрыть',exact:true}).click();
    const snap=async name=>{if(shots){fs.mkdirSync(shots,{recursive:true});await page.evaluate(()=>document.fonts.ready);await page.screenshot({path:shots+'/'+name+'.png'});}};
    await page.goto(base+'/consultation.html?start=new');await ready();
    assert.equal(await page.locator('.et-welcome').isVisible(),true);
    await snap('live-task-welcome');

    // There is a pending real request, and the next draft must not be sent or discarded.
    gate={};
    await page.locator('#et-question').fill('Нужен раздельный учёт офиса, корпус Б. Два арендатора.');
    await page.locator('.et-send').click();
    await page.locator('.et-pending').waitFor();
    assert.equal(await page.locator('#et-question').isEnabled(),true,'typing a future draft is allowed');
    assert.equal(await page.locator('.et-send').isDisabled(),true,'parallel request must not start');
    await page.locator('#et-question').fill('Площадь офиса 500 м².');
    await page.locator('#et-question').press('Enter');
    assert.equal(posts,1);
    await page.locator('.et-sidebar [data-action="task-add"]').click();
    await page.locator('.et-task-form textarea[name="detail"]').fill('Ночной режим работы');
    await page.getByRole('button',{name:'Добавить в черновик',exact:true}).click();
    assert.match(await page.locator('#et-question').inputValue(),/Площадь офиса 500 м²/);
    assert.match(await page.locator('#et-question').inputValue(),/Ночной режим работы/);
    assert.equal(posts,1,'task editing only prepares next message');
    assert.doesNotMatch(await page.locator('.et-sidebar .et-task-rows').innerText(),/Ночной режим работы/,'unsent draft must not become a confirmed fact');
    const draft=await page.locator('#et-question').inputValue();
    await snap('live-task-waiting');
    gate.release();gate=null;await ready();
    assert.equal(await page.locator('#et-question').inputValue(),draft,'response preserves newer draft');
    assert.match(await field('object').innerText(),/Офис, корпус Б/);
    assert.match(await field('parameters').innerText(),/Два арендатора/);
    assert.match(await field('constraints').innerText(),/Без остановки работы/);
    assert.match(await field('questions').innerText(),/Есть ли отдельные счётчики/);
    assert.match(await field('products').innerText(),/Решение из тестовой базы/);
    assert.match(await field('parameters').innerText(),/<img/);
    assert.equal(await page.locator('.et-task-rows img').count(),0);
    assert.equal(await page.evaluate(()=>window.injected),undefined);
    await page.reload();await ready();
    assert.equal(await page.locator('#et-question').inputValue(),draft,'draft survives reload');
    await snap('live-task-answer');

    // A long request is honestly cancellable without claiming that the server stopped.
    await page.clock.install();
    await page.emulateMedia({reducedMotion:'reduce'});
    gate={};
    await page.locator('#et-question').fill('Проверка длительного ожидания');
    await page.locator('.et-send').click();
    await page.locator('.et-pending').waitFor();
    await page.locator('#et-question').fill('Черновик после прерывания');
    await page.clock.fastForward(21000);
    assert.equal(await page.locator('.et-wait-long').isVisible(),true);
    assert.equal(await page.locator('.et-wait-help').isVisible(),true);
    assert.equal(await page.locator('.et-energy-bars i').first().evaluate(e=>getComputedStyle(e).animationName),'none');
    assert.match(await field('object').innerText(),/Офис, корпус Б/,'confirmed summary survives pending');
    const requestsBeforeStop=posts;
    await page.getByRole('button',{name:'Прервать ожидание',exact:true}).click();
    await page.getByRole('button',{name:'Обновить историю',exact:true}).waitFor();
    assert.equal(await page.locator('.et-send').isDisabled(),true);
    assert.equal(posts,requestsBeforeStop,'abort cannot silently retry a request');
    assert.equal(await page.locator('#et-question').inputValue(),'Черновик после прерывания');
    gate.release();gate=null;
    await page.getByRole('button',{name:'Обновить историю',exact:true}).click();await ready();
    assert.equal(await page.locator('#et-question').inputValue(),'Черновик после прерывания');
    assert.equal(posts,requestsBeforeStop,'refresh only reads the settled session');
    await page.emulateMedia({reducedMotion:'no-preference'});

    // Long server data must stay reachable in the sidebar and in the mobile sheet.
    const long=structuredClone(summary);
    long.parameters=Array.from({length:22},(_,i)=>({value:'Подтверждённый параметр '+(i+1)+' — '+('важные детали '.repeat(6)),message_index:2}));
    long.manager_questions=['Последний вопрос для специалиста'];
    responses.push({summary:long});
    await send('Дополню сведения по офису.');
    for(const width of [1280,1440,1920]) {
      await page.setViewportSize({width,height:960});
      assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth),false,'page overflow '+width);
      await field('questions').scrollIntoViewIfNeeded();
      const box=await field('questions').boundingBox();
      assert.ok(box.y>=0 && box.y<960,'last task section reachable '+width);
      assert.equal(await page.locator('.et-sidebar').evaluate(e=>e.scrollWidth>e.clientWidth+1),false,'sidebar horizontal overflow');
    }
    for(const width of [360,390]) {
      await page.setViewportSize({width,height:844});
      const task=page.locator('.et-task-mobile');
      await task.click();
      assert.equal(await page.locator('dialog').isVisible(),true);
      const last=page.locator('dialog .et-task-row[data-task-key="questions"]');
      await last.scrollIntoViewIfNeeded();
      assert.match(await last.innerText(),/Последний вопрос/);
      assert.equal(await page.locator('dialog').evaluate(e=>e.scrollWidth>e.clientWidth+1),false,'mobile task sheet overflow');
      await snap('live-task-mobile-'+width);
      await close();
      assert.equal(await page.evaluate(()=>document.activeElement.classList.contains('et-task-mobile')),true,'close restores task-button focus');
    }
    await page.setViewportSize({width:390,height:480});
    await page.locator('#et-question').focus();
    await page.locator('#et-question').scrollIntoViewIfNeeded();
    const inputBox=await page.locator('#et-question').boundingBox();
    assert.ok(inputBox.y>=0 && inputBox.y+inputBox.height<=480,'mobile input visible with shortened viewport');

    // Existing source, lead, contact, review, saved and history UI still works.
    await page.setViewportSize({width:1440,height:960});
    await page.getByRole('button',{name:'Меню',exact:true}).click();
    await page.getByRole('button',{name:'Включить режим отладки',exact:true}).click();
    await page.locator('[data-source-message]').last().click();
    await page.locator('[data-fragment]').first().click();
    assert.match(await page.locator('dialog').innerText(),/Тестовая цитата/);await close();
    await page.getByRole('button',{name:'Подготовить заявку',exact:true}).click();
    await page.getByLabel('Телефон или email',{exact:true}).fill('test@example.com');
    await page.getByRole('button',{name:'Проверить заявку',exact:true}).click();
    await page.getByRole('button',{name:'Изменить данные',exact:true}).click();
    await page.locator('.et-summary-edit summary').click();
    await page.getByLabel('Кратко о вашей задаче').fill('Заявка для проверки нового интерфейса.');
    await page.getByRole('button',{name:'Сохранить',exact:true}).click();
    assert.equal(await page.locator('.et-review').isVisible(),true);
    await snap('live-task-review');
    await page.getByRole('button',{name:'Сформировать заявку',exact:true}).click();
    await page.getByRole('heading',{name:'Заявка сформирована',exact:true}).waitFor();
    assert.match(await page.locator('.et-review').innerText(),/test@example.com/);
    await page.locator('.et-flow').getByRole('button',{name:'История диалогов',exact:true}).click();
    await page.locator('[data-session]').first().click();
    await page.getByRole('heading',{name:'Сохранённый диалог',exact:true}).waitFor();
    assert.match(await page.locator('dialog').innerText(),/Заявка для проверки нового интерфейса/);
    await close();
    assert.equal(posts,3,'non-chat interactions never submit extra user messages');
    // Persisted request markers must reconcile safely after a full page reload.
    for (const scenario of [
      {name:'recorded-original',recorded:true,draft:''},
      {name:'recorded-newer-draft',recorded:true,draft:'Новый вопрос, написанный во время ожидания'},
      {name:'not-recorded',recorded:false,draft:''},
      {name:'not-recorded-newer-draft',recorded:false,draft:'Следующий черновик тоже должен сохраниться'},
    ]) {
      const recovery=await browser.newPage();
      recovery.on('pageerror',e=>errors.push(e.message));
      const session={id:'recovery-'+scenario.name,status:'active',messages:[],lead:{fields:{}},updated_at:new Date().toISOString()};
      const original='Исходный вопрос для '+scenario.name;
      let release,requests=0;
      await recovery.addInitScript(id=>localStorage.setItem('energytool-session',id),session.id);
      await recovery.route('**/api/v1/**',async route=>{
        if(route.request().url().endsWith('/messages')) {
          requests++;
          const content=route.request().postDataJSON().content;
          await new Promise(resolve=>{release=resolve});
          if(scenario.recorded) {
            session.last_result={status:'answered',answer:'Ответ уже сохранён сервером',summary:{},sources:[]};
            session.messages.push({role:'user',content},{role:'assistant',content:session.last_result.answer,response:session.last_result});
          }
          await route.abort('failed');
        } else await route.fulfill({json:session});
      });
      const recovered=()=>recovery.waitForFunction(()=>document.querySelector('#energytool-chat').dataset.screen!=='waiting'&&document.querySelector('#energytool-chat').dataset.screen!=='sync'&&!document.querySelector('#et-question').disabled);
      await recovery.goto(base+'/consultation.html');await recovered();
      await recovery.locator('#et-question').fill(original);
      await recovery.locator('.et-send').click();
      await recovery.locator('.et-pending').waitFor();
      if(scenario.draft)await recovery.locator('#et-question').fill(scenario.draft);
      release();
      await recovery.getByRole('button',{name:'Обновить историю',exact:true}).waitFor();
      assert.equal(await recovery.locator('#et-question').inputValue(),scenario.draft||original);
      const marker=await recovery.evaluate(id=>JSON.parse(sessionStorage.getItem('energytool-pending-'+id)),session.id);
      assert.equal(marker.text,original,'unconfirmed request survives reload');
      assert.equal(marker.restored,!scenario.draft,'only automatically restored original gets cleared');
      await recovery.reload();await recovered();
      const expected=scenario.recorded?scenario.draft:[original,scenario.draft].filter(Boolean).join('\n\n');
      assert.equal(await recovery.locator('#et-question').inputValue(),expected,scenario.name);
      assert.equal(requests,1,'reload must not automatically repeat POST: '+scenario.name);
      assert.equal(await recovery.evaluate(id=>sessionStorage.getItem('energytool-pending-'+id),session.id),null,'settled marker removed');
      assert.equal(await recovery.locator('.et-user').count(),scenario.recorded?1:0);
      await recovery.close();
    }
    assert.deepEqual(errors,[]);
    console.log('PASS: live task summary, untrusted text, pending draft preservation, next-message edits, reload/reconciliation of failed sends, long wait/abort/reduced motion, long sidebar/mobile sheet, sources, contact/review/save/history.');
  } finally { await browser.close(); }
})().catch(error=>{console.error(error);process.exit(1);});
