// Deterministic browser-only checks for failure recovery and untrusted model text.
const assert=require('node:assert/strict');
const {chromium}=require(process.env.PLAYWRIGHT_MODULE||'playwright');
const base=process.env.WEB_TEST_URL||'http://127.0.0.1:8768';
(async()=>{const b=await chromium.launch({headless:true});try{
 const p=await b.newPage();let calls=0,fail=true;
 const session={id:'browser-fixture',status:'active',messages:[],lead:{fields:{}},updated_at:new Date().toISOString()};
 await p.route('**/api/v1/**',async route=>{
  if(route.request().url().endsWith('/messages')){
   calls++;const content=route.request().postDataJSON().content;
   session.messages.push({role:'user',content},{role:'assistant',content:'Ответ <img src=x onerror="window.injected=true">'});
   session.last_result={status:'answered',elapsed_ms:1250,sources:[{document_id:'<script>bad()</script>',quote:'<img src=x onerror="window.injected=true">'}]};
   if(fail){await route.abort('failed');return}
  }
  await route.fulfill({json:route.request().url().endsWith('/sessions')&&route.request().method()==='GET'?{sessions:[session]}:session});
 });
 await p.goto(base+'/consultation.html');await p.waitForFunction(()=>!document.querySelector('#et-question').disabled);
 await p.locator('#et-question').fill('Тест потери соединения');await p.getByRole('button',{name:'Отправить',exact:true}).click();
 await p.getByRole('button',{name:'Обновить историю',exact:true}).waitFor();assert.equal(await p.locator('#et-question').isDisabled(),true);assert.equal(calls,1);
 await p.getByRole('button',{name:'Обновить историю',exact:true}).click();await p.waitForFunction(()=>!document.querySelector('#et-question').disabled);
 assert.equal(await p.locator('.et-user').count(),1);assert.equal(await p.locator('.et-assistant').count(),1);assert.equal(calls,1);
 assert.match(await p.locator('.et-assistant').innerText(),/<img/);assert.equal(await p.locator('.et-assistant img').count(),0);
 await p.getByRole('button',{name:'Меню',exact:true}).click();await p.getByRole('button',{name:'Включить режим отладки',exact:true}).click();await p.locator('[data-source-message]').last().click();
 assert.match(await p.locator('dialog').innerText(),/<script>/);assert.equal(await p.locator('dialog script, dialog img').count(),0);assert.equal(await p.evaluate(()=>window.injected),undefined);
 await p.getByRole('button',{name:'Закрыть',exact:true}).click();
 session.last_result.status='technical_error';await p.reload();await p.getByRole('heading',{name:'Не удалось получить ответ',exact:true}).waitFor();
 fail=false;await p.getByRole('button',{name:'Повторить',exact:true}).click();await p.waitForFunction(()=>!document.querySelector('#et-question').disabled);assert.equal(calls,2);
 for(const width of [320,390,768,1024,1440]){await p.setViewportSize({width,height:844});assert.equal(await p.evaluate(()=>document.documentElement.scrollWidth>innerWidth),false,'overflow at '+width);}
 console.log('PASS: ambiguous network failure, no automatic duplicate POST, refresh recovery, model/source text escaping, technical retry, five viewport sizes.');
}finally{await b.close()}})().catch(e=>{console.error(e);process.exit(1)});
