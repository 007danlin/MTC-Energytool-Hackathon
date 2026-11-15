// Real browser UI with controllable API fixtures; no model or production data is used.
const assert = require('node:assert/strict');
const { chromium } = require(process.env.PLAYWRIGHT_MODULE || 'playwright');
const base = process.env.WEB_TEST_URL || 'http://127.0.0.1:8776';
const errors = [];
async function eventually(check, message) {
  const until = Date.now() + 5000;
  while (!check() && Date.now() < until) await new Promise(resolve=>setTimeout(resolve,25));
  assert.ok(check(),message);
}

async function fixture(browser, name) {
  const context = await browser.newContext({viewport:{width:1280,height:900}});
  const page = await context.newPage();
  page.on('pageerror', error => errors.push(name + ': ' + error.message));
  await page.clock.install();
  const session = {id:'wait-'+name,status:'active',messages:[],lead:{fields:{}},updated_at:new Date().toISOString()};
  const posts = [], waiting = [];
  let reads = 0, saves = 0, readGate = null, failBeforeWrite = false;
  await page.route('**/api/v1/**', async route => {
    const request = route.request();
    const path = new URL(request.url()).pathname;
    if (path === '/api/v1/sessions') {
      await route.fulfill({json:request.method()==='GET'?{sessions:[session]}:session});
      return;
    }
    if (path.endsWith('/messages')) {
      const body = request.postDataJSON();
      posts.push(body);
      if (!failBeforeWrite) session.messages.push({id:'user-'+posts.length,role:'user',content:body.content,sequence:session.messages.length+1});
      failBeforeWrite = false;
      await new Promise(resolve => waiting.push({route,resolve,body}));
      return;
    }
    if (path.endsWith('/application')) {
      saves++;
      session.application = {id:'app-'+name,number:'123456',...request.postDataJSON(),saved_at:new Date().toISOString()};
      await route.fulfill({json:session});
      return;
    }
    if (path.includes('/requests/')) {
      const id = path.split('/').at(-1);
      const result = session.messages.find(message=>message.response?.request_id===id)?.response;
      await route.fulfill({status:result?200:409,json:result||{code:'request_pending',message:'Response pending'}});
      return;
    }
    reads++;
    if (readGate && !readGate.snapshot) {
      readGate.snapshot = structuredClone(session);
      readGate.route = route;
      await new Promise(resolve=>{readGate.resolve=resolve;});
      return;
    }
    await route.fulfill({json:session});
  });
  await page.goto(base+'/consultation.html?start=new');
  await page.waitForFunction(()=>document.querySelector('#et-question') && !document.querySelector('#et-question').disabled);
  return {
    page,session,posts,context,
    get reads(){return reads;}, get saves(){return saves;},
    failNextBeforeWrite() { failBeforeWrite = true; },
    async fail() {
      const pending = waiting.shift();
      assert.ok(pending,'there must be an outstanding request');
      await pending.route.abort('failed'); pending.resolve();
    },
    holdNextRead() {
      const gate = readGate = {};
      return {
        get captured(){return Boolean(gate.snapshot);},
        async release() {
          assert.ok(gate.snapshot,'the held read must have started');
          readGate = null;
          await gate.route.fulfill({json:gate.snapshot}); gate.resolve();
        }
      };
    },
    async send(text) {
      await page.locator('#et-question').fill(text);
      await page.locator('.et-send').click();
      await page.locator('.et-pending').waitFor();
    },
    async complete(status='answered', answer='Сохранённый ответ после долгого ожидания.') {
      const pending = waiting.shift();
      assert.ok(pending,'there must be an outstanding request');
      const result = {status,answer,request_id:pending.body.client_request_id,summary:{},sources:[],lead:{session_id:session.id,fields:{}}};
      session.last_result = result;
      session.messages.push({id:'assistant-'+posts.length,role:'assistant',content:answer,response:result,sequence:session.messages.length+1});
      try { await pending.route.fulfill({json:result}); } catch (_) { /* The browser may have stopped waiting. */ }
      pending.resolve();
    },
    async tick() { await page.clock.fastForward(4000); },
    async close() {
      if (readGate?.route) { try { await readGate.route.abort(); } catch (_) {} readGate.resolve(); }
      for (const pending of waiting.splice(0)) { try { await pending.route.abort(); } catch (_) {} pending.resolve(); }
      await context.close();
    }
  };
}

(async () => {
  const browser = await chromium.launch({headless:true});
  try {
    // Aborting a wait retains the next draft and only performs reads while recovering.
    let f = await fixture(browser,'abort');
    try {
      await f.send('Нужен раздельный учёт двух арендаторов.');
      assert.ok(f.posts[0].client_request_id,'every message has an idempotency key');
      await f.page.locator('#et-question').fill('Следующее уточнение, которое нельзя потерять');
      await f.page.clock.fastForward(21000);
      await f.page.getByRole('button',{name:'Прервать ожидание',exact:true}).click();
      await f.page.waitForFunction(()=>document.querySelector('#energytool-chat').dataset.screen==='sync');
      assert.equal(await f.page.getByRole('button',{name:'Позвать оператора',exact:true}).isVisible(),true);
      assert.equal(await f.page.getByRole('button',{name:'Продолжить ожидание',exact:true}).isVisible(),true);
      assert.equal(await f.page.locator('.et-send').isDisabled(),true);
      assert.equal(await f.page.locator('#et-question').inputValue(),'Следующее уточнение, которое нельзя потерять');
      await f.page.evaluate(()=>document.fonts.ready);
      await f.page.screenshot({path:'/private/tmp/energytool-recovery-desktop.png'});
      await f.page.setViewportSize({width:390,height:844});
      await f.page.locator('.et-recovery').scrollIntoViewIfNeeded();
      await f.page.screenshot({path:'/private/tmp/energytool-recovery-mobile.png'});
      await f.page.setViewportSize({width:1280,height:900});
      const readsBefore = f.reads;
      await f.tick();
      await f.page.waitForFunction(()=>document.querySelector('#energytool-chat').dataset.screen==='sync');
      await eventually(()=>f.reads > readsBefore,'recovery polls history without a manual click');
      assert.equal(f.posts.length,1,'polling cannot resend a message');
      await f.page.getByRole('button',{name:'Позвать оператора',exact:true}).focus();
      await f.tick();
      await eventually(()=>f.reads > readsBefore+1,'another unchanged poll completes');
      assert.equal(await f.page.evaluate(()=>document.activeElement?.dataset.action),'operator','unchanged polling must preserve keyboard focus');
      assert.equal(await f.page.locator('.et-status').isVisible(),false,'normal interrupted waiting is not a red error');
      await f.page.getByRole('button',{name:'Продолжить ожидание',exact:true}).click();
      await f.page.getByRole('heading',{name:'Проверяю готовность ответа',exact:true}).waitFor();
      assert.equal(f.posts.length,1,'resuming waiting only checks the existing request');
      await f.complete();
      await f.tick();
      await f.page.waitForFunction(()=>!document.querySelector('#et-question').disabled && document.querySelector('#energytool-chat').dataset.screen!=='sync');
      assert.match(await f.page.locator('.et-messages').innerText(),/Сохранённый ответ/);
      assert.equal(await f.page.locator('#et-question').inputValue(),'Следующее уточнение, которое нельзя потерять');
      assert.equal(f.posts.length,1);
      await f.send('Продолжаем после прерывания.');
      assert.notEqual(f.posts[1].client_request_id,f.posts[0].client_request_id);
      await f.complete();
    } finally { await f.close(); }

    // Reloading during server processing recovers automatically and keeps the draft.
    f = await fixture(browser,'reload');
    try {
      await f.send('Проверка возврата к незавершённой консультации.');
      await f.page.locator('#et-question').fill('Черновик переживает перезагрузку');
      await f.page.reload();
      await f.page.waitForFunction(()=>document.querySelector('#energytool-chat').dataset.screen==='sync');
      assert.equal(await f.page.locator('#et-question').inputValue(),'Черновик переживает перезагрузку');
      await f.complete();
      await f.tick();
      await f.page.waitForFunction(()=>!document.querySelector('#et-question').disabled && document.querySelector('#energytool-chat').dataset.screen!=='sync');
      assert.equal(await f.page.locator('.et-user').count(),1,'reload cannot duplicate the question');
      assert.equal(f.posts.length,1);
      assert.equal(await f.page.locator('#et-question').inputValue(),'Черновик переживает перезагрузку');
    } finally { await f.close(); }

    // Operator request is available during a slow first answer and can be saved immediately.
    f = await fixture(browser,'operator');
    try {
      const original = 'Нужна автоматизация учёта на производстве, оператор поможет уточнить детали.';
      await f.send(original);
      await f.page.locator('#et-question').fill('Дополнение для продолжения консультации');
      await f.page.clock.fastForward(21000);
      await f.page.getByRole('button',{name:'Позвать оператора',exact:true}).click();
      await f.page.getByRole('heading',{name:'Как с вами связаться?',exact:true}).waitFor();
      await f.page.getByLabel('Телефон или email',{exact:true}).fill('operator-test@example.test');
      await f.page.getByRole('button',{name:'Проверить заявку',exact:true}).click();
      await f.page.getByRole('heading',{name:'Проверьте заявку',exact:true}).waitFor();
      assert.match(await f.page.locator('.et-review').innerText(),/Нужна автоматизация учёта на производстве/,'the pending first question is attached');
      await f.page.getByRole('button',{name:'Сформировать заявку',exact:true}).click();
      await f.page.getByRole('heading',{name:'Заявка сформирована',exact:true}).waitFor();
      assert.equal(f.saves,1);
      assert.equal(f.posts.length,1,'saving an operator request does not resend the chat question');
      await f.page.getByRole('button',{name:'Продолжить консультацию',exact:true}).click();
      await f.page.waitForFunction(()=>document.querySelector('#energytool-chat').dataset.screen==='sync');
      await f.complete();
      await f.tick();
      await f.page.waitForFunction(()=>!document.querySelector('#et-question').disabled && document.querySelector('#energytool-chat').dataset.screen!=='sync');
      assert.equal(await f.page.locator('#et-question').inputValue(),'Дополнение для продолжения консультации');
      assert.equal(await f.page.locator('.et-application-receipt').isVisible(),true);
      assert.equal(f.posts.length,1);
    } finally { await f.close(); }

    // A GET started before saving must not overwrite the newer saved application.
    f = await fixture(browser,'stale-read');
    try {
      await f.send('Заявка оператору во время ожидания не должна пропадать.');
      await f.page.clock.fastForward(21000);
      await f.page.getByRole('button',{name:'Позвать оператора',exact:true}).click();
      await f.page.getByLabel('Телефон или email',{exact:true}).fill('stale-test@example.test');
      await f.page.getByRole('button',{name:'Проверить заявку',exact:true}).click();
      const held = f.holdNextRead();
      await f.tick();
      await eventually(()=>held.captured,'the pending poll captured the pre-save snapshot');
      await f.page.getByRole('button',{name:'Сформировать заявку',exact:true}).click();
      await f.page.getByRole('heading',{name:'Заявка сформирована',exact:true}).waitFor();
      const staleDelivered = f.page.waitForResponse(response=>response.request().method()==='GET' && response.url().endsWith('/'+f.session.id));
      await held.release();
      await staleDelivered;
      await f.page.clock.runFor(100);
      assert.equal(await f.page.getByRole('heading',{name:'Заявка сформирована',exact:true}).isVisible(),true,'the stale read cannot erase the saved review');
      assert.equal(await f.page.locator('.et-application-receipt').isVisible(),true,'the application receipt survives the stale read');
      const downloaded = f.page.waitForEvent('download');
      await f.page.getByRole('button',{name:'Скачать заявку',exact:true}).click();
      const download = await downloaded;
      assert.match(download.suggestedFilename(),/123456/);
      await download.delete();
      await f.page.getByRole('button',{name:'Продолжить консультацию',exact:true}).click();
      await f.page.waitForFunction(()=>document.querySelector('#energytool-chat').dataset.screen==='sync');
      await f.complete();
      await f.tick();
      await f.page.waitForFunction(()=>document.querySelector('#energytool-chat').dataset.screen!=='sync');
      assert.equal(await f.page.locator('.et-application-receipt').isVisible(),true);
      assert.equal(f.posts.length,1);
    } finally { await f.close(); }

    // A confirmed missing send keeps its identity through reconciliation and reload.
    f = await fixture(browser,'missing-send');
    try {
      const text = 'Вопрос, который ещё не дошёл до сервера.';
      f.failNextBeforeWrite();
      await f.send(text);
      const originalID = f.posts[0].client_request_id;
      await f.fail();
      await f.page.getByRole('button',{name:'Обновить историю',exact:true}).click();
      await f.page.waitForFunction(()=>!document.querySelector('.et-send').disabled);
      assert.equal(f.session.messages.length,0);
      await f.page.reload();
      await f.page.waitForFunction(()=>!document.querySelector('.et-send').disabled);
      assert.equal(await f.page.locator('#et-question').inputValue(),text);
      await f.send(text);
      assert.equal(f.posts[1].client_request_id,originalID,'reload must retain the identity of an unconfirmed original send');
      await f.complete();
      await f.page.waitForFunction(()=>document.querySelector('#energytool-chat').dataset.screen!=='waiting');
      assert.equal(await f.page.locator('.et-user').count(),1);
    } finally { await f.close(); }

    // Old browser state predating request identities receives a new valid ID.
    f = await fixture(browser,'legacy-marker');
    try {
      const text = 'Черновик из прежней версии интерфейса.';
      await f.page.evaluate(({id,text})=>{
        sessionStorage.setItem('energytool-composer-'+id,text);
        sessionStorage.setItem('energytool-pending-'+id,JSON.stringify({sessionID:id,text,offset:0,fromComposer:true,retry:false,restored:true}));
      },{id:f.session.id,text});
      await f.page.reload();
      await f.page.waitForFunction(()=>!document.querySelector('.et-send').disabled);
      await f.send(text);
      assert.match(f.posts[0].client_request_id,/^[a-f0-9]{8}-[a-f0-9]{4}-4[a-f0-9]{3}-[89ab][a-f0-9]{3}-[a-f0-9]{12}$/i);
      await f.complete();
    } finally { await f.close(); }

    // A background answer must not replace a partly completed operator form on mobile.
    f = await fixture(browser,'mobile-form');
    try {
      await f.page.setViewportSize({width:390,height:844});
      await f.send('Нужен специалист по учёту электроэнергии для офиса.');
      await f.page.clock.fastForward(21000);
      await f.page.getByRole('button',{name:'Позвать оператора',exact:true}).click();
      await f.page.getByRole('heading',{name:'Как с вами связаться?',exact:true}).waitFor();
      await f.page.getByLabel('Телефон или email',{exact:true}).fill('unfinished@example.test');
      await f.complete();
      await f.tick();
      await f.page.getByText('Ответ получен. Можно вернуться к консультации.',{exact:true}).waitFor();
      assert.equal(await f.page.getByLabel('Телефон или email',{exact:true}).inputValue(),'unfinished@example.test','polling cannot replace form fields');
      assert.equal(await f.page.evaluate(()=>document.documentElement.scrollWidth>innerWidth),false,'mobile recovery flow has no horizontal overflow');
      await f.page.getByRole('button',{name:'Проверить заявку',exact:true}).click();
      await f.page.getByRole('button',{name:'Вернуться к консультации',exact:true}).click();
      await f.page.waitForFunction(()=>!document.querySelector('#et-question').disabled && document.querySelector('#energytool-chat').dataset.screen!=='sync');
      assert.match(await f.page.locator('.et-messages').innerText(),/Сохранённый ответ/);
      assert.equal(f.posts.length,1);
    } finally { await f.close(); }

    // A technical failure offers human help and a retry with a new request identity.
    f = await fixture(browser,'error');
    try {
      await f.send('Технический сбой не должен завершать консультацию.');
      await f.complete('technical_error','Сервис временно недоступен.');
      await f.page.getByRole('heading',{name:'Не удалось получить ответ',exact:true}).waitFor();
      assert.equal(await f.page.getByRole('button',{name:'Позвать оператора',exact:true}).isVisible(),true);
      await f.page.getByRole('button',{name:'Повторить',exact:true}).click();
      await f.page.locator('.et-pending').waitFor();
      assert.equal(f.posts.length,2);
      assert.notEqual(f.posts[1].client_request_id,f.posts[0].client_request_id,'a user-requested retry is a new attempt');
      await f.complete();
      await f.page.waitForFunction(()=>!document.querySelector('#et-question').disabled && document.querySelector('#energytool-chat').dataset.screen!=='waiting');
      assert.equal(await f.page.locator('.et-user').count(),1,'technical retries do not repeat the displayed question');
    } finally { await f.close(); }
    assert.deepEqual(errors,[]);
    console.log('PASS: abort and reload auto-recovery, draft retention, no duplicate POST, request identities, operator application during first pending response, return after save, mobile form retained during polling, stale reads after save, retry identity after reload, legacy markers, technical retry.');
  } finally { await browser.close(); }
})().catch(error=>{console.error(error);process.exit(1);});
