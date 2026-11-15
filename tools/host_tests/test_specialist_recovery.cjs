// Browser controls with isolated responses, including failures after mutations.
const assert=require('node:assert/strict');
const {chromium}=require(process.env.PLAYWRIGHT_MODULE||'playwright');
const base=process.env.WEB_TEST_URL||'http://127.0.0.1:8776';
(async()=>{
 const browser=await chromium.launch({headless:true});
 try{
  const page=await browser.newPage({viewport:{width:1366,height:900}}),errors=[],replies=[];
  const question={id:'recovery-request',version:1,status:'queued',question:'Как подключить учёт?',necessary_context:[]};
  const commands=new Map();let failList=false,entry=null,replyAttempts=0;
  page.on('pageerror',e=>errors.push(e.message));
  await page.route('**/api/v1/operator/**',async route=>{
   const request=route.request(),path=new URL(request.url()).pathname.split('/operator/')[1],parts=path.split('/');
   const json=(value,status=200)=>route.fulfill({status,json:JSON.parse(JSON.stringify(value))});
   if(parts[0]==='expert-requests'){
    if(request.method()==='GET'){
     if(parts.length===1){if(failList){failList=false;return json({},503)}return json({requests:[question]})}
     return json(question);
    }
    const data=request.postDataJSON(),action=parts[2];
    if(action==='reply'){replies.push(data);replyAttempts++;if(replyAttempts===1)return json({},503)}
    if(commands.has(data.command_id)){assert.deepEqual(data,commands.get(data.command_id));return json(question)}
    if(data.expected_version!==question.version)return json({},409);
    if(action==='assign')question.assignee_id=data.assignee_id;
    if(action==='start'){question.status='in_review';failList=true}
    if(action==='reply'){question.status='answered';question.reply={body:data.body,id:data.reply_id,delivery_status:'delivered'}}
    question.version++;commands.set(data.command_id,data);
    if(action==='reply'&&replyAttempts===2)return route.abort('failed');
    return json(question);
   }
   if(request.method()==='GET')return json(parts.length===1?{entries:entry?[entry]:[]}:entry);
   const data=request.postDataJSON();
   if(parts.length===1)entry={id:'recovery-knowledge',version:1,test:data.test,revisions:[{...data,revision:1,publication_status:'draft',runtime_status:'pending'}]};
   else{
    assert.equal(data.expected_version,entry.version);entry.version++;
    if(parts[2]==='approve'){assert.equal(Object.keys(data.checklist).length,5);entry.revisions[0].publication_status='approved';entry.revisions[0].runtime_status='active'}
    if(parts[2]==='revoke'){entry.revisions[0].publication_status='revoked';entry.revisions[0].runtime_status='inactive'}
   }
   return json(entry);
  });
  const login=async(actor,role)=>{
   await page.locator('#access').evaluate(el=>el.open=true);
   await page.locator('[name=actor]').fill(actor);await page.locator('[name=role]').selectOption(role);await page.locator('[name=token]').fill('fixture-key');
   await page.getByRole('button',{name:'Подключиться',exact:true}).click();
   await page.waitForFunction(()=>!document.querySelector('#access').open&&!document.querySelector('#refresh').disabled);
  };
  const openQuestion=()=>page.locator('[data-id="'+question.id+'"]').click();
  const idle=()=>page.waitForFunction(()=>!document.querySelector('#refresh').disabled);
  await page.goto(base+'/specialist.html');
  await login('coordinator','coordinator');await openQuestion();
  await page.locator('#assign [name=assignee]').fill('specialist');
  await page.getByRole('button',{name:'Назначить',exact:true}).click();await idle();
  assert.equal(question.assignee_id,'specialist');
  await login('specialist','specialist');await openQuestion();
  const body='Проверьте модель счётчика и передайте документацию для проверки подключения.';
  await page.locator('#reply [name=body]').fill(body);
  await page.locator('#refresh').click();await idle();
  assert.equal(await page.locator('#reply [name=body]').inputValue(),body,'refresh preserves the reply draft');
  await page.reload();await login('specialist','specialist');await openQuestion();
  assert.equal(await page.locator('#reply [name=body]').inputValue(),body,'reload preserves the reply draft');
  const reply=()=>page.getByRole('button',{name:'Сохранить и передать в диалог',exact:true}).click();
  await reply();await idle();
  assert.equal(replyAttempts,1,'failure to refresh the list after start must not prevent sending the reply');
  assert.equal(await page.locator('#reply [name=body]').inputValue(),body,'failed reply keeps the full answer');
  await reply();await idle();
  assert.equal(replyAttempts,2);
  assert.equal(await page.locator('#reply [name=body]').inputValue(),body,'lost response keeps the full answer');
  await reply();await idle();
  assert.equal(replyAttempts,3);
  assert.deepEqual(replies[1],replies[0],'transport retry reuses reply and command IDs');
  assert.deepEqual(replies[2],replies[0],'ambiguous retry reuses the same command');
  await page.getByText('Доставлен в диалог',{exact:true}).waitFor();
  assert.equal(question.reply.body,body);
  await page.locator('#new-draft').click();
  for(const [key,value]of Object.entries({title:'Проверка знаний',generalized_question:'Как подготовить сведения?',answer:'Соберите документацию счётчика.',applicability:'Перед проверкой совместимости.',basis:'Тестовый сценарий.'}))await page.locator('#draft [name='+key+']').fill(value);
  await page.locator('#draft [name=test]').check();
  await page.getByRole('button',{name:'Сохранить черновик',exact:true}).click();await idle();
  assert.equal(entry.test,true);
  await login('reviewer','reviewer');await page.locator('[data-id="'+entry.id+'"]').click();
  await page.locator('#approve input').first().waitFor();
  for(const checkbox of await page.locator('#approve input').all())await checkbox.check();
  await page.getByRole('button',{name:'Одобрить и опубликовать',exact:true}).click();await idle();
  assert.equal(entry.revisions[0].publication_status,'approved',await page.locator('#feedback').innerText());
  await page.locator('#revoke [name=reason]').fill('Проверка закончена');
  await page.getByRole('button',{name:'Отозвать из поиска',exact:true}).click();await idle();
  assert.equal(entry.revisions[0].runtime_status,'inactive');
  await page.locator('#requests-tab').click();await idle();await openQuestion();
  await page.locator('#knowledge-tab').click();await idle();
  await page.setViewportSize({width:390,height:844});
  assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth),false);
  assert.deepEqual(errors,[]);
  console.log('PASS: specialist assignment, reply drafts across refresh/reload, failed and ambiguous reply recovery, replay IDs, knowledge create/approve/revoke, tabs and mobile.');
 }finally{await browser.close()}
})().catch(e=>{console.error(e);process.exitCode=1});
