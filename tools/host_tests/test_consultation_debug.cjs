// Isolated browser regression: per-answer provenance, timing, archived metadata and escaping.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const {chromium} = require(process.env.PLAYWRIGHT_MODULE || 'playwright');
const base = process.env.WEB_TEST_URL || 'http://127.0.0.1:8768';
const shots = process.env.WEB_TEST_SHOTS;

(async () => {
  const browser = await chromium.launch({headless: true});
  try {
    const page = await browser.newPage({viewport: {width: 1440, height: 960}});
    const errors = [];
    page.on('pageerror', error => errors.push(error.message));
    const quote = 'Исходная цитата <img src=x onerror="window.injected=true">';
    const longID = '20-products/' + 'длинное-имя-'.repeat(25) + '.md#section-1';
    const first = {
      status: 'answered', elapsed_ms: 1250,
      sources: [{document_id: 'Первый документ', chunk_id: 'section-1', source_id: 'first.md#section-1', quote}],
      debug: {retrieved_sources: ['first.md#section-1', longID, '<script>window.injected=true</script>'], ml_elapsed_ms: 1000, repairs: 1},
    };
    const failure = {status: 'technical_error', elapsed_ms: 3456, sources: [], debug: {error_code: 'consultation_unavailable', backend_elapsed_ms: 3456}};
    const archiveMeta = {status: 'clarification', elapsed_ms: 9876, sources: [], debug: {retrieved_sources: ['archive.md#s1'], ml_elapsed_ms: 9000}};
    const sessions = {
      current: {id: 'current', status: 'active', lead: {fields: {}}, updated_at: '2026-11-13T09:00:00Z', messages: [
        {role: 'user', content: 'Первый вопрос'}, {role: 'assistant', content: 'Первый ответ', response: first},
        {role: 'user', content: 'Второй вопрос'}, {role: 'assistant', content: 'Сбой', response: failure},
      ], last_result: failure},
      archived: {id: 'archived', status: 'closed', lead: {fields: {}}, updated_at: '2026-11-13T08:00:00Z', messages: [
        {role: 'user', content: 'Архивный вопрос'}, {role: 'assistant', content: 'Архивный ответ', response: archiveMeta},
      ], last_result: first}, // Deliberately conflicting: response metadata must win.
      legacy: {id: 'legacy', status: 'closed', lead: {fields: {}}, updated_at: '2026-11-13T07:00:00Z', messages: [
        {role: 'user', content: 'Старый вопрос'}, {role: 'assistant', content: 'Старый ответ'},
      ], last_result: {status: 'answered', elapsed_ms: -1, sources: []}},
    };
    for (const id of ['compatible', 'conflict', 'conflictText']) {
      sessions[id] = {id, status:'closed', lead:{fields:{}}, updated_at:'2026-11-13T06:00:00Z', messages:[
        {role:'user', content:'Проверка старых метаданных: ' + id},
        {role:'assistant', content:'Сохранённый ответ', response:{status:'answered', elapsed_ms:1500, sources:[]}},
      ], last_result:{answer:id === 'conflictText' ? 'Другой ответ' : 'Сохранённый ответ',
        status:id === 'conflict' ? 'clarification' : 'answered', elapsed_ms:9999, sources:first.sources,
        debug:{retrieved_sources:['legacy-context.md#s1'], repairs:1}}};
    }
    await page.addInitScript(() => {
      localStorage.setItem('energytool-session', 'current');
      localStorage.setItem('energytool-session-ids', JSON.stringify(['current', 'archived', 'legacy', 'compatible', 'conflict', 'conflictText']));
    });
    await page.route('**/api/v1/**', async route => {
      const path = new URL(route.request().url()).pathname;
      const value = path.endsWith('/sessions') ? {sessions: Object.values(sessions)} : sessions[path.split('/').at(-1)];
      assert.ok(value, 'unexpected API request: ' + path);
      await route.fulfill({json: value});
    });
    const enableDebug = async () => {
      await page.getByRole('button', {name: 'Меню', exact: true}).click();
      await page.getByRole('button', {name: 'Включить режим отладки', exact: true}).click();
    };
    const close = () => page.getByRole('button', {name: 'Закрыть', exact: true}).click();
    const history = async () => {
      await page.getByRole('button', {name: 'Меню', exact: true}).click();
      await page.locator('dialog').getByRole('button', {name: 'История диалогов', exact: true}).click();
    };
    await page.goto(base + '/consultation.html');
    await page.waitForFunction(() => !document.querySelector('#et-question').disabled);
    assert.equal(await page.locator('[data-source-message]').count(), 0);
    assert.doesNotMatch(await page.locator('.et-messages').innerText(), /first\.md|archive\.md/);
    await enableDebug();
    await page.locator('[data-source-message="1"]').click();
    assert.equal(await page.locator('.et-source-time').innerText(), '1,3 с');
    assert.match(await page.locator('dialog').innerText(), /Обработка внутри ML-сервиса: 1 с/);
    assert.match(await page.locator('dialog').innerText(), /Повторов после проверки формата и цитат: 1/);
    assert.equal(await page.locator('[data-fragment]').count(), 1);
    await page.locator('.et-retrieved summary').click();
    assert.equal(await page.locator('.et-retrieved li').count(), 3);
    assert.match(await page.locator('.et-retrieved').innerText(), /не равен использованным цитатам/);
    assert.equal(await page.locator('.et-retrieved script').count(), 0);
    if (shots) { fs.mkdirSync(shots, {recursive: true}); await page.screenshot({path: shots + '/debug-desktop.png'}); }
    await page.locator('[data-fragment="0"]').click();
    assert.equal(await page.locator('.et-source-quote').innerText(), quote);
    assert.equal(await page.locator('.et-source-quote img').count(), 0);
    await page.getByRole('button', {name: 'Назад к источникам', exact: true}).click();
    await page.setViewportSize({width: 320, height: 760});
    await page.locator('.et-retrieved summary').click();
    assert.equal(await page.locator('dialog').evaluate(el => el.scrollWidth > el.clientWidth), false);
    if (shots) await page.screenshot({path: shots + '/debug-mobile.png'});
    await close();
    await page.setViewportSize({width: 1440, height: 960});
    await page.locator('[data-source-message="3"]').click();
    assert.equal(await page.locator('.et-source-time').innerText(), '3,5 с');
    assert.match(await page.locator('dialog').innerText(), /consultation_unavailable/);
    assert.match(await page.locator('dialog').innerText(), /Данные о поисковом контексте этого ответа не сохранены/);
    assert.equal(await page.locator('[data-fragment]').count(), 0);
    await close();
    await history();
    await page.locator('[data-session="archived"]').click();
    await page.locator('[data-source-context="archive"]').click();
    assert.equal(await page.locator('.et-source-time').innerText(), '9,9 с');
    assert.match(await page.locator('dialog').innerText(), /Фрагментов в контексте: 1/);
    assert.equal(await page.locator('[data-fragment]').count(), 0);
    await page.getByRole('button', {name: 'Назад к диалогу', exact: true}).click();
    assert.match(await page.locator('dialog').innerText(), /Архивный ответ/);
    assert.equal(await page.evaluate(() => localStorage.getItem('energytool-session')), 'current');
    await page.getByRole('button', {name: 'Назад к истории', exact: true}).click();
    await page.locator('[data-session="legacy"]').click();
    await page.locator('[data-source-context="archive"]').click();
    assert.equal(await page.locator('.et-source-time').innerText(), 'Не указано');
    assert.match(await page.locator('dialog').innerText(), /Данные о поисковом контексте этого ответа не сохранены/);
    await close();
    for (const id of ['compatible', 'conflict', 'conflictText']) {
      await history();
      await page.locator(`[data-session="${id}"]`).click();
      await page.locator('[data-source-context="archive"]').click();
      assert.equal(await page.locator('.et-source-time').innerText(), '1,5 с', 'must retain message timing');
      assert.equal(await page.locator('[data-fragment]').count(), 0, 'must retain message citations');
      if (id === 'compatible') {
        assert.match(await page.locator('dialog').innerText(), /Фрагментов в контексте: 1/);
        assert.match(await page.locator('dialog').innerText(), /Повторов после проверки формата и цитат: 1/);
      } else {
        assert.match(await page.locator('dialog').innerText(), /Данные о поисковом контексте этого ответа не сохранены/);
      }
      await close();
    }
    assert.equal(await page.evaluate(() => window.injected), undefined);
    assert.deepEqual(errors, []);
    console.log('PASS: actual per-answer metadata, error timing, retrieved versus cited sources, archived and legacy responses, safe text, mobile debug layout.');
  } finally {
    await browser.close();
  }
})().catch(error => { console.error(error); process.exit(1); });
