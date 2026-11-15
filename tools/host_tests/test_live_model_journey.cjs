// Runs against the real local backend and model. No routes or responses are mocked.
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const {chromium}=require(process.env.PLAYWRIGHT_MODULE||'playwright');
const base=process.env.WEB_TEST_URL||'http://127.0.0.1:8768';
const out=process.env.WEB_TEST_OUTPUT||'reports/live-user-audit-20261115/main';
if(!/^http:\/\/(127\.0\.0\.1|localhost):/.test(base))throw Error('Local demo stack required');
fs.mkdirSync(out,{recursive:true});
const report={started_at:new Date().toISOString(),base,mocked:false,steps:[],errors:[],posts:[],answers:[]};
const record=(step,data={})=>{const event={step,at:new Date().toISOString(),...data};report.steps.push(event);console.log(JSON.stringify(event));fs.writeFileSync(path.join(out,'result.json'),JSON.stringify(report,null,2));};
(async()=>{
 const browser=await chromium.launch({headless:true});
 const context=await browser.newContext({viewport:{width:1440,height:960},locale:'ru-RU'});
 const page=await context.newPage();page.setDefaultTimeout(15000);
 page.on('pageerror',e=>report.errors.push(e.message));
 page.on('request',r=>{if(r.method()==='POST'&&r.url().endsWith('/messages'))report.posts.push({at:new Date().toISOString(),...r.postDataJSON()});});
 const button=name=>page.getByRole('button',{name,exact:true});
 const capture=async name=>{
   await page.evaluate(()=>document.fonts.ready);
   const file=path.join(out,name+'.png');await page.screenshot({path:file,fullPage:false});
   const screen=await page.locator('#energytool-chat').count()?await page.locator('#energytool-chat').getAttribute('data-screen'):null;
   record(name,{screen,screenshot:file});
 };
 const ready=()=>page.waitForFunction(()=>document.querySelector('#et-question')&&!document.querySelector('#et-question').disabled);
 const waitAnswer=async label=>{
   const started=Date.now();let announced=0;
   for(;;){
     const state=await page.locator('#energytool-chat').getAttribute('data-screen');
     if(!['waiting','sync'].includes(state)&&await page.locator('.et-assistant').count()||state==='technical_error')break;
     if(Date.now()-started>310000)throw Error(label+': no answer after 310 seconds');
     if(Date.now()-announced>25000){record(label+'-waiting',{seconds:Math.round((Date.now()-started)/1000),state});announced=Date.now();}
     await page.waitForTimeout(1000);
   }
   const id=await page.evaluate(()=>localStorage.getItem('energytool-session'));
   const session=await(await page.request.get(base+'/api/v1/sessions/'+id)).json();
   const result=session.last_result;report.answers.push({label,session_id:id,result});
   record(label+'-received',{status:result?.status,elapsed_ms:result?.elapsed_ms,answer:result?.answer});
   await capture(label);
   return result;
 };
 try{
   await page.goto(base+'/consultation.html?start=new');await ready();
   report.session_id=await page.evaluate(()=>localStorage.getItem('energytool-session'));
   await capture('01-welcome');
   const question='У нас склад с двумя арендаторами. Показания электросчётчиков переписываем вручную раз в месяц. Как организовать раздельный учёт и снизить потери?';
   const followup='У каждого арендатора уже есть отдельный электросчётчик, показания пока снимаем вручную. Можно начать автоматизацию с этих счётчиков? Какие сведения о них собрать для специалиста?';
   await page.locator('#et-question').fill(question);await button('Отправить').click();
   await page.locator('.et-pending').waitFor();await page.locator('#et-question').fill(followup);
   await page.waitForTimeout(5000);await capture('02-waiting-with-draft');
   await button('Прервать ожидание').click();await page.locator('.et-recovery').waitFor();await capture('03-interrupted');
   await button('Меню').click();await button('Вернуться на сайт').click();
   await page.locator('dialog').getByRole('button',{name:'Закрыть чат',exact:true}).click();
   await page.waitForURL(base+'/');await capture('04-site');
   await button('Заказать консультацию').first().click();await ready();
   assert.equal(await page.evaluate(()=>localStorage.getItem('energytool-session')),report.session_id,'return must resume same conversation');
   assert.equal(await page.locator('#et-question').inputValue(),followup,'next draft must survive exit');
   assert.equal(report.posts.length,1,'exit/return must not repeat original request');
   await capture('05-returned');
   let result=await waitAnswer('06-first-answer');
   if(result.status==='technical_error'){
     await button('Повторить').click();result=await waitAnswer('06b-retry-answer');
   }
   assert.notEqual(result.status,'technical_error','live model must provide a substantive first response');
   assert.equal(await page.locator('#et-question').inputValue(),followup);
   await button('Отправить').click();await page.locator('.et-pending').waitFor();
   record('07-followup-sent');
   await page.waitForFunction(()=>{
     const screen=document.querySelector('#energytool-chat').dataset.screen;
     const operator=document.querySelector('.et-wait-long [data-action="operator"]');
     return !['waiting','sync'].includes(screen)||operator?.getBoundingClientRect().height>0;
   },undefined,{timeout:35000});
   await capture('08-longwait-operator');
   if(await button('Позвать оператора').isVisible())await button('Позвать оператора').click();
   else{await button('Меню').click();await page.locator('dialog').getByRole('button',{name:'Подготовить заявку',exact:true}).click();}
   await page.getByLabel('Телефон или email',{exact:true}).fill('live-audit@example.test');
   await page.getByLabel('Имя и фамилия',{exact:true}).fill('Проверка живого сценария');
   await page.getByLabel('Название компании',{exact:true}).fill('Тестовый склад · аудит интерфейса');
   await capture('09-operator-contacts');
   await button('Проверить заявку').click();await capture('10-review');
   await button('Вернуться к консультации').click();
   assert.equal(await page.locator('#et-question').isVisible(),true);
   const operator=button('Позвать оператора');
   if(await operator.isVisible())await operator.click();else{await button('Меню').click();await page.locator('dialog').getByRole('button',{name:'Подготовить заявку',exact:true}).click();}
   assert.equal(await page.getByLabel('Телефон или email',{exact:true}).inputValue(),'live-audit@example.test');
   await button('Проверить заявку').click();await button('Сформировать заявку').click();
   await page.getByRole('heading',{name:'Заявка сформирована',exact:true}).waitFor();await capture('11-saved');
   const download=page.waitForEvent('download');await page.locator('.et-review').getByRole('button',{name:'Скачать заявку',exact:true}).click();
   const file=await download;await file.saveAs(path.join(out,file.suggestedFilename()));
   record('12-downloaded',{filename:file.suggestedFilename()});
   await button('Продолжить консультацию').click();result=await waitAnswer('13-followup-answer');
   if(result.status==='technical_error'){
     await button('Повторить').click();result=await waitAnswer('13b-followup-retry');
   }
   assert.notEqual(result.status,'technical_error','live model must provide a substantive followup response');
   await page.reload();await ready();await button('Меню').click();await button('Сохранённая заявка').click();
   assert.match(await page.locator('.et-review').innerText(),/live-audit@example.test/);
   await capture('14-saved-after-reload');
   const session=await(await page.request.get(base+'/api/v1/sessions/'+report.session_id)).json();
   report.application=session.application;
   report.message_count=session.messages.length;
   assert.ok(session.application?.id);assert.equal(session.messages.filter(m=>m.role==='user'&&m.content===question).length,report.posts.filter(p=>p.content===question).length);
   assert.ok(session.application.summary.includes('отдельный электросчётчик'),'operator handoff includes the most recent clarification');
   const queue=await(await page.request.get(base+'/api/v1/applications')).json();
   assert.ok(queue.applications.some(a=>a.session_id===report.session_id),'operator application must be in queue');
   await page.setViewportSize({width:390,height:844});await capture('15-mobile-saved');
   assert.ok(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1));
   assert.deepEqual(report.errors,[]);report.passed=true;record('complete',{application_number:session.application.number||session.application.id});
 }catch(error){report.passed=false;report.failure=error.stack;await capture('failure').catch(()=>{});record('failed',{error:error.message});process.exitCode=1;}
 finally{report.finished_at=new Date().toISOString();fs.writeFileSync(path.join(out,'result.json'),JSON.stringify(report,null,2));await browser.close();}
})();
