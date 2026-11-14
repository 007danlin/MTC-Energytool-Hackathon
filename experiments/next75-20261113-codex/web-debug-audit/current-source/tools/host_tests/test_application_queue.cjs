const assert = require('node:assert/strict');
const { spawn } = require('node:child_process');
const { once } = require('node:events');
const fs = require('node:fs');
const http = require('node:http');
const path = require('node:path');
const { chromium } = require(process.env.PLAYWRIGHT_MODULE || 'playwright');

const root = path.resolve(__dirname, '../..');
const field = (value, status = 'confirmed') => ({ value, status });
const timestamp = '2026-11-13T09:00:00Z';
const record = {
  id: 'demo-application', session_id: 'demo-session', version: 1, status: 'new',
  demo: true, updated_at: timestamp, card: {
    task: field('Снизить расходы завода'),
    contact: { full_name: field('Иван Тестовый'), phone: field('+7 000 000 00 00'), company: field('ООО Тест') },
    contact_time: field('13.11.2026 в 16:00 МСК — желаемое время'),
    object: [{ ...field('Завод в Тульской области'), evidence: [{ sequence: 2 }] }],
    power: [
      { amount: '600', unit: 'кВт', state: 'actual' },
      { amount: '900', unit: 'кВт', state: 'history' },
    ],
    products: [{ name: 'Выход на оптовый рынок', status: 'assumed' }],
    unknowns: [field('Уточнить класс напряжения', 'unknown')],
    next_step: field('Позвонить и уточнить класс напряжения', 'assumed'),
  },
};
const endpoint = '/api/v1/applications/' + record.id;
const commands = [];
const responses = new Map();
let failQueue = true;
let loseResponse = false;
let rejectCommand = false;

function json(response, data, status = 200) {
  response.writeHead(status, { 'Content-Type': 'application/json' });
  response.end(JSON.stringify(data));
}

async function handle(request, response) {
  const url = new URL(request.url, 'http://localhost');
  if (url.pathname === '/api/v1/applications') {
    await new Promise(resolve => setTimeout(resolve, 120));
    if (failQueue) return json(response, { code: 'not_found' }, 404);
    const filter = url.searchParams.get('status');
    return json(response, { applications: filter && filter !== record.status ? [] : [{
      id: record.id, demo: record.demo, status: record.status, updated_at: timestamp,
      company: record.card.contact.company.value, task: record.card.task.value,
    }] });
  }
  if (url.pathname === '/api/v1/metrics/pilot') {
    const included = url.searchParams.get('include_demo') === '1';
    const accepted = included && record.status === 'accepted';
    return json(response, {
      includes_demo: included, sessions_with_question: included ? 1 : 0, sessions_with_application: included ? 1 : 0,
      conversion_to_application: { display: included ? '100%' : 'нет данных' },
      acceptance_rate: { display: accepted ? '100%' : 'нет данных' },
      status_counts: { [record.status]: Number(included) },
    });
  }
  if (url.pathname === '/api/v1/applications/reasons') {
    return json(response, { missing_data: 'Не хватает данных', other: 'Другое' });
  }
  if (url.pathname === '/api/v1/sessions/demo-session/messages') {
    return json(response, { messages: [
      { sequence: 1, role: 'assistant', content: 'Какой объект нужно обследовать?' },
      { sequence: 2, role: 'user', content: 'Завод в Тульской области' },
    ] });
  }
  if (url.pathname === endpoint) return json(response, record);
  if (url.pathname === endpoint + '/export') {
    if (url.searchParams.get('format') === 'json') return json(response, record.card);
    response.writeHead(200, { 'Content-Type': 'text/plain; charset=utf-8' });
    return response.end(record.card.task.value + '\n' + record.card.contact.company.value);
  }

  const isEdit = request.method === 'PATCH' && url.pathname === endpoint + '/card';
  const isTransition = request.method === 'POST' && url.pathname === endpoint + '/transitions';
  if (!isEdit && !isTransition) return json(response, { code: 'not_found' }, 404);
  let body = '';
  for await (const chunk of request) body += chunk;
  const command = JSON.parse(body);
  commands.push(command);
  if (responses.has(command.client_request_id)) {
    assert.deepEqual(command, responses.get(command.client_request_id));
    return json(response, record);
  }
  if (command.expected_version !== record.version) return json(response, { code: 'version_conflict' }, 409);
  if (rejectCommand) {
    rejectCommand = false;
    return json(response, {}, 503);
  }
  if (isEdit) {
    for (const edit of command.edits) {
      if (['contact.company','contact.phone','contact.email'].includes(edit.path)) {
        record.card.contact[edit.path.slice(8)] = field(edit.action === 'remove' ? '' : edit.value);
      }
    }
  } else {
    record.status = {
      start_review: 'in_review', accept: 'accepted', needs_info: 'needs_info', reject: 'rejected', reopen: 'in_review',
    }[command.action];
    record.reason = command.reason;
    record.comment = command.comment;
  }
  record.version++;
  responses.set(command.client_request_id, command);
  if (loseResponse) {
    loseResponse = false;
    return json(response, {}, 503);
  }
  return json(response, record);
}

async function main() {
  const server = http.createServer((request, response) => {
    handle(request, response).catch(error => {
      console.error(error);
      json(response, {}, 500);
    });
  });
  server.listen(0, '127.0.0.1');
  await once(server, 'listening');
  const preview = spawn('python3', ['-u', 'local-preview/energytool-site/serve.py'], {
    cwd: root, stdio: ['ignore', 'pipe', 'inherit'],
    env: { ...process.env, WEB_PORT: '0', BACKEND_URL: 'http://127.0.0.1:' + server.address().port },
  });
  let browser;
  try {
    const [output] = await once(preview.stdout, 'data');
    const origin = String(output).match(/http:\/\/127\.0\.0\.1:\d+/)?.[0];
    assert.ok(origin && !origin.endsWith(':0'), String(output));
    browser = await chromium.launch({ headless: true });
    const page = await browser.newPage({ viewport: { width: 1366, height: 900 } });
    const errors = [];
    page.on('pageerror', error => errors.push(error.message));
    const button = (name, parent = page) => parent.getByRole('button', { name, exact: true });
    const modal = page.getByRole('dialog');
    const card = page.locator('#application');
    const queue = page.locator('#queue-result');
    const metrics = page.locator('#metrics-result');
    const entry = page.getByRole('link', { name: /Снизить расходы завода/ });
    const verifyStatus = status => card.locator('.card-head').getByText(status, { exact: true }).waitFor();
    const screenshots = process.env.WEB_TEST_SHOTS;
    const screenshot = async name => {
      if (!screenshots) return;
      fs.mkdirSync(screenshots, { recursive: true });
      await page.screenshot({ path: path.join(screenshots, name + '.png'), fullPage: true });
    };

    await page.goto(origin + '/applications.html');
    await queue.getByText('API очереди заявок ещё не подключён.').waitFor();
    failQueue = false;
    await button('Повторить', queue).click();
    await queue.getByText('Загружаем заявки…').waitFor();
    await entry.waitFor();
    await page.getByLabel('Статус заявки', { exact: true }).selectOption('accepted');
    await queue.getByText('Заявок с этим статусом пока нет.').waitFor();
    await page.getByLabel('Статус заявки', { exact: true }).selectOption('');
    await entry.click();
    await verifyStatus('Новая');
    assert.equal(await queue.getByText(record.card.contact.phone.value, { exact: true }).count(), 0);
    await card.getByText('Демо', { exact: true }).waitFor();
    await card.getByText('Подтверждено', { exact: true }).first().waitFor();
    await card.getByText('Предположение', { exact: true }).first().waitFor();
    await card.getByText('Неизвестно', { exact: true }).first().waitFor();
    await card.getByText('Актуальное', { exact: true }).waitFor();
    await card.getByText('Прежнее', { exact: true }).waitFor();
    await card.getByText(record.card.contact_time.value, { exact: true }).waitFor();
    await button('Сообщение №2').click();
    assert.match(await modal.locator('.highlight').innerText(), /Завод в Тульской области/);
    await page.keyboard.press('Escape');
    await screenshot('application-queue-desktop');

    loseResponse = true;
    await button('Взять в работу').evaluate(element => { element.click(); element.click(); });
    await page.getByText('Не удалось подтвердить действие.', { exact: false }).waitFor();
    assert.equal(commands.length, 1, 'double click must issue one request');
    await button('Взять в работу').click();
    await verifyStatus('На разборе');
    assert.deepEqual(commands[0], commands[1], 'retry must reuse the identical command');
    assert.equal(record.version, 2);

    await button('Запросить уточнение').click();
    await modal.getByLabel('Причина').selectOption('missing_data');
    await modal.getByLabel('Комментарий').fill('Первый комментарий');
    rejectCommand = true;
    await button('Запросить уточнение', modal).click();
    await modal.getByRole('alert').waitFor();
    await modal.getByLabel('Комментарий').fill('Уточните класс напряжения');
    await button('Запросить уточнение', modal).click();
    await verifyStatus('Нужны данные');
    assert.notEqual(commands[2].client_request_id, commands[3].client_request_id);
    await card.getByText('Не хватает данных', { exact: true }).waitFor();

    await button('Редактировать').click();
    await modal.getByLabel('Компания', { exact: true }).fill('Первая попытка');
    record.version++;
    await button('Сохранить изменения', modal).click();
    await card.getByText('Заявка изменилась.', { exact: false }).waitFor();
    assert.equal(await modal.isVisible(), false);
    await button('Редактировать').click();
    await modal.getByLabel('Компания', { exact: true }).fill('ООО После правки');
    await button('Сохранить изменения', modal).click();
    await card.getByText('ООО После правки', { exact: true }).waitFor();
    assert.deepEqual(commands.at(-1).edits, [{ path: 'contact.company', action: 'set', value: 'ООО После правки' }]);

    // Existing manager editor accepts an email-only contact without demanding phone.
    await button('Редактировать').click();
    await modal.getByLabel('Телефон', {exact:true}).fill('');
    await modal.getByLabel('Email', {exact:true}).fill('manager+test@example.com');
    await button('Сохранить изменения', modal).click();
    await card.getByText('manager+test@example.com', {exact:true}).waitFor();
    assert.deepEqual(commands.at(-1).edits, [
      {path:'contact.phone',action:'remove'},
      {path:'contact.email',action:'set',value:'manager+test@example.com'},
    ]);
    await button('Редактировать').click();
    await modal.getByLabel('Email', {exact:true}).fill('');
    const beforeEmpty = commands.length;
    await button('Сохранить изменения', modal).click();
    assert.equal(commands.length, beforeEmpty, 'cannot remove the final contact');
    await modal.getByLabel('Телефон', {exact:true}).fill('+7 999 123 45 67');
    await button('Сохранить изменения', modal).click();
    await card.getByText('+7 999 123 45 67', {exact:true}).waitFor();
    assert.deepEqual(commands.at(-1).edits, [
      {path:'contact.phone',action:'set',value:'+7 999 123 45 67'},
      {path:'contact.email',action:'remove'},
    ]);
    await button('Взять в работу').click();
    await verifyStatus('На разборе');
    await button('Отклонить').click();
    await modal.getByLabel('Причина').selectOption('other');
    await button('Отклонить', modal).click();
    await verifyStatus('Отклонена');
    assert.equal(await button('Редактировать').count(), 0);
    await button('Открыть повторно').click();
    await modal.getByLabel('Причина').selectOption('other');
    await button('Открыть повторно', modal).click();
    await verifyStatus('На разборе');
    await page.getByLabel('Учитывать демо в метриках').check();
    await metrics.getByText('100%', { exact: true }).waitFor();
    await button('Принять в работу').click();
    await verifyStatus('Принята в работу');
    await metrics.locator('.metric').filter({ hasText: 'Доля принятых в работу' }).getByText('100%', { exact: true }).waitFor();

    for (const format of ['TXT', 'JSON']) {
      const pending = page.waitForEvent('download');
      await button('Скачать ' + format).click();
      const downloaded = await pending;
      assert.equal(downloaded.suggestedFilename(), 'energytool-application-demo-application.' + format.toLowerCase());
      const contents = fs.readFileSync(await downloaded.path(), 'utf8');
      if (format === 'JSON') assert.deepEqual(JSON.parse(contents), record.card);
      else assert.match(contents, /Снизить расходы завода\nООО После правки/);
    }
    await page.reload();
    await verifyStatus('Принята в работу');
    await page.setViewportSize({ width: 390, height: 844 });
    assert.equal(await page.evaluate(() => document.documentElement.scrollWidth > innerWidth), false);
    await screenshot('application-card-mobile');
    await button('← К очереди').click();
    await entry.click();
    await verifyStatus('Принята в работу');
    await page.goBack();
    await entry.waitFor();
    assert.equal(await card.isVisible(), false);
    assert.deepEqual(errors, []);
    console.log('PASS: queue, filter, evidence, edits via proxy, transitions, replay, conflicts, exports, metrics, mobile and reload.');
  } finally {
    await browser?.close();
    preview.kill();
    server.closeAllConnections();
    server.close();
  }
}

main().catch(error => { console.error(error); process.exitCode = 1; });
