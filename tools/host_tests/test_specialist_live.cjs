// Exercises the real local demo stack, with synthetic records only.
const assert=require('node:assert/strict'),fs=require('node:fs');
const {chromium}=require(process.env.PLAYWRIGHT_MODULE||'playwright');
const base=process.env.WEB_TEST_URL||'http://127.0.0.1:8782';
if(!/^http:\/\/(127\.0\.0\.1|localhost):/.test(base))throw Error('Local demo stack required');
(async()=>{const browser=await chromium.launch({headless:true});try{
 const page=await browser.newPage({viewport:{width:1440,height:1000}}),errors=[];page.on('pageerror',e=>errors.push(e.message));
 const out='reports/release-validation/screens';fs.mkdirSync(out,{recursive:true});
 await page.goto(base+'/specialist.html');
 async function login(actor,role){await page.locator('#access').evaluate(e=>e.open=true);await page.locator('[name=actor]').fill(actor);await page.locator('[name=role]').selectOption(role);await page.locator('[name=token]').fill(process.env.OPERATOR_TOKEN||'local-demo-operator');await page.getByRole('button',{name:'Подключиться',exact:true}).click();await page.waitForFunction(()=>!document.querySelector('#access').open);}
 await login('demo-author','specialist');await page.locator('#new-draft').click();
 const fields={title:'Проверка публикации демо',generalized_question:'Как проверить цикл редакторской публикации?',answer:'Сначала создают черновик, затем его проверяет другой редактор.',applicability:'Только техническая проверка демонстрационного стенда.',basis:'Сценарий приёмки интерфейса.'};
 for(const [k,v]of Object.entries(fields))await page.locator('#draft [name='+k+']').fill(v);
 // This non-test record is transiently published only in this isolated demo volume,
 // then revoked. It must never be copied to production or used as domain knowledge.
 const created=page.waitForResponse(r=>r.url().endsWith('/operator/knowledge')&&r.request().method()==='POST');
 await page.getByRole('button',{name:'Сохранить черновик',exact:true}).click();const response=await created;assert.equal(response.status(),201);let record=await response.json();
 await login('demo-reviewer','reviewer');await page.locator('#knowledge-tab').click();await page.locator(`[data-id="${record.id}"]`).click();
 await page.locator('#approve input').first().waitFor();for(const cb of await page.locator('#approve input').all())await cb.check();
 let pending=page.waitForResponse(r=>r.url().endsWith('/approve'));await page.getByRole('button',{name:'Одобрить и опубликовать'}).click();let approved=await pending;assert.equal(approved.status(),200);record=await approved.json();assert.equal(record.revisions.at(-1).publication_status,'approved');assert.equal(record.revisions.at(-1).runtime_status,'active');
 await page.waitForFunction(()=>document.querySelector('#detail').innerText.includes('В поиске'));await page.screenshot({path:out+'/specialist-desktop.png'});
 await page.setViewportSize({width:390,height:844});await page.screenshot({path:out+'/specialist-mobile.png',fullPage:true});assert.ok(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1));
 await page.locator('#revoke [name=reason]').fill('Проверка завершена; тестовая запись удалена из поиска.');pending=page.waitForResponse(r=>r.url().endsWith('/revoke'));await page.getByRole('button',{name:'Отозвать из поиска',exact:true}).click();const revoked=await pending;assert.equal(revoked.status(),200);record=await revoked.json();assert.equal(record.revisions.at(-1).runtime_status,'inactive');
 assert.deepEqual(errors,[]);fs.writeFileSync('reports/release-validation/specialist-ui.json',JSON.stringify({passed:true,record_id:record.id,publication:record.revisions.at(-1).publication_status,runtime:record.revisions.at(-1).runtime_status},null,2));console.log('Specialist UI: create, review, publish, revoke, mobile OK');
}finally{await browser.close()}})().catch(e=>{console.error(e);process.exitCode=1});
