// Regression: explicit task editor fields must keep their meaning through pending, model summaries and reload.
const assert=require('node:assert/strict');
const {chromium}=require(process.env.PLAYWRIGHT_MODULE||'playwright');
const base=process.env.WEB_TEST_URL||'http://127.0.0.1:8775';
(async()=>{
 const browser=await chromium.launch({headless:true});
 try {
  const page=await browser.newPage({viewport:{width:1440,height:960}}),errors=[];
  page.on('pageerror',e=>errors.push(e.message));
  const sessions={};let count=0,posts=0,gate=null;
  const responseQueue=[];
  await page.route('**/api/v1/**',async route=>{
   const req=route.request(),parts=new URL(req.url()).pathname.split('/').filter(Boolean);let result;
   if(parts.length===3&&req.method()==='POST'){
    const id='task-mapping-'+(++count);result=sessions[id]={id,status:'active',messages:[],lead:{fields:{}},updated_at:new Date().toISOString()};
   }else if(parts.length===3)result={sessions:Object.values(sessions)};
   else{
    const session=sessions[parts[3]];assert.ok(session);
    if(parts[4]==='messages'){
     posts++;session.messages.push({role:'user',content:req.postDataJSON().content});
     if(gate)await new Promise(resolve=>{gate.release=resolve});
     const next=responseQueue.shift()||{};
     result={status:'answered',answer:'Ответ для проверки карточки.',summary:{},sources:[],elapsed_ms:10,lead:{fields:{}},...next};
     session.last_result=result;session.messages.push({role:'assistant',content:result.answer,response:result});
    }else result=session;
   }
   await route.fulfill({json:result});
  });
  const ready=()=>page.waitForFunction(()=>document.querySelector('#energytool-chat').dataset.screen!=='waiting'&&!document.querySelector('#et-question').disabled);
  const value=key=>page.locator(`.et-sidebar .et-task-row[data-task-key="${key}"] .et-task-value`);
  const send=async text=>{await page.locator('#et-question').fill(text);await page.locator('.et-send').click();await ready();};
  const original='Уточнение — объект: Частный дом\n\nУточнение — задача: Хочу уменьшить потребление\n\nУточнение — известные сведения: Расходы сейчас 30000 рублей в год\n\nДополнение к задаче: Хочу подешевле';
  const explicit=async()=>{
   assert.equal(await value('object').innerText(),'Частный дом','object field must not be dumped into task');
   assert.equal(await value('task').innerText(),'Хочу уменьшить потребление');
   assert.equal(await value('parameters').innerText(),'Расходы сейчас 30000 рублей в год');
   assert.equal(await value('notes').innerText(),'Хочу подешевле','legacy generic addition stays separately labelled');
   assert.doesNotMatch(await value('task').innerText(),/Уточнение|30000|Частный дом/);
  };
  await page.goto(base+'/consultation.html?start=new');await ready();
  responseQueue.push({summary:{
   object:[{value:'Хочу уменьшить потребление',message_index:0}],
   task:[{value:'Частный дом',message_index:0}],
   parameters:[{value:'Хочу подешевле',message_index:0}],
  }});
  gate={};await page.locator('#et-question').fill(original);await page.locator('.et-send').click();
  await page.locator('.et-pending').waitFor();
  await explicit();
  await page.locator('#et-question').fill('Уточнение — объект: Это только неотправленный черновик');
  await explicit();assert.equal(posts,1);
  gate.release();gate=null;await ready();await explicit();
  await page.reload();await ready();await explicit();

  // A correction replaces the old explicit field, even if the next model result has no summary.
  const unsafe='Таунхаус <img src=x onerror="window.injected=true">';
  await send('Уточнение — объект: '+unsafe);
  assert.equal(await value('object').innerText(),unsafe);
  assert.doesNotMatch(await value('object').innerText(),/Частный дом/);
  assert.equal(await value('object').locator('img').count(),0);
  assert.equal(await page.evaluate(()=>window.injected),undefined);
  assert.equal(await value('task').innerText(),'Хочу уменьшить потребление');
  assert.equal(await value('parameters').innerText(),'Расходы сейчас 30000 рублей в год');
  await page.reload();await ready();assert.equal(await value('object').innerText(),unsafe);

  // A genuinely newer user fact may supersede old explicit input if summary carries its evidence index.
  responseQueue.push({summary:{object:[{value:'Офис',message_index:4}],parameters:[{value:'Расходы сейчас 30000 рублей в год',message_index:0},{value:'Есть приборы учёта',message_index:4}]}});
  await send('Объект теперь Офис. Есть приборы учёта');
  assert.match(await value('parameters').innerText(),/30000 рублей в год/);
  assert.match(await value('parameters').innerText(),/Есть приборы учёта/);
  assert.equal(await value('object').innerText(),'Офис');
  assert.equal(await value('task').innerText(),'Хочу уменьшить потребление');

  // Add fact form makes field choice explicit and does not submit anything by itself.
  const priorPosts=posts;
  await page.locator('.et-sidebar [data-action="task-add"]').click();
  assert.equal(await page.locator('.et-task-form select[name="field"]').inputValue(),'parameters');
  await page.locator('.et-task-form select[name="field"]').selectOption('constraints');
  await page.locator('.et-task-form textarea[name="detail"]').fill('Без замены проводки');
  await page.getByRole('button',{name:'Добавить в черновик',exact:true}).click();
  assert.equal(await page.locator('#et-question').inputValue(),'Дополнение — условия: Без замены проводки');
  assert.equal(posts,priorPosts);
  assert.equal(await page.locator('.et-sidebar .et-task-row[data-task-key="constraints"]').count(),0);
  await page.locator('.et-send').click();await ready();
  assert.equal(await value('constraints').innerText(),'Без замены проводки');

  // Application review must use the same resolved field meanings as the visible card.
  await page.getByRole('button',{name:'Подготовить заявку',exact:true}).click();
  await page.getByLabel('Телефон или email',{exact:true}).fill('mapping@example.com');
  await page.getByRole('button',{name:'Проверить заявку',exact:true}).click();
  const review=await page.locator('.et-review .et-application-summary').last().innerText();
  assert.match(review,/Объект:\n• Офис/);
  assert.match(review,/Задача клиента:\n• Хочу уменьшить потребление/);
  assert.match(review,/Известные параметры:\n• Расходы сейчас 30000 рублей в год/);
  assert.match(review,/Условия и ограничения:\n• Без замены проводки/);
  assert.match(review,/Дополнения клиента:\n• Хочу подешевле/);
  assert.doesNotMatch(review,/Уточнение —|Дополнение к задаче:/);

  // Plain free text stays a verbatim task fallback; no semantic guesswork invents an object.
  await page.goto(base+'/consultation.html?start=new');await ready();
  const plain='У нас выросли счета. Что проверить сначала?';
  gate={};await page.locator('#et-question').fill(plain);await page.locator('.et-send').click();
  await page.locator('.et-pending').waitFor();
  assert.equal(await value('task').innerText(),plain);
  assert.equal(await value('object').innerText(),'Пока не уточнили');
  gate.release();gate=null;await ready();
  assert.equal(await value('task').innerText(),plain);
  assert.deepEqual(errors,[]);
  console.log('PASS: typed field separation pending/answer/reload; incorrect same-message summary ignored; corrections replace; newer grounded model evidence updates; unsent draft isolation; explicit add-fact field; legacy notes; review summary field parity; plain fallback; XSS escaping.');
 }finally{await browser.close()}
})().catch(e=>{console.error(e);process.exit(1)});
