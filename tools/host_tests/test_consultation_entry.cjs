const assert=require('node:assert/strict'),fs=require('node:fs');const {chromium}=require(process.env.PLAYWRIGHT_MODULE||'playwright');
const shots=process.env.WEB_TEST_SHOTS||'/tmp/mts-design-review';fs.mkdirSync(shots,{recursive:true});
const base=process.env.WEB_TEST_URL||'http://127.0.0.1:8768';
(async()=>{const b=await chromium.launch({headless:true});try{
 const original=await b.newPage({viewport:{width:1440,height:960}});await original.route('**/chat.js',r=>r.abort());await original.goto(base);await original.evaluate(()=>document.fonts.ready);const before=await original.getByRole('button',{name:'Войти в кабинет',exact:true}).first().boundingBox();
 const p=await b.newPage({viewport:{width:1440,height:960}});await p.goto(base);await p.getByRole('link',{name:'Онлайн-консультация',exact:true}).first().waitFor();await p.evaluate(()=>document.fonts.ready);
 await p.waitForFunction(x=>{const n=[...document.querySelectorAll('button')].find(e=>e.textContent.trim()==='Войти в кабинет'&&e.getBoundingClientRect().width>0);return Math.abs(n.getBoundingClientRect().x-x)<1},before.x);
 const after=await p.getByRole('button',{name:'Войти в кабинет',exact:true}).first().boundingBox();assert.ok(Math.abs(before.x-after.x)<1);assert.ok(Math.abs(before.y-after.y)<1);
 assert.equal(await p.getByRole('button',{name:'Войти в кабинет',exact:true}).first().isDisabled(),true);
 assert.equal(await p.getByRole('button',{name:'Заказать консультацию',exact:true}).first().isDisabled(),true);
 assert.match(await p.locator('#local-preview-notice').innerText(),/Демо EnergyTool/);
 const link=p.getByRole('link',{name:'Онлайн-консультация',exact:true}).first(),r=await link.boundingBox(),badge=await link.locator('.et-new-badge').boundingBox();assert.ok(badge.x>r.x+r.width/2&&badge.y<r.y+10&&badge.x+badge.width<=r.x+r.width);
 await p.screenshot({path:shots+'/site-desktop.png'});await p.setViewportSize({width:390,height:844});await p.waitForFunction(()=>document.documentElement.scrollWidth===innerWidth);await p.screenshot({path:shots+'/site-mobile.png'});
 console.log('PASS: login keeps original x/y; new badge in top right; mobile page has no horizontal scroll.');
}finally{await b.close()}})().catch(e=>{console.error(e);process.exit(1)});
