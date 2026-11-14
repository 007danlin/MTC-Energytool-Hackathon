// UI fixtures only: this suite does not evaluate or call the language model.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const {chromium} = require(process.env.PLAYWRIGHT_MODULE || 'playwright');
const base = process.env.WEB_TEST_URL || 'http://127.0.0.1:8776';
const shots = process.env.WEB_TEST_SHOTS || '/private/tmp/energytool-polish';

(async () => {
  const browser = await chromium.launch({headless:true});
  try {
    fs.mkdirSync(shots,{recursive:true});
    const page = await browser.newPage({viewport:{width:1440,height:960}});
    const errors=[];page.on('pageerror',e=>errors.push(e.message));
    const sessions={};let count=0,posts=0,next=null,release=null,hold=false;
    const answer='Начните со сравнения счетов и показаний за сопоставимые периоды. Уточните, менялся ли режим работы склада и состав оборудования. Затем можно обсудить, нужен ли более подробный учёт.';
    const summary={object:[{value:'Склад и офисная часть'}],task:[{value:'Понять, почему выросли счета за электроэнергию'}],parameters:[{value:'Рост начался с сентября'},{value:'Виден только общий счёт'},{value:'Показания снимаем вручную раз в месяц'},{value:'Режим работы не менялся'},{value:'Два арендатора'},{value:'Площадь 500 м²'},{value:'Учёт ведём в таблице'}],manager_questions:['Менялся ли состав оборудования?','Какая сумма была в сентябре прошлого года?','Были ли изменения тарифа?','Сохранились ли показания за прошлый год?']};
    await page.route('**/api/v1/**',async route=>{
      const req=route.request(),parts=new URL(req.url()).pathname.split('/').filter(Boolean);let value;
      if(parts.length===3 && req.method()==='POST'){
        const id='polish-'+(++count);value=sessions[id]={id,status:'active',messages:[],lead:{fields:{}},updated_at:new Date().toISOString()};
      }else if(parts.length===3)value={sessions:Object.values(sessions)};
      else{
        const session=sessions[parts[3]];assert.ok(session);
        if(parts[4]==='messages'){
          posts++;session.messages.push({role:'user',content:req.postDataJSON().content});
          if(hold)await new Promise(resolve=>{release=resolve;});
          const response={status:'answered',answer,summary:structuredClone(summary),sources:[],...next};next=null;
          session.last_result=response;session.messages.push({role:'assistant',content:response.answer,response});value=response;
        }else if(parts[4]==='application'){session.application={id:'ET-polish',...req.postDataJSON(),saved_at:new Date().toISOString()};value=session;}
        else if(parts[4]==='close'){session.status='closed';value=session;}
        else value=session;
      }
      await route.fulfill({json:value});
    });
    const ready=()=>page.waitForFunction(()=>document.querySelector('#energytool-chat').dataset.screen!=='waiting' && !document.querySelector('#et-question').disabled);
    const snap=async name=>{await page.evaluate(()=>document.fonts.ready);await page.screenshot({path:`${shots}/${name}.png`});};
    const send=async text=>{await page.locator('#et-question').fill(text);await page.locator('.et-send').click();await ready();};
    const close=()=>page.locator('dialog').getByRole('button',{name:'Закрыть',exact:true}).click();
    await page.goto(base+'/consultation.html?start=new');await ready();
    await page.getByRole('button',{name:'Снизить расходы',exact:true}).click();
    assert.equal(posts,0,'choosing a scenario must never submit it');
    assert.equal(await page.locator('[data-prompt="cost"]').getAttribute('aria-pressed'),'true');
    assert.match(await page.locator('#et-question').inputValue(),/выросли счета/);
    await snap('start-1440');
    for(const width of [320,390,768,1024,1280,1440]){
      await page.setViewportSize({width,height:844});
      assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth),false,'welcome overflow '+width);
      assert.equal(await page.locator('.et-suggestions').evaluate(e=>e.scrollWidth>e.clientWidth+1),false,'scenarios overflow '+width);
      if(width===390){await page.waitForFunction(()=>document.querySelector('#et-question').clientHeight>=48);await snap('start-390');}
    }
    await page.setViewportSize({width:1440,height:960});
    hold=true;await page.locator('.et-send').click();await page.locator('.et-pending').waitFor();
    assert.equal(await page.locator('.et-plan-sidebar').isVisible(),false,'no fabricated plan while awaiting first response');
    await page.locator('#et-question').fill('Черновик следующего вопроса');
    await snap('waiting-1440');hold=false;release();await ready();
    assert.equal(await page.locator('#et-question').inputValue(),'Черновик следующего вопроса');
    const facts=page.locator('.et-sidebar [data-task-key="parameters"]');
    assert.equal(await facts.locator('li').count(),2);
    await facts.getByRole('button',{name:/Показать ещё 5/}).click();
    assert.equal(await facts.locator('li').count(),7);
    assert.equal(await facts.getByRole('button',{name:/Свернуть/}).getAttribute('aria-expanded'),'true');
    await facts.getByRole('button',{name:/Свернуть/}).click();
    await page.locator('.et-sidebar [data-action="task-all"]').click();
    assert.equal(await page.locator('dialog [data-task-key="parameters"] li').count(),7);
    await close();
    const plan=page.locator('.et-plan-sidebar');
    assert.equal(await plan.locator('[data-plan-step]').count(),3);
    assert.equal(await plan.locator('input:checked').count(),0);
    await plan.locator('[data-plan-step="0"]').check();
    await page.reload();await ready();
    assert.equal(await plan.locator('[data-plan-step="0"]').isChecked(),true,'plan progress survives reload');
    await plan.getByRole('button',{name:/Посмотреть ответ/}).click();
    assert.match(await page.locator('dialog').innerText(),/Начните со сравнения/);await close();
    for(const width of [320,390,768,1024,1280,1440,1920]){
      await page.setViewportSize({width,height:960});
      assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth),false,'conversation overflow '+width);
      assert.equal(await page.locator('.et-workspace').evaluate(e=>e.scrollWidth>e.clientWidth+1),false,'workspace overflow '+width);
      if(width>=1280){
        assert.equal(await plan.isVisible(),true);
        const [chatBox,planBox]=await Promise.all([page.locator('.et-workspace').boundingBox(),plan.boundingBox()]);
        assert.ok(chatBox.x+chatBox.width<=planBox.x,'chat must not overlap plan');
        await snap('answer-'+width);
      }else{
        assert.equal(await plan.isVisible(),false);
        await page.locator('.et-plan-toggle').click();
        assert.equal(await page.locator('dialog [data-plan-step="0"]').isChecked(),true);
        await page.locator('dialog [data-plan-step="1"]').check();
        assert.equal(await page.locator('dialog').evaluate(e=>e.scrollWidth>e.clientWidth+1),false,'plan drawer overflow');
        if(width===390)await snap('plan-390');
        await close();
      }
    }
    await page.setViewportSize({width:1440,height:960});
    await page.getByRole('button',{name:'Подготовить заявку',exact:true}).click();
    const [contactBox,nameBox,companyBox]=await Promise.all(['contact','full_name','company'].map(n=>page.locator(`.et-contact-form [name="${n}"]`).boundingBox()));
    assert.ok(contactBox.y<nameBox.y && nameBox.y===companyBox.y,'contact first; optional fields share second row');
    await page.getByRole('button',{name:'Посмотреть',exact:true}).click();
    assert.match(await page.locator('dialog').innerText(),/Рост начался с сентября/);await close();
    await page.getByLabel('Телефон или email',{exact:true}).fill('ui-test@example.com');
    assert.equal(await page.locator('.et-callback').isVisible(),false);
    await snap('contacts-1440');
    await page.getByRole('button',{name:'Проверить заявку',exact:true}).click();
    await page.getByRole('button',{name:'Сформировать заявку',exact:true}).click();
    await page.getByRole('heading',{name:'Заявка сформирована',exact:true}).waitFor();
    assert.equal(posts,1,'plan, summary and contacts never send chat messages');
    await page.goto(base+'/consultation.html?start=new');await ready();
    next={status:'clarification',answer:'Есть ли показания за прошлый год?',summary:{}};
    await send('Проверка нового диалога');
    assert.equal(await plan.isVisible(),false,'no steps copied from another session or a question');
    next={status:'clarification',answer:'Уточните, есть ли у вас присоединённая мощность — это поможет подобрать решение.',summary:{state_version:2,action_plan:[]}};
    await send('Проверка уточнения с точкой вместо знака вопроса');
    assert.equal(await plan.isVisible(),false,'a direct clarifying request is not an action plan');
    next={status:'clarification',answer:'Вы снимаете показания вручную и видите только общую сумму. Что ещё нужно уточнить?',summary:{state_version:2,parameters:[{value:'видим только общую сумму'}],action_plan:[]}};
    await send('Дополнение о показаниях');
    assert.equal(await page.locator('[data-reply]').count(),0,'acknowledged facts must not create repeated quick questions');
    next={answer:'Сравните счета. Проверьте <img src=x onerror="window.injected=true">.',summary:structuredClone(summary)};
    await send('Нужны шаги');
    assert.equal(await plan.locator('input:checked').count(),0,'new session has independent progress');
    assert.equal(await plan.locator('img').count(),0,'plan treats model output as plain text');
    assert.equal(await page.evaluate(()=>window.injected),undefined);
    // Regression from an actual Qwen reply: inline numbering and infinitives.
    const inline='Чтобы выявить причину роста счетов, рекомендую следующий план: 1) проанализировать показания за последние три месяца; 2) проверить, нет ли аномалий в работе общего счётчика; 3) рассмотреть возможность подключения к облачной платформе учёта. Это поможет контролировать потребление.';
    next={answer:inline,summary:{}};
    await send('Составь план из трёх действий.');
    assert.equal(await plan.locator('[data-plan-step]').count(),3,'legacy inline real-model plan is parsed');
    await page.reload();await ready();
    assert.equal(await plan.locator('[data-plan-step]').count(),3,'inline plan survives reload');
    // Authoritative v2 summary may intentionally clear questions; never replace
    // that with an entire assistant answer or resurrect an old task editor value.
    next={status:'clarification',answer:'Сравните счета за сопоставимые периоды.',summary:{state_version:2,object:[{value:'Склад',message_index:0}],task:[{value:'Снизить расходы',message_index:0}],parameters:[{value:'Расходы 30000 рублей в год',message_index:0},{value:'Есть приборы учёта',message_index:0},{value:'Показания снимаем вручную раз в месяц',message_index:0}],manager_questions:[],action_plan:['Сравните счета за сопоставимые периоды.']}};
    await send('Дополню данные.');
    assert.match(await page.locator('.et-sidebar [data-task-key="questions"]').innerText(),/Открытых вопросов пока нет/);
    assert.equal(await plan.locator('[data-plan-step]').count(),1,'actionable clarification can have a plan');
    await page.locator('.et-sidebar [data-action="task-all"]').click();
    assert.equal(await page.locator('dialog [data-task-key="parameters"] li').count(),3);
    await close();
    await page.emulateMedia({reducedMotion:'reduce'});
    assert.equal(await page.locator('.et-scenario').first().evaluate(e=>getComputedStyle(e).transitionDuration),'0s');
    assert.deepEqual(errors,[]);
    console.log('PASS: scenario selection, 7 viewports, collapsed/full facts, grounded plan, checkboxes/reload/session isolation, safe model text, source answer, pending drafts, contact order/preview/save, reduced motion. API mocked.');
  }finally{await browser.close();}
})().catch(error=>{console.error(error);process.exit(1);});
