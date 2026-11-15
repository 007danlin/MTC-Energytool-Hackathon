// Deterministic navigation checks: leaving a conversation must not end it.
const assert = require('node:assert/strict');
const {chromium} = require(process.env.PLAYWRIGHT_MODULE || 'playwright');
const base = process.env.WEB_TEST_URL || 'http://127.0.0.1:8776';

(async () => {
  const browser = await chromium.launch({headless:true});
  try {
    const page = await browser.newPage({viewport:{width:1366,height:900}});
    const records = new Map(), errors = [], mutations = [];
    let sequence = 0;
    const copy = value => JSON.parse(JSON.stringify(value));
    const newSession = () => {
      const session = {id:'navigation-'+(++sequence),status:'active',messages:[],lead:{fields:{}},updated_at:new Date().toISOString()};
      records.set(session.id,session); return session;
    };
    page.on('pageerror', error => errors.push(error.message));
    await page.route('**/api/v1/**', async route => {
      const request = route.request(), path = new URL(request.url()).pathname.replace('/api/v1','');
      const parts = path.split('/').filter(Boolean), method = request.method();
      let response;
      if (parts.length === 1) response = method === 'GET' ? {sessions:[...records.values()]} : newSession();
      else {
        const session = records.get(parts[1]);
        assert.ok(session, 'known fixture session '+parts[1]);
        if (method !== 'GET') {
          mutations.push({id:session.id,action:parts[2]});
          if (parts[2] === 'messages') {
            const {content} = request.postDataJSON();
            const result = {status:'answered',answer:'Проверьте показания за последний месяц.',sources:[],summary:{task:[content]}};
            session.messages.push({role:'user',content},{role:'assistant',content:result.answer,response:result});
            session.last_result=result;
          } else if (parts[2] === 'resume') session.status='active';
          else if (parts[2] === 'close') session.status='closed';
          else if (parts[2] === 'application') session.application={...request.postDataJSON(),id:'app-'+session.id,number:'123456',saved_at:new Date().toISOString()};
        }
        response=session;
      }
      await route.fulfill({json:copy(response)});
    });
    const composer=page.locator('#et-question');
    const activeID=()=>page.evaluate(()=>localStorage.getItem('energytool-session'));
    const idle=()=>page.waitForFunction(()=>{
      const input=document.querySelector('#et-question');
      return input && !input.disabled && document.querySelector('#energytool-chat').dataset.screen!=='waiting';
    });
    const action=(name,scope=page)=>scope.locator('[data-action="'+name+'"]');
    const menu=async()=>{await action('menu').click();};
    const contacts=async()=>{await menu();await action('contacts',page.locator('dialog')).click();};
    const resume=async id=>{
      await page.locator('.et-header [data-action="history"]').click();
      await page.locator('[data-session="'+id+'"]').click();
      await action('resume',page.locator('dialog')).click();
      await idle();
      assert.equal(await activeID(),id);
    };
    await page.goto(base+'/consultation.html'); await idle();
    const first=await activeID();
    await composer.fill('Нужно автоматизировать учёт в цехе');
    await page.getByRole('button',{name:'Отправить',exact:true}).click(); await idle();
    await composer.fill('Неотправленное уточнение первого диалога');
    await page.locator('.et-header [data-action="new"]').click();
    await action('confirm-new',page.locator('dialog')).click(); await idle();
    const second=await activeID();
    assert.notEqual(first,second);
    assert.equal(records.get(first).status,'active','new conversation keeps the old one resumable');
    await composer.fill('Черновик второго диалога');
    await resume(first);
    assert.equal(await composer.inputValue(),'Неотправленное уточнение первого диалога');
    await resume(second);
    assert.equal(await composer.inputValue(),'Черновик второго диалога','a draft-only conversation can be resumed from history');
    await resume(first);
    await page.reload(); await idle();
    assert.equal(await activeID(),first);
    assert.equal(await composer.inputValue(),'Неотправленное уточнение первого диалога');

    await contacts();
    await page.locator('.et-contact-form [name="contact"]').fill('audit@example.test');
    await page.locator('.et-contact-form [name="full_name"]').fill('Тестовый клиент');
    await page.reload();
    await page.locator('.et-contact-form').waitFor();
    assert.equal(await page.locator('.et-contact-form [name="contact"]').inputValue(),'audit@example.test');
    await page.getByRole('button',{name:'Вернуться к консультации',exact:true}).click(); await idle();
    assert.equal(await composer.inputValue(),'Неотправленное уточнение первого диалога');
    await contacts();
    assert.equal(await page.locator('.et-contact-form [name="contact"]').inputValue(),'audit@example.test');
    await page.getByRole('button',{name:'Проверить заявку',exact:true}).click();
    await page.getByRole('heading',{name:'Проверьте заявку',exact:true}).waitFor();
    await page.reload();
    await page.getByRole('heading',{name:'Проверьте заявку',exact:true}).waitFor();
    assert.match(await page.locator('.et-review').innerText(),/audit@example.test/);
    await page.getByRole('button',{name:'Вернуться к консультации',exact:true}).click(); await idle();
    await contacts();
    await page.getByRole('button',{name:'Продолжить без контакта',exact:true}).click();
    await page.getByRole('button',{name:'Продолжить консультацию',exact:true}).click(); await idle();
    await composer.fill('Продолжаем после отказа от контакта');
    await page.getByRole('button',{name:'Отправить',exact:true}).click(); await idle();
    assert.equal(records.get(first).messages.filter(m=>m.role==='user').length,2);

    await contacts();
    await page.getByRole('button',{name:'Проверить заявку',exact:true}).click();
    await page.getByRole('button',{name:'Сформировать заявку',exact:true}).click();
    await page.getByRole('heading',{name:'Заявка сформирована',exact:true}).waitFor();
    await page.getByRole('button',{name:'Продолжить консультацию',exact:true}).click(); await idle();
    await menu();await page.getByRole('button',{name:'Вернуться на сайт',exact:true}).click();
    const leave=action('confirm-close',page.locator('dialog'));
    if(await leave.count())await leave.click();
    await page.waitForURL(url=>url.pathname!=='/consultation.html');
    assert.equal(records.get(first).status,'active','leaving the site preserves active consultation');
    await page.goto(base+'/consultation.html'); await idle();
    assert.equal(await activeID(),first,'reopening returns to the same conversation');
    assert.equal(mutations.filter(m=>m.action==='close').length,0);
    records.get(first).status='closed';
    await page.reload();
    await page.getByRole('heading',{name:'Диалог сохранён',exact:true}).waitFor();
    await action('resume',page.locator('.et-flow')).click();await idle();
    assert.equal(records.get(first).status,'active','previously closed conversations can be reopened');
    assert.equal(mutations.filter(m=>m.action==='resume').length,1);
    await page.setViewportSize({width:390,height:844});
    await menu();await action('history',page.locator('dialog')).click();
    const draftCard=page.locator('.et-modal-body .et-card').filter({has:page.locator('[data-session="'+second+'"]')});
    assert.match(await draftCard.innerText(),/Черновик второго диалога/);
    assert.match(await draftCard.innerText(),/ещё не отправлен/);
    await page.locator('[data-session="'+second+'"]').click();
    await action('resume',page.locator('dialog')).click();await idle();
    assert.equal(await composer.inputValue(),'Черновик второго диалога');
    assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth),false);
    assert.deepEqual(errors,[]);
    console.log('PASS: new/history resume, per-session draft, reload recovery for contact form, review/decline return, application save, site return, closed-session recovery and mobile history.');
  } finally {await browser.close();}
})().catch(error=>{console.error(error);process.exitCode=1;});
