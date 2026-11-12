МТС Energytool — линия N3, продолжение N2 (12.11.2026)

НАЧНИТЕ С REPORT-N3.md.

ЧТО ОТПРАВЛЯТЬ НА ПЛАТФОРМУ СЕГОДНЯ (одна попытка)
  release/mts-energytool-n3-docs.zip
  SHA-256 0a5dce8b3e8abbf5454e2a16d609a91463010b610fc0035652efe911643d0ce0
После отправки записать балл и «Длительность UI».

ЛУЧШИЙ ПОДТВЕРЖДЁННЫЙ (не менять): control/mts-energytool-n2-docs.zip — 69.912
  SHA-256 a22d786f895257e14fb89e747a674cd419be0d711ed43b834fb9442ef3b6ac9b

СЕГОДНЯ НЕ ОТПРАВЛЯТЬ: prepared/mts-energytool-n3-kb.zip (вся база в запросе; ждёт результата n3-docs)
  SHA-256 91a29848e509c4ff2336e8aab7346774057d36ac13418eb77071b9bb7d58c1f4

Качество N3 на Qwen3.8-27B НЕ измерено: модель не запускалась, проверки — на имитаторе API.

СОСТАВ
  release/   кандидат n3-docs и его manifest
  prepared/  n3-kb и его manifest
  control/   N2 (69.912), N1 (58.758) и A2 (55.969) без изменений
  source/    исходники N3; из них побайтно собираются оба архива
  tools/     сборка, запуск точных байтов ZIP, приёмка, имитатор API,
             T1 (совпадение с A2 в контрольном режиме), T3 (сравнение с N2), T4 (запрос n3-kb против N2)
  data/      база знаний и наборы вопросов для приёмки
  eval/      замороженный набор 67 вопросов и список разрешённых зависимостей
  evidence/  журналы приёмки 47/47, T1, T3, T4
  history/   баллы платформы

КАК ПОВТОРИТЬ ПРОВЕРКИ (Python 3.9+, без сети и без модели)
  python3 tools/build_zip.py --source source --output /tmp/n3-docs.zip
  python3 tools/build_zip.py --source source --output /tmp/n3-kb.zip --set context=kb
  python3 tools/accept.py release/mts-energytool-n3-docs.zip /tmp/accept-n3-docs
  python3 tools/t1_equivalence.py release/mts-energytool-n3-docs.zip /tmp/t1
  python3 tools/t3_compare.py release/mts-energytool-n3-docs.zip /tmp/t3
  python3 tools/t4_kb_request.py prepared/mts-energytool-n3-kb.zip /tmp/t4

НЕ ЗАГРУЖАЙТЕ ЭТОТ ПАКЕТ НА ПЛАТФОРМУ — туда идёт только один ZIP из release/.
