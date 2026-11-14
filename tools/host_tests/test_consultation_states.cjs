// Deterministic browser-only checks for failure recovery and untrusted model text.
const assert=require('node:assert/strict');
const {chromium}=require(process.env.PLAYWRIGHT_MODULE||'playwright');
const base=process.env.WEB_TEST_URL||'http://127.0.0.1:8768';
(async()=>{const b=await chromium.launch({headless:true});try{
 const p=await b.newPage();let calls=0,fail=true,failBeforeWrite=false,failHistory=false;
 const session={id:'browser-fixture',status:'active',messages:[],lead:{fields:{}},updated_at:new Date().toISOString()};
 await p.route('**/api/v1/**',async route=>{
  if(route.request().url().endsWith('/messages')){
   calls++;const content=route.request().postDataJSON().content;
   if(failBeforeWrite){await route.abort('failed');return}
   session.messages.push({role:'user',content},{role:'assistant',content:'Ответ <img src=x onerror="window.injected=true">'});
   session.last_result={status:'answered',elapsed_ms:1250,sources:[{document_id:'<script>bad()</script>',quote:'<img src=x onerror="window.injected=true">'}]};
   if(fail){await route.abort('failed');return}
  }
  if(failHistory&&route.request().method()==='GET'&&route.request().url().endsWith('/'+session.id)){
   failHistory=false;await route.abort('failed');return;
  }
  await route.fulfill({json:route.request().url().endsWith('/sessions')&&route.request().method()==='GET'?{sessions:[session]}:session});
 });
 await p.goto(base+'/consultation.html');await p.waitForFunction(()=>document.querySelector('#energytool-chat').dataset.screen!=='waiting'&&!document.querySelector('#et-question').disabled);
 await p.locator('#et-question').fill('Тест потери соединения');await p.getByRole('button',{name:'Отправить',exact:true}).click();
 await p.getByRole('button',{name:'Обновить историю',exact:true}).waitFor();assert.equal(await p.locator('#et-question').isDisabled(),true);assert.equal(calls,1);
 assert.equal(await p.locator('#et-question').inputValue(),'Тест потери соединения');
 await p.getByRole('button',{name:'Обновить историю',exact:true}).click();await p.waitForFunction(()=>document.querySelector('#energytool-chat').dataset.screen!=='waiting'&&!document.querySelector('#et-question').disabled);
 assert.equal(await p.locator('.et-user').count(),1);assert.equal(await p.locator('.et-assistant').count(),1);assert.equal(calls,1);
 assert.equal(await p.locator('#et-question').inputValue(),'');
 assert.match(await p.locator('.et-assistant').innerText(),/<img/);assert.equal(await p.locator('.et-assistant img').count(),0);
 await p.getByRole('button',{name:'Меню',exact:true}).click();await p.getByRole('button',{name:'Включить режим отладки',exact:true}).click();await p.locator('[data-source-message]').last().click();
 assert.match(await p.locator('dialog').innerText(),/Получен ответ/);assert.match(await p.locator('dialog').innerText(),/<script>/);assert.equal(await p.locator('dialog script, dialog img').count(),0);assert.equal(await p.evaluate(()=>window.injected),undefined);
 await p.getByRole('button',{name:'Закрыть',exact:true}).click();
 session.last_result.status='technical_error';await p.reload();await p.getByRole('heading',{name:'Не удалось получить ответ',exact:true}).waitFor();
 fail=false;await p.getByRole('button',{name:'Повторить',exact:true}).click();await p.waitForFunction(()=>document.querySelector('#energytool-chat').dataset.screen!=='waiting'&&!document.querySelector('#et-question').disabled);assert.equal(calls,2);
 const send=p.getByRole('button',{name:'Отправить',exact:true});
 const refresh=p.getByRole('button',{name:'Обновить историю',exact:true});
 failBeforeWrite=true;
 await p.locator('#et-question').fill('Вопрос, который сервер не получил');
 await send.click();await refresh.waitFor();await refresh.click();await send.waitFor();
 assert.equal(await p.locator('#et-question').inputValue(),'Вопрос, который сервер не получил');
 assert.equal(calls,3);
 failBeforeWrite=false;failHistory=true;
 await send.click();await refresh.waitFor();
 assert.equal(await p.locator('#et-question').inputValue(),'Вопрос, который сервер не получил');
 await refresh.click();await p.waitForFunction(()=>document.querySelector('#energytool-chat').dataset.screen!=='waiting'&&!document.querySelector('#et-question').disabled);
 assert.equal(await p.locator('#et-question').inputValue(),'');
 assert.equal(await p.locator('.et-user').filter({hasText:'Вопрос, который сервер не получил'}).count(),1);
 assert.equal(calls,4);
 for(const width of [320,390,768,1024,1366,1440]){await p.setViewportSize({width,height:844});assert.equal(await p.evaluate(()=>document.documentElement.scrollWidth>innerWidth),false,'overflow at '+width);}
 await p.setViewportSize({width:390,height:480});
 await p.locator('#et-question').focus();
 const composer=await p.locator('.et-composer').boundingBox();
 assert.ok(composer.y+composer.height<=480,'composer is visible in a shortened mobile viewport');
 console.log('PASS: ambiguous network failure, no automatic duplicate POST, refresh recovery, model/source text escaping, technical retry, five viewport sizes.');
}finally{await b.close()}})().catch(e=>{console.error(e);process.exit(1)});
