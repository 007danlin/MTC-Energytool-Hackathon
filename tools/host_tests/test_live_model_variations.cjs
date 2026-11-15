// Alternative user journeys on the real local model/backend, with no API mocks.
const assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path');
const {chromium}=require(process.env.PLAYWRIGHT_MODULE||'playwright');
const base=process.env.WEB_TEST_URL||'http://127.0.0.1:8768';
const out=process.env.WEB_TEST_OUTPUT||'reports/live-user-audit-20261115/variations';
if(!/^http:\/\/(127\.0\.0\.1|localhost):/.test(base))throw Error('Local demo stack required');
fs.mkdirSync(out,{recursive:true});
const result={started_at:new Date().toISOString(),mocked:false,scenarios:[],errors:[]};
const log=(step,data={})=>{console.log(JSON.stringify({step,...data}));fs.writeFileSync(path.join(out,'result.json'),JSON.stringify(result,null,2));};
(async()=>{
 const browser=await chromium.launch({headless:true});
 try{
  const page=await browser.newPage({viewport:{width:390,height:844},locale:'ru-RU'});
  page.on('pageerror',e=>result.errors.push(e.message));
  const b=name=>page.getByRole('button',{name,exact:true});
  const snap=async name=>{await page.evaluate(()=>document.fonts.ready);await page.screenshot({path:path.join(out,name+'.png')});};
  const ready=()=>page.waitForFunction(()=>document.querySelector('#et-question')&&!document.querySelector('#et-question').disabled);
  const send=async(text,label)=>{
   await page.locator('#et-question').fill(text);await b('Отправить').click();
   await page.locator('.et-pending').waitFor();const started=Date.now();let announced=0;
   for(;;){
    const state=await page.locator('#energytool-chat').getAttribute('data-screen');
    if(!['waiting','sync'].includes(state))break;
    if(Date.now()-started>310000)throw Error(label+': response timeout');
    if(Date.now()-announced>25000){log(label+'-waiting',{seconds:Math.round((Date.now()-started)/1000)});announced=Date.now();}
    await page.waitForTimeout(1000);
   }
   const id=await page.evaluate(()=>localStorage.getItem('energytool-session'));
   const session=await(await page.request.get(base+'/api/v1/sessions/'+id)).json();
   const item={label,session_id:id,question:text,result:session.last_result};result.scenarios.push(item);log(label+'-received',{status:item.result.status,answer:item.result.answer,elapsed_ms:item.result.elapsed_ms});
   assert.notEqual(item.result.status,'technical_error');await snap(label);return item;
  };
  await page.goto(base+'/consultation.html?start=new');await ready();
  const opening=await send('Хочу снизить расходы на электроэнергию, но не понимаю, с чего начать.','01-vague-question');
  assert.ok(['answered','clarification'].includes(opening.result.status));
  await b('Меню').click();await page.locator('dialog').getByRole('button',{name:'Подготовить заявку',exact:true}).click();
  await b('Продолжить без контакта').click();await b('Продолжить консультацию').click();
  assert.equal(await page.locator('#et-question').isEnabled(),true);await snap('02-continue-without-contacts');
  const next=await send('Это небольшое кафе. Счета выросли после установки второй холодильной витрины, показания снимаем вручную. Какие первые действия помогут разобраться?','03-clarifying-answer');
  assert.ok(['answered','clarification'].includes(next.result.status));
  await b('Меню').click();await b('Включить режим отладки').click();
  await page.locator('[data-source-message]').last().click();await snap('04-debug-sources');
  if(await page.locator('[data-fragment]').count()){
   await page.locator('[data-fragment]').first().click();await snap('05-source-fragment');await b('Назад к источникам').click();
  }
  await page.locator('dialog').getByRole('button',{name:'Закрыть',exact:true}).click();
  await b('Меню').click();await page.locator('dialog').getByRole('button',{name:'Новый диалог',exact:true}).click();await b('Начать новый').click();await ready();
  const off=await send('Какая погода завтра в Москве?','06-out-of-scope');
  assert.equal(off.result.status,'out_of_scope');await b('Задать другой вопрос').click();
  assert.equal(await page.locator('#et-question').isEnabled(),true);
  const gap=await send('Есть ли подтверждённая интеграция EnergyTool с системой QuasarGrid-9000?','07-unknown-integration');
  assert.equal(gap.result.status,'knowledge_gap');
  await b('Подготовить заявку').click();await b('Вернуться к консультации').click();
  assert.equal(await page.locator('#et-question').isEnabled(),true);await snap('08-gap-return');
  assert.ok(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1));
  assert.deepEqual(result.errors,[]);result.passed=true;log('complete');
 }catch(e){result.passed=false;result.failure=e.stack;log('failed',{error:e.message});process.exitCode=1;}
 finally{result.finished_at=new Date().toISOString();fs.writeFileSync(path.join(out,'result.json'),JSON.stringify(result,null,2));await browser.close();}
})();
