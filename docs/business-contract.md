# Бизнес-модуль: контракт для интеграции (v1, черновик к встрече 13.11)

Автор: Артём. Код: `backend/internal/business/` (ветка `artem/business-backend`), 17 тестов.
Это предложение к согласованию: имена путей и место хранения выбирает Игорь, представление — Георгий.
Действующие маршруты `/api/v1/sessions/...` и форма заявки не меняются.

## Разделение ответственности

| Кто | Что |
|---|---|
| Артём | правила карточки, правок, переходов, событий и метрик (пакет `business`, без HTTP и без хранилища) |
| Игорь | регистрация маршрутов, хранение `ApplicationRecord`, вызов функций пакета в нужных местах, идемпотентность транспорта |
| Георгий | экран очереди заявок и карточки, действия менеджера |

## Объекты

**`ApplicationRecord`** — хранимая заявка, одна на сессию. `version` растёт на каждом изменении
(повторное сохранение формы, правка карточки, переход); `card.version` всегда равна `version`.
Хранит текущую карточку, все прошлые карточки (`previous_cards`), журнал правок (`changes`, без значений),
журнал переходов (`transitions`) и `request_ids` — последние ID запросов для защиты от повторов.
`request_ids` нужен только хранилищу, в ответах API его не отдаём.

**`NeedCard`** — карточка потребности. У каждого значения:
- `status`: `confirmed` — сказал/подтвердил клиент (или правка менеджера), `assumed` — предположение консультанта, `unknown` — неизвестно;
- `origin`: `application_form`, `client_message` (дословная цитата клиента, проверенная по сообщению), `consultant`, `rule`, `client_edit`, `manager_edit`;
- `evidence`: ссылки на сообщения-основания (`message_id`, `sequence`, `quote`).

Карточка строится из сохранённой формы и `session.last_result.summary`. Новых вызовов модели нет.
Мощность берётся только как число с единицей из слов клиента; тип мощности — только если клиент его назвал.
Процентов достоверности, оценки права на продукт и экономии в карточке нет.

## Состояния обработки

```text
new ──start_review──> in_review ──accept──> accepted
                         │    └──reject (причина)──> rejected
                         └──needs_info (причина)──> needs_info ──start_review──> in_review
accepted | rejected ──reopen (причина)──> in_review
```

- `accepted` — менеджер взял заявку в работу; не договор и не выручка.
- Причина обязательна для `needs_info`, `reject`, `reopen` — код из справочника; свободный `comment` хранится в заявке и не попадает в события.
- Правка карточки после `accepted`/`rejected` запрещена (сначала `reopen`).
- Повторное сохранение формы с теми же данными — ничего не меняет. С изменёнными — та же заявка, `version+1`, прошлая карточка в истории, статус не меняется.

Справочник причин (`GET .../reasons`):

```json
{
  "missing_data": "не хватает данных об объекте/задаче",
  "unreachable": "не удалось связаться",
  "not_target": "не целевой сегмент или задача вне продуктов",
  "duplicate": "дубль обращения",
  "no_consent": "клиент отказался продолжать",
  "manager_error": "ошибка обработки (повторное открытие)",
  "other": "другое"
}
```

## Предлагаемые маршруты

| Метод и путь | Функция пакета | Ответ |
|---|---|---|
| `GET /api/v1/applications?status=new&demo=1` | — (выборка из хранилища) | список, см. «Элемент списка» |
| `GET /api/v1/applications/{id}` | — | `ApplicationRecord` без `request_ids` |
| `PATCH /api/v1/applications/{id}/card` | `EditCard` | обновлённая заявка |
| `POST /api/v1/applications/{id}/transitions` | `Transition` | обновлённая заявка |
| `GET /api/v1/applications/{id}/export?format=txt\|json` | `ExportTXT` / `ExportJSON` | файл карточки |
| `GET /api/v1/applications/reasons` | `ReasonCatalog` | справочник причин |
| `GET /api/v1/metrics/pilot?from=2026-11-13&to=2026-11-14&include_demo=1` | `ComputePilotMetrics` | сводка метрик |

`from`/`to` — даты по Москве, `to` не включается. Без параметров — весь период.

### Ошибки (общий формат ошибок Игоря)

| Ошибка пакета | HTTP | `code` |
|---|---|---|
| `ErrVersionConflict` | 409 | `version_conflict` — в ответе текущая `version`, клиент перечитывает заявку |
| `ErrInvalidTransition` | 409 | `invalid_transition` |
| `ErrApplicationClosed` | 409 | `application_closed` |
| `ErrReasonRequired` | 422 | `reason_required` |
| `ErrInvalidEdit` | 422 | `invalid_edit` |

### Правка карточки

```http
PATCH /api/v1/applications/8f1c2a90-.../card
{
  "expected_version": 1,
  "actor": "manager",
  "client_request_id": "b7d0-edit-1",
  "edits": [
    {"path": "contact.company", "action": "set", "value": "ООО Тест"},
    {"path": "power.1.kind", "action": "set", "value": "присоединённая"},
    {"path": "power.0", "action": "remove"},
    {"path": "products.0", "action": "confirm"},
    {"path": "unknowns.3", "action": "remove"}
  ]
}
```

Пути: `task`, `next_step`, `contact.phone|full_name|company`, `power` (add, «600 кВт»), `power.N` (remove),
`power.N.kind`, `products.N` (confirm/remove), `unknowns` (add), `unknowns.N` (remove).
Пакет правок применяется целиком или не применяется вовсе. Пункты «неизвестно», выведенные правилами,
пересчитываются (указали компанию — пункт «компания не указана» исчезает); следующий шаг, заданный менеджером вручную, сохраняется.

### Переход

```http
POST /api/v1/applications/8f1c2a90-.../transitions
{"action": "needs_info", "reason": "missing_data", "comment": "Не указан класс напряжения",
 "expected_version": 2, "client_request_id": "c0a1-ni"}
```

Ответ — заявка; фрагмент:

```json
{
  "id": "8f1c2a90-3b4d-4e5f-9a10-2b3c4d5e6f70",
  "session_id": "s1",
  "version": 3,
  "demo": true,
  "status": "needs_info",
  "reason": "missing_data",
  "comment": "Не указан класс напряжения",
  "updated_at": "2026-11-13T09:40:00Z",
  "transitions": [
    {"version": 2, "action": "start_review", "from": "new", "to": "in_review", "at": "2026-11-13T09:30:00Z"},
    {"version": 3, "action": "needs_info", "from": "in_review", "to": "needs_info",
     "reason": "missing_data", "comment": "Не указан класс напряжения", "at": "2026-11-13T09:40:00Z"}
  ]
}
```

Повтор с тем же `client_request_id` или запрос статуса, который уже стоит, возвращает ту же заявку без новой версии и без события.

### Элемент списка (предложение)

Без телефона: он нужен только в карточке.

```json
{
  "id": "8f1c2a90-3b4d-4e5f-9a10-2b3c4d5e6f70",
  "session_id": "s1",
  "version": 3,
  "status": "needs_info",
  "status_label": "нужны данные",
  "reason": "missing_data",
  "demo": true,
  "created_at": "2026-11-13T09:00:00Z",
  "updated_at": "2026-11-13T09:40:00Z",
  "contact_name": "Иван Тестовый",
  "company": null,
  "task": "Снизить расходы на электроэнергию завода",
  "products": ["Выход на оптовый рынок", "Солнечные электростанции"],
  "unknowns_count": 4,
  "next_step": "Позвонить и уточнить: Какой класс напряжения подключения?"
}
```

Подписи статусов: `new` — новая, `in_review` — в работе, `needs_info` — нужны данные, `accepted` — принята, `rejected` — отклонена.

### Карточка (полный пример, сгенерирован кодом)

Клиент: завод, сначала назвал 900 кВт, потом исправил на 600; спросил и про опт, и про солнечные панели.

```json
{
  "schema_version": "1.0",
  "application_id": "8f1c2a90-3b4d-4e5f-9a10-2b3c4d5e6f70",
  "session_id": "s1",
  "version": 1,
  "built_at": "2026-11-13T09:00:00Z",
  "demo": true,
  "contact": {
    "phone": {"value": "+7 900 000-00-00", "status": "confirmed", "origin": "application_form"},
    "full_name": {"value": "Иван Тестовый", "status": "confirmed", "origin": "application_form"},
    "company": {"value": "", "status": "unknown", "origin": "application_form"},
    "preferred_channel": {"value": "телефон", "status": "confirmed", "origin": "application_form"}
  },
  "task": {"value": "Снизить расходы на электроэнергию завода", "status": "confirmed", "origin": "application_form"},
  "object": [
    {"value": "завод в Тульской области", "status": "confirmed", "origin": "client_message",
     "evidence": [{"message_id": "m1", "sequence": 1, "quote": "завод в Тульской области"}]}
  ],
  "parameters": [
    {"value": "присоединённая мощность 900 кВт", "status": "confirmed", "origin": "client_message",
     "evidence": [{"message_id": "m1", "sequence": 1, "quote": "присоединённая мощность 900 кВт"}]},
    {"value": "у нас 600 кВт, а не 900", "status": "confirmed", "origin": "client_message",
     "evidence": [{"message_id": "m3", "sequence": 3, "quote": "у нас 600 кВт, а не 900"}]}
  ],
  "constraints": [],
  "power": [
    {"amount": "900", "unit": "кВт", "kind": {"value": "присоединённая", "status": "confirmed", "origin": "rule"},
     "evidence": [{"message_id": "m1", "sequence": 1, "quote": "присоединённая мощность 900 кВт"}]},
    {"amount": "600", "unit": "кВт", "kind": {"value": "", "status": "unknown", "origin": "rule"},
     "evidence": [{"message_id": "m3", "sequence": 3, "quote": "у нас 600 кВт, а не 900"}]}
  ],
  "products": [
    {"name": "Выход на оптовый рынок", "source_id": "20-products/21-orem.md#s003", "status": "assumed", "origin": "consultant"},
    {"name": "Солнечные электростанции", "source_id": "20-products/23-solar.md#s009", "status": "assumed", "origin": "consultant"}
  ],
  "unknowns": [
    {"value": "Тип мощности 600 кВт не указан: присоединённая или фактическая", "status": "unknown", "origin": "rule"},
    {"value": "Клиент назвал несколько значений мощности — уточнить актуальное", "status": "unknown", "origin": "rule"},
    {"value": "Название компании не указано", "status": "unknown", "origin": "rule"},
    {"value": "Какой класс напряжения подключения?", "status": "unknown", "origin": "consultant"}
  ],
  "next_step": {"value": "Позвонить и уточнить: Какой класс напряжения подключения?", "status": "assumed", "origin": "rule"}
}
```

При исправлении («900 → 600») карточка не выбирает значение сама: у клиента бывают две площадки,
и правило «брать последнее» ошиблось бы молча. Она показывает оба и просит менеджера уточнить.

### Метрики пилота (проверочный пример ТЗ: 10 сессий, 4 заявки, 2 accepted / 1 rejected / 1 needs_info)

```json
{
  "time_zone": "Europe/Moscow (UTC+3)",
  "includes_demo": true,
  "excluded_demo_events": 0,
  "sessions_started": 10,
  "sessions_with_question": 10,
  "sessions_with_answer": 10,
  "sessions_with_application": 4,
  "conversion_to_application": {"numerator": 4, "denominator": 10, "value": 0.4, "display": "40%"},
  "acceptance_rate": {"numerator": 2, "denominator": 3, "value": 0.6667, "display": "66,7%"},
  "status_counts": {"new": 0, "in_review": 0, "needs_info": 1, "accepted": 2, "rejected": 1},
  "time_to_application": {"n": 4, "median_seconds": 140, "p95_seconds": 230, "display": "медиана 2,3 мин, p95 3,8 мин, N=4"},
  "review_time": {"n": 3, "median_seconds": 600, "p95_seconds": 600, "display": "медиана 10,0 мин, p95 10,0 мин, N=3"},
  "sessions_without_application": {"numerator": 6, "denominator": 10, "value": 0.6, "display": "60%"},
  "needs_info_reasons": {"missing_data": 1},
  "reject_reasons": {"not_target": 1},
  "knowledge_gaps": {},
  "notes": [
    "accepted — принятие менеджером в работу, не договор и не выручка",
    "причины потерь показаны только зафиксированные менеджером; причины ухода без заявки не известны"
  ]
}
```

Формулы:
1. Конверсия = сессии когорты с сохранённой заявкой / сессии когорты. Когорта — сессии, чей первый вопрос попал в период (Москва).
2. Доля принятых = accepted / (accepted + rejected). `needs_info`, `new`, `in_review` — отдельно в `status_counts`.
3. Время до заявки = первое `application_saved` − первый вопрос; медиана, p95 (nearest-rank), N.
4. Время разбора = итоговое решение − первое `review_started`; только когда есть оба события.
5. Потери — сессии без заявки и распределение зафиксированных причин.

Пустой знаменатель → `value: null`, `display: "нет данных"`. Демо-события по умолчанию исключены (`include_demo=1` — включить).
Цифры не захардкожены: всё пересчитывается из журнала событий.

## Что нужно встроить Игорю

**1. Хранение заявки.** `ApplicationRecord` по `session_id` (или `id`) в существующем хранилище — одна запись на сессию.

**2. Вызовы в существующем коде:**

| Место | Вызов |
|---|---|
| `CreateSession` | `log.Append(business.SessionStarted(id, demo, now))` |
| `SendMessage`, после сохранения сообщения пользователя | `ConsultationRequested(sessionID, userMessage.ID, demo, at)` |
| `SendMessage`, ответ со статусом ≠ `technical_error` | `FirstAnswerReceived(sessionID, demo, at)` — ID детерминированный, учтётся только первый |
| `SendMessage`, статус `knowledge_gap` / `out_of_scope` | `KnowledgeGap(sessionID, assistantMessage.ID, status, topic, demo, at)`; `topic` — `source_id` первого источника или пусто |
| `SaveApplication` (форма) | `rec, events, err := business.SaveApplication(existing, session, newID, demo, now)` → сохранить `rec`, `log.Append(events...)` |

**3. Журнал событий.** `business.OpenEventLog(path)` — отдельный файл рядом с хранилищем сессий
(например, `BUSINESS_EVENTS_PATH=/data/events.jsonl`). Только типы событий, ID, версии, время, коды причин —
без телефонов, имён и текста реплик. Повтор того же события отбрасывается, в том числе после перезапуска.

**4. Флаг демо.** Предложение: `demo` берётся из сессии (`POST /api/v1/sessions {"demo": true}`) или из
`BUSINESS_DEMO=1` для демонстрационного стенда. Демо-данные помечаются в карточке, в выгрузке и в событиях.

**5. Работа без модели.** Карточка, переходы, выгрузка и метрики не вызывают Python/модель: после сохранения заявки
всё работает при недоступной модели.

## Что нужно Георгию

- очередь: фильтр по статусу, элемент списка (см. выше), подпись демо;
- карточка: значения с меткой «подтверждено / предположение / неизвестно», ссылки «сообщение №N» ведут в историю диалога;
- действия: «Взять в работу», «Принять», «Нужны данные» и «Отклонить» (выбор причины + комментарий), «Открыть заново»;
  правка полей карточки; кнопки выгрузки TXT/JSON;
- при `409 version_conflict` — перечитать заявку и показать, что её изменили.
