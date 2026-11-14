// One contact input, email extraction seed, channel replacement, legacy phone and secondary retention.
const assert=require('node:assert/strict'),fs=require('node:fs');
const {chromium}=require(process.env.PLAYWRIGHT_MODULE||'playwright');
const base=process.env.WEB_TEST_URL||'http://127.0.0.1:8768';
const realAPI=process.env.REAL_CONTACT_API==='1';
(async()=>{const browser=await chromium.launch({headless:true});try{
 const page=await browser.newPage({viewport:{width:1440,height:960}}),errors=[],posts=[];
 page.on('pageerror',e=>errors.push(e.message));
 const session={id:'email-test',status:'active',messages:[],lead:{fields:{email:'Seed+case@Example.COM'}},updated_at:new Date().toISOString()};
 if(realAPI) page.on('request',req=>{if(req.method()==='POST' && new URL(req.url()).pathname.endsWith('/application'))posts.push(req.postDataJSON());});
 if(!realAPI) await page.route('**/api/v1/**',async route=>{
  const req=route.request(),path=new URL(req.url()).pathname;
  if(path.endsWith('/application')){const body=req.postDataJSON();posts.push(body);session.application={...body,id:'ET-email-test',saved_at:new Date().toISOString()};}
  await route.fulfill({json:path.endsWith('/sessions')&&req.method()==='GET'?{sessions:[session]}:session});
 });
 const contact=()=>page.getByLabel('Телефон или email',{exact:true});
 const button=name=>page.getByRole('button',{name,exact:true});
 const ready=()=>page.waitForFunction(()=>!document.querySelector('#et-question').disabled);
 const edit=async()=>{await button('Меню').click();await button('Изменить контакты').click();};
 const saveEdit=async()=>{await button('Сохранить').click();await page.waitForFunction(()=>!document.querySelector('dialog').open);};
 const saved=async()=>{await button('Меню').click();await button('Сохранённая заявка').click();};
 await page.goto(base+'/consultation.html');await ready();
 await button('Оставить заявку специалисту').click();
 assert.equal(await contact().inputValue(),realAPI ? '' : 'Seed+case@Example.COM');
 assert.equal(await contact().getAttribute('type'),'text');
 assert.equal(await contact().getAttribute('inputmode'),'email');
 if(realAPI) await contact().fill('Seed+case@Example.COM');
 assert.equal(await page.locator('.et-callback').isVisible(),false);
 await page.getByLabel('Кратко о вашей задаче').fill('Нужен раздельный учёт по арендаторам.');
 for(const bad of ['x@localhost','a..b@example.com','x@-a.example','123']){
  await contact().fill(bad);await button('Проверить заявку').click();
  assert.equal(await page.locator('.et-phone-error').count(),1);
  assert.equal(await page.getByRole('heading',{name:'Проверьте заявку',exact:true}).count(),0);
 }
 await contact().fill('User+site@Example.COM');
 if(process.env.WEB_TEST_SHOTS){
  fs.mkdirSync(process.env.WEB_TEST_SHOTS,{recursive:true});
  await page.screenshot({path:process.env.WEB_TEST_SHOTS+'/contact-email-desktop.png'});
  await page.setViewportSize({width:320,height:760});
  await page.screenshot({path:process.env.WEB_TEST_SHOTS+'/contact-email-mobile.png'});
  await page.setViewportSize({width:1440,height:960});
 }
 await button('Проверить заявку').click();
 assert.match(await page.locator('.et-review').innerText(),/User\+site@Example\.COM/);
 assert.doesNotMatch(await page.locator('.et-review').innerText(),/Звонок/);
 await button('Сформировать заявку').click();await page.getByRole('heading',{name:'Заявка сформирована',exact:true}).waitFor();
 assert.equal(posts.at(-1).phone,'');assert.equal(posts.at(-1).email,'User+site@Example.COM');
 assert.equal(posts.at(-1).full_name,'');assert.equal(posts.at(-1).company,'');assert.equal(posts.at(-1).callback_at,'');
 const pending=page.waitForEvent('download');await page.locator('.et-review').getByRole('button',{name:'Скачать заявку',exact:true}).click();
 const text=fs.readFileSync(await (await pending).path(),'utf8');
 assert.match(text,/Email: User\+site@Example\.COM/);assert.doesNotMatch(text,/Телефон:|Звонок/);
 await page.reload();await ready();await saved();assert.match(await page.locator('.et-review').innerText(),/User\+site/);
 await edit();assert.equal(await contact().inputValue(),'User+site@Example.COM');
 await contact().fill('+7 999 123 45 67');assert.equal(await page.locator('.et-callback').isVisible(),true);await saveEdit();
 assert.equal(posts.at(-1).phone,'+7 999 123 45 67');assert.equal(posts.at(-1).email,undefined,'replaced sole email must not silently survive');
 await edit();await contact().fill('replacement@example.com');await saveEdit();
 assert.equal(posts.at(-1).phone,'');assert.equal(posts.at(-1).email,'replacement@example.com');
 // A separately supplied second contact remains visible and survives a phone edit.
 if(realAPI) {
  const id=await page.evaluate(()=>localStorage.getItem('energytool-session'));
  const response=await page.request.post(base+'/api/v1/sessions/'+id+'/application',{data:{phone:'+7 999 222 33 44',email:'secondary@example.com',summary:'Учёт по арендаторам.'}});
  assert.equal(response.status(),200);
 } else session.application={...session.application,phone:'+7 999 222 33 44',email:'secondary@example.com'};
 await page.reload();await ready();await saved();await edit();
 assert.equal(await contact().inputValue(),'+7 999 222 33 44');
 assert.match(await page.locator('.et-secondary-contact').innerText(),/secondary@example.com/);
 await contact().fill('+7 999 333 44 55');await saveEdit();
 assert.equal(posts.at(-1).email,'secondary@example.com');assert.equal(posts.at(-1).phone,'+7 999 333 44 55');
 // User-selected replacement email is explicit in review and old phone is removed.
 await edit();await contact().fill('final@example.com');await saveEdit();
 assert.equal(posts.at(-1).phone,'');assert.equal(posts.at(-1).email,'final@example.com');
 assert.match(await page.locator('.et-review').innerText(),/final@example.com/);
 assert.doesNotMatch(await page.locator('.et-review').innerText(),/secondary@example.com/);
 await page.setViewportSize({width:320,height:760});await edit();
 assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth),false);
 assert.equal(await page.locator('dialog').evaluate(el=>el.scrollWidth>el.clientWidth),false);
 for(const body of posts)assert.equal(Object.hasOwn(body,'contact'),false,'UI-only contact must never enter strict API payload');
 if(realAPI){
  const id=await page.evaluate(()=>localStorage.getItem('energytool-session'));
  const stored=await(await page.request.get(base+'/api/v1/sessions/'+id)).json();
  assert.equal(stored.application.phone,'');assert.equal(stored.application.email,'final@example.com');
 }
 assert.deepEqual(errors,[]);
 console.log((realAPI?'REAL API ':'MOCK API ')+'PASS: email-only seed/save/reload/export, invalid addresses, phone↔email replacement, separately retained contact disclosure, mobile input/layout.');
}finally{await browser.close()}})().catch(e=>{console.error(e);process.exit(1)});
