// Rechecks only content defects found in the live user audit. No mocked API/model.
const assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path');
const {chromium}=require(process.env.PLAYWRIGHT_MODULE||'playwright');
const base=process.env.WEB_TEST_URL||'http://127.0.0.1:8768';
const out=process.env.WEB_TEST_OUTPUT||'reports/live-user-audit-20261115/content-fixed';
if(!/^http:\/\/(127\.0\.0\.1|localhost):/.test(base))throw Error('Local demo stack required');
fs.mkdirSync(out,{recursive:true});
const report={started_at:new Date().toISOString(),mocked:false,answers:[],errors:[]};
const record=(step,data={})=>{console.log(JSON.stringify({step,...data}));fs.writeFileSync(path.join(out,'result.json'),JSON.stringify(report,null,2));};
(async()=>{
 const browser=await chromium.launch({headless:true});
 try{
  const page=await browser.newPage({viewport:{width:1440,height:960},locale:'ru-RU'});
  page.on('pageerror',e=>report.errors.push(e.message));
  const readResult=async(text,label)=>{
   const id=await page.evaluate(()=>localStorage.getItem('energytool-session'));
   const session=await(await page.request.get(base+'/api/v1/sessions/'+id)).json();
   const result=session.last_result;assert.ok(result,'real session must contain a completed answer');
   report.answers.push({label,question:text,session_id:id,result});
   await page.screenshot({path:path.join(out,label+'.png')});
   record(label+'-received',{status:result.status,answer:result.answer,elapsed_ms:result.elapsed_ms,routing:result.debug?.routing,repairs:result.debug?.repairs});
   assert.notEqual(result.status,'technical_error');return result;
  };
  const send=async(text,label)=>{
   await page.locator('#et-question').fill(text);await page.getByRole('button',{name:'Отправить',exact:true}).click();
   await page.locator('.et-pending').waitFor();const start=performance.now();let last=0;
   while(['waiting','sync'].includes(await page.locator('#energytool-chat').getAttribute('data-screen'))){
    // Monotonic active time avoids counting a suspended laptop as model time.
    if(performance.now()-start>310000)throw Error(label+': timed out');
    if(performance.now()-last>25000){record(label+'-waiting',{seconds:Math.round((performance.now()-start)/1000)});last=performance.now();}
    await page.waitForTimeout(1000);
   }
   return readResult(text,label);
  };
  const opening='Хочу снизить расходы на электроэнергию, но не понимаю, с чего начать.';
  let result;
  if(process.env.WEB_TEST_RESUME_SESSION){
   report.recovered_session=process.env.WEB_TEST_RESUME_SESSION;
   await page.goto(base+'/');
   await page.evaluate(id=>{localStorage.setItem('energytool-session',id);localStorage.setItem('energytool-session-ids',JSON.stringify([id]));},report.recovered_session);
   await page.goto(base+'/consultation.html');
   await page.waitForFunction(()=>document.querySelector('#et-question')&&!document.querySelector('#et-question').disabled);
   result=await readResult(opening,'01-no-premature-product');
   assert.ok(await page.locator('.et-composer').isVisible(),'reopened real conversation is usable');
  }else{
   await page.goto(base+'/consultation.html?start=new');await page.waitForFunction(()=>!document.querySelector('#et-question').disabled);
   result=await send(opening,'01-no-premature-product');
  }
  assert.equal(result.status,'clarification');
  assert.doesNotMatch(result.answer,/солнечн|оптов[а-яё]*\s+рын|(?:670|750)\s*кВт/iu,'vague opening asks about the object instead of selecting a product');
  result=await send('Это небольшое кафе. Счета выросли после установки второй холодильной витрины, показания снимаем вручную. Какие первые действия помогут разобраться?','02-cafe-context');
  assert.doesNotMatch(result.answer,/(?:уточните|сообщите|какой|какого|что[^.!?]*уточнить)[^.!?]*тип[^.!?]*организа/iu,'already known cafe type must not be requested again');
  assert.doesNotMatch(result.answer,/670[^.!?]*оптов|оптов[^.!?]*670/iu,'retail price-category threshold is not wholesale eligibility');
  assert.doesNotMatch(result.answer,/(?:нуж|потреб|необходим|минимум|не менее)[^.!?]*(?:год|дневн[^.!?]*ночн)/iu,'first bill diagnosis must not require a commercial-loss dataset');
  // Resume the audit's real existing meter conversation; no fixture or API write seeds its history.
  const main=JSON.parse(fs.readFileSync('reports/live-user-audit-20261115/main-fixed/result.json'));
  await page.evaluate(id=>{localStorage.setItem('energytool-session',id);localStorage.setItem('energytool-session-ids',JSON.stringify([id]));},main.session_id);
  await page.goto(base+'/consultation.html');
  await page.waitForFunction(()=>document.querySelector('#et-question')&&!document.querySelector('#et-question').disabled);
  if(!await page.locator('.et-composer').isVisible())await page.getByRole('button',{name:'Продолжить консультацию',exact:true}).click();
  result=await send('Тип и модель счётчиков пока неизвестны. Подтвердите: можно ли подключить эти существующие счётчики без замены?','03-unknown-meter-compatibility');
  assert.ok(['clarification','knowledge_gap'].includes(result.status));
  assert.doesNotMatch(result.answer,/^\s*(?:да\b|можно\s+(?:подключить|начать)|подойдут)/iu,'unknown hardware compatibility cannot be promised');
  assert.match(result.answer,/провер|подтвержд|тип|модел/iu);
  assert.deepEqual(report.errors,[]);report.passed=true;record('complete');
 }catch(error){report.passed=false;report.failure=error.stack;record('failed',{error:error.message});process.exitCode=1;}
 finally{report.finished_at=new Date().toISOString();fs.writeFileSync(path.join(out,'result.json'),JSON.stringify(report,null,2));await browser.close();}
})();
