// Live regression for commercial-loss requirements leaking into bill diagnosis.
const assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path');
const {chromium}=require(process.env.PLAYWRIGHT_MODULE||'playwright');
const base=process.env.WEB_TEST_URL||'http://127.0.0.1:8768';
const out=process.env.WEB_TEST_OUTPUT||'reports/live-user-audit-20261115/bill-diagnosis';
if(!/^http:\/\/(127\.0\.0\.1|localhost):/.test(base))throw Error('Local demo stack required');
fs.mkdirSync(out,{recursive:true});
const report={started_at:new Date().toISOString(),mocked:false,errors:[]};
const record=(step,data={})=>{console.log(JSON.stringify({step,...data}));fs.writeFileSync(path.join(out,'result.json'),JSON.stringify(report,null,2));};
(async()=>{
 const browser=await chromium.launch({headless:true});let page;
 try{
  page=await browser.newPage({viewport:{width:1440,height:960},locale:'ru-RU'});
  page.on('pageerror',e=>report.errors.push(e.message));
  await page.goto(base+'/consultation.html?start=new');
  await page.waitForFunction(()=>document.querySelector('#et-question')&&!document.querySelector('#et-question').disabled);
  report.session_id=await page.evaluate(()=>localStorage.getItem('energytool-session'));
  report.question='Это небольшое кафе. Счета выросли после установки второй холодильной витрины, показания снимаем вручную. Какие первые действия помогут разобраться?';
  await page.locator('#et-question').fill(report.question);
  await page.getByRole('button',{name:'Отправить',exact:true}).click();
  await page.locator('.et-pending').waitFor();record('sent');
  const start=performance.now();let last=0;
  while(['waiting','sync'].includes(await page.locator('#energytool-chat').getAttribute('data-screen'))){
   const elapsed=performance.now()-start;
   if(elapsed>310000)throw Error('Live bill diagnosis timed out');
   if(elapsed-last>25000){record('waiting',{seconds:Math.round(elapsed/1000)});last=elapsed;}
   await page.waitForTimeout(1000);
  }
  const session=await(await page.request.get(base+'/api/v1/sessions/'+report.session_id)).json();
  report.result=session.last_result;
  await page.screenshot({path:path.join(out,'answer.png')});
  record('received',{answer:report.result.answer,status:report.result.status,elapsed_ms:report.result.elapsed_ms,repairs:report.result.debug?.repairs});
  assert.equal(report.result.status,'answered');
  assert.match(report.result.answer,/сравн|проверь|сопостав/iu);
  assert.doesNotMatch(report.result.answer,/670[^.!?]*оптов|оптов[^.!?]*670/iu);
  assert.doesNotMatch(report.result.answer,/(?:нуж|потреб|необходим|минимум|не менее)[^.!?]*(?:год|дневн[^.!?]*ночн)/iu,'first bill diagnosis must not require a commercial-loss dataset');
  assert.ok(!report.result.sources.some(s=>s.document_id.includes('24-losses')),'unrelated commercial-loss product is excluded from this diagnosis');
  report.meter_question='Модель нашего существующего электросчётчика мне неизвестна. Можно ли подключить его без замены?';
  await page.locator('#et-question').fill(report.meter_question);
  await page.getByRole('button',{name:'Отправить',exact:true}).click();
  await page.locator('.et-pending').waitFor();const meterStart=performance.now();last=0;
  while(['waiting','sync'].includes(await page.locator('#energytool-chat').getAttribute('data-screen'))){
   const elapsed=performance.now()-meterStart;
   if(elapsed>310000)throw Error('Live unknown meter question timed out');
   if(elapsed-last>25000){record('meter-waiting',{seconds:Math.round(elapsed/1000)});last=elapsed;}
   await page.waitForTimeout(1000);
  }
  const meterSession=await(await page.request.get(base+'/api/v1/sessions/'+report.session_id)).json();
  report.meter_result=meterSession.last_result;
  await page.screenshot({path:path.join(out,'unknown-meter.png')});
  record('meter-received',{answer:report.meter_result.answer,status:report.meter_result.status,elapsed_ms:report.meter_result.elapsed_ms,routing:report.meter_result.debug?.routing});
  assert.notEqual(report.meter_result.status,'technical_error');
  assert.doesNotMatch(report.meter_result.answer,/^\s*(?:да\b|можно\s+подключить)/iu);
  assert.doesNotMatch(report.meter_result.answer,/(?:какой|какая|уточните)[^.!?]*(?:модел|тип)[^.!?]*\?/iu,'explicitly unknown model should not be immediately requested again');
  assert.match(report.meter_result.answer,/специалист|позже/iu);
  assert.deepEqual(report.errors,[]);report.passed=true;record('complete');
 }catch(error){report.passed=false;report.failure=error.stack;if(page)await page.screenshot({path:path.join(out,'failure.png')}).catch(()=>{});record('failed',{error:error.message});process.exitCode=1;}
 finally{report.finished_at=new Date().toISOString();fs.writeFileSync(path.join(out,'result.json'),JSON.stringify(report,null,2));await browser.close();}
})();
