const assert=require('node:assert/strict'),fs=require('node:fs');
const {chromium}=require(process.env.PLAYWRIGHT_MODULE||'playwright');
const base=process.env.WEB_TEST_URL||'http://127.0.0.1:8768';
const shots=process.env.WEB_TEST_SHOTS||'/tmp/mts-design-review';fs.mkdirSync(shots,{recursive:true});
(async()=>{const browser=await chromium.launch({headless:true});try{
 const p=await browser.newPage({viewport:{width:1440,height:960}});const errors=[];p.on('pageerror',e=>errors.push(e.message));
 let counter=0,queue=[],gate=null;const sessions={};
 const makeResult=(s,status,answer)=>({status,answer,elapsed_ms:1800,sources:status==='answered'?[{document_id:'Технический учёт электроэнергии',quote:'Раздельный учёт позволяет анализировать потребление по отдельным объектам.'}]:[],lead:{session_id:s.id,fields:{}},summary:{task:[{value:'Выросли счета по трём магазинам.'}]}});
 await p.route('**/api/v1/**',async route=>{
  const req=route.request(),path=new URL(req.url()).pathname.split('/').filter(Boolean),id=path[3];let result;
  if(path.length===3&&req.method()==='POST'){result=sessions['s'+(++counter)]={id:'s'+counter,status:'active',messages:[],lead:{fields:{}},updated_at:new Date().toISOString()};}
  else if(path.length===3) result={sessions:Object.values(sessions)};
  else {const s=sessions[id];if(path[4]==='messages'){
   const data=req.postDataJSON();s.messages.push({role:'user',content:data.content});
   if(gate)await new Promise(resolve=>{gate.release=resolve});
   const [status,answer]=queue.shift()||['answered','Начните с раздельного учёта.'];result=makeResult(s,status,answer);
   if(data.content==='Хочу поговорить со специалистом')s.lead=result.lead={...result.lead,requested:true,declined:false};
   s.last_result=result;s.messages.push({role:'assistant',content:answer,response:{status,sources:result.sources,elapsed_ms:result.elapsed_ms}});
  }else if(path[4]==='application'){s.application={...req.postDataJSON(),saved_at:new Date().toISOString()};result=s;}
  else if(path[4]==='close'){s.status='closed';result=s;}else result=s;}
  await route.fulfill({json:result});
 });
 const ready=()=>p.waitForFunction(()=>!document.querySelector('#et-question').disabled);
 const snap=async name=>{await p.evaluate(()=>document.fonts.ready);await p.screenshot({path:shots+'/'+name+'.png'});};
 const fresh=async()=>{await p.goto(base+'/consultation.html?start=new');await ready();};
 const send=async text=>{await p.locator('#et-question').fill(text);await p.getByRole('button',{name:'Отправить',exact:true}).click();await ready();};
 await fresh();assert.equal(await p.locator('.et-welcome').isVisible(),true);assert.equal(await p.locator('.et-flow .et-card').count(),0);await snap('01-welcome');
 await p.getByRole('button',{name:'Снизить расходы',exact:true}).click();assert.equal(await p.locator('.et-user').count(),0);await snap('02-input');
 queue.push(['clarification','По каждому магазину есть отдельные показания счётчика или вы видите только общую сумму в счетах?']);gate={};await p.getByRole('button',{name:'Отправить',exact:true}).click();await p.locator('.et-pending').waitFor();assert.equal(await p.locator('.et-welcome').isVisible(),false);await snap('03-waiting');gate.release();gate=null;await ready();
 assert.equal(await p.getByRole('button',{name:'Подготовить заявку',exact:true}).count(),0);await p.getByRole('button',{name:'Вижу только общую сумму',exact:true}).waitFor();await snap('04-clarification');
 queue.push(['answered','Начните с раздельного учёта по магазинам. Соберите показания каждой точки за один и тот же период.']);await p.getByRole('button',{name:'Вижу только общую сумму',exact:true}).click();await ready();await snap('05-recommendation');
 await p.getByRole('button',{name:'Меню',exact:true}).click();await p.getByRole('button',{name:'Включить режим отладки',exact:true}).click();assert.equal(await p.locator('[data-source-message]').count(),2);await snap('12-debug');
 await p.locator('[data-source-message="3"]').click();await snap('sources');await p.locator('[data-fragment="0"]').click();await snap('fragment');assert.match(await p.locator('dialog').innerText(),/Раздельный учёт/);await p.getByRole('button',{name:'Закрыть',exact:true}).click();
 await p.getByRole('button',{name:'Подготовить заявку',exact:true}).click();await snap('06-contacts');assert.equal(await p.locator('.et-contact-form input').count(),3);
 await p.getByRole('button',{name:'Продолжить без телефона',exact:true}).click();await snap('15-no-phone');assert.equal(await p.getByRole('button',{name:'Подготовить заявку',exact:true}).count(),0);
 queue.push(['answered','Для каждой точки запишите показания за начало и конец одного периода, даты замеров и режим работы.']);await p.getByRole('button',{name:'Какие данные собрать?',exact:true}).click();await ready();await snap('15r-continue');await p.getByRole('button',{name:'Вернуться к заявке',exact:true}).click();
 await p.getByLabel('Имя и фамилия',{exact:true}).fill('Анна Миронова');await p.getByLabel('Телефон',{exact:true}).fill('+7 999 123 45 67');await p.getByLabel('Название компании',{exact:true}).fill('Тестовая компания');await p.getByRole('button',{name:'Проверить заявку',exact:true}).click();await snap('07-review');
 await p.getByRole('button',{name:'Изменить данные',exact:true}).click();await snap('edit');await p.getByLabel('Телефон',{exact:true}).fill('123');await p.getByRole('button',{name:'Сохранить',exact:true}).click();await snap('edit-error');assert.equal(await p.locator('.et-phone-error').count(),1);await p.getByLabel('Телефон',{exact:true}).fill('+7 999 765 43 21');await p.getByRole('button',{name:'Сохранить',exact:true}).click();assert.equal(await p.locator('dialog').isVisible(),false);await snap('07-updated');
 await p.getByRole('button',{name:'Сформировать заявку',exact:true}).click();await p.getByRole('heading',{name:'Заявка сформирована',exact:true}).waitFor();await snap('09-saved');
 await p.setViewportSize({width:390,height:844});await snap('09-mobile');await p.setViewportSize({width:1440,height:960});
 await p.locator('.et-flow').getByRole('button',{name:'История диалогов',exact:true}).click();await snap('history');await p.locator('[data-session]').first().click();await snap('archive');assert.match(await p.locator('dialog').innerText(),/765 43 21/);await p.getByRole('button',{name:'Закрыть',exact:true}).click();
 const oldId=await p.evaluate(()=>localStorage.getItem('energytool-session'));await fresh();assert.equal(await p.locator('.et-welcome').isVisible(),true);assert.notEqual(await p.evaluate(()=>localStorage.getItem('energytool-session')),oldId);
 for(const [state,text,title] of [['knowledge_gap','В базе EnergyTool нет данных для точного ответа на этот вопрос.','16-gap'],['out_of_scope','Я консультирую по учёту электроэнергии и решениям EnergyTool.','16b-scope'],['technical_error','Технический сбой.','14-error']]){
  await fresh();queue.push([state,text]);await send('Тестовый вопрос');await snap(title);
  assert.equal(await p.getByRole('heading',{name:'Разобраться вместе со специалистом',exact:true}).count(),0);
  if(state==='technical_error'){assert.equal(await p.locator('.et-error').count(),1);assert.equal(await p.locator('.et-assistant').count(),0);}
  if(state==='out_of_scope')assert.equal(await p.getByRole('button',{name:'Подготовить заявку',exact:true}).count(),0);
 }
 await fresh();queue.push(['clarification','Как я могу помочь?']);await send('Хочу поговорить со специалистом');
 await p.getByRole('button',{name:'Подготовить заявку',exact:true}).click();
 await p.getByRole('heading',{name:'Как с вами связаться?',exact:true}).waitFor();
 for(const width of [320,390,768,1024,1440]){await p.setViewportSize({width,height:844});assert.equal(await p.evaluate(()=>document.documentElement.scrollWidth>innerWidth),false,'overflow '+width);}
 assert.deepEqual(errors,[]);console.log('PASS: design states, correct cards and order, per-answer sources, editable modal, no-phone branch, archive, fresh entry, five viewports.');
}finally{await browser.close()}})().catch(e=>{console.error(e);process.exit(1)});
