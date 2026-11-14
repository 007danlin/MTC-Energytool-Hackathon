const assert=require('node:assert/strict'),fs=require('node:fs');const {chromium}=require(process.env.PLAYWRIGHT_MODULE||'playwright');
const base=process.env.WEB_TEST_URL||'http://127.0.0.1:8783';
(async()=>{const browser=await chromium.launch({headless:true});try{
 const session=JSON.parse(fs.readFileSync('reports/release-validation/benchmark-final/case-06.json')).session_id;
 const headers={'X-Operator-ID':'demo-coordinator','X-Operator-Role':'coordinator','X-Operator-Token':'local-demo-operator'};
 const data=await(await fetch(base+'/api/v1/operator/expert-requests',{headers})).json();const request=data.requests.find(r=>r.session_id===session);assert.ok(request);
 const page=await browser.newPage({viewport:{width:1440,height:1000}}),errors=[];page.on('pageerror',e=>errors.push(e.message));await page.goto(base+'/specialist.html');
 async function login(actor,role){await page.locator('#access').evaluate(e=>e.open=true);await page.locator('[name=actor]').fill(actor);await page.locator('[name=role]').selectOption(role);await page.locator('[name=token]').fill('local-demo-operator');await page.getByRole('button',{name:'Подключиться',exact:true}).click();await page.waitForFunction(()=>!document.querySelector('#access').open);await page.locator(`[data-id="${request.id}"]`).click()}
 await login('demo-coordinator','coordinator');await page.locator('#assign [name=assignee]').fill('demo-expert');await page.getByRole('button',{name:'Назначить',exact:true}).click();await page.waitForFunction(()=>document.querySelector('#detail').innerText.includes('demo-expert'));
 await login('demo-expert','specialist');await page.locator('#reply [name=body]').fill('Это проверка демонстрационного сценария. Совместимость с Demo-Unknown-9000 не подтверждена; для предметного разбора потребуется документация системы.');await page.getByRole('button',{name:'Сохранить и передать в диалог'}).click();await page.waitForFunction(()=>document.querySelector('#detail').innerText.includes('Доставлен в диалог'));
 await page.screenshot({path:'reports/release-validation/screens/expert-reply.png'});
 await page.goto(base+'/consultation.html');await page.evaluate(id=>{localStorage.setItem('energytool-session',id);localStorage.setItem('energytool-session-ids',JSON.stringify([id]))},session);await page.reload();await page.getByText('Специалист EnergyTool',{exact:true}).waitFor();assert.deepEqual(errors,[]);
 console.log('Real knowledge_gap → assignment → specialist reply → client history: OK');
}finally{await browser.close()}})().catch(e=>{console.error(e);process.exitCode=1});
