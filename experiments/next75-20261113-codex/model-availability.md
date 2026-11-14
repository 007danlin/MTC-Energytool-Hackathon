# Проверка локальной модели — 13 ноября 2026

Статус первого эксперимента: pinned 4-bit веса скачаны и проверены; локальный сервер реально выполнил2 sanity smoke и4 деловых ответа (2 завершённые пары). Пятый деловой HTTP прерван координированно после двух системных CRITICAL измерений. Наш сервер и runner остановлены, порт18765 свободен; это проверено повторно при возобновлении. Это подтверждение локального инференса, не воспроизведение скрытой платформенной конфигурации.

## Локальные факты

`sysctl hw.memsize hw.model`: 34359738368 bytes (32 GiB), Mac16,13. `df`: 618 GiB available. Это не 16 GiB. Два Ollama-сервера: 127.0.0.1:11434, версия 0.32.14; 127.0.0.1:11435, версия 0.40.11. В обоих `/api/ps` вернул пустой список. Не останавливались сторонние процессы.

В обоих зарегистрированы energytool-qwen-local-eval:20261110, qwen3-vl:30b-a3b-instruct, qwen3-vl:8b-instruct, qwen3-vl:4b-instruct, qwen3-vl:2b-instruct и qwen3:4b-instruct. Qwen3.8 нет. Поиск в стандартном HF cache (отсутствует), Ollama manifests, workspace, Downloads и Library/Caches не нашёл Qwen3.8 weights. Это ограниченный инвентарь, а не доказательство отсутствия в каждом каталоге диска.

Alias energytool-qwen-local-eval действительно Qwen3-VL-30B-A3B-Instruct, GGUF Q4_K_M, 31.1B total params, размер 19595409816 bytes; digest 0cfe481aa32a651f1ab473d9bc0a66a3aedcf2244def7f0ca989e9ecd458e57e. Template `{{ .Prompt }}`, SHA256 b507b9c2f6ca642bffcd06665ea7c91f235fd32daeefdf875a0f938db05fb315. Params num_ctx=16384, seed42, temperature0, top_k20, top_p0.95. Поэтому прямое OpenAI chat использование этого alias без прежнего harness нельзя объявлять совместимым с сохранёнными прогонами.

## Модель организаторов и официальный источник

Сохранённый Q&A №33 называет Qwen3.8-27B; сообщение 11 ноября 19:24 говорит об API провайдера и нераскрытой конфигурации. Это не гарантирует точность, runtime, template revision и thinking режим платформы.

[Официальный Qwen репозиторий](https://huggingface.co/Qwen/Qwen3.8-27B) доступен. Текущий pinned revision `37561816e66b5b9153b1b64c10968c18c1e6f4a0`, Apache-2.0, BF16, совокупные файлы 55586107015 bytes. Оригинальные BF16 веса не помещаются в 32 GiB даже без KV/cache. [Официальный исходный config](https://huggingface.co/Qwen/Qwen3.8-27B/blob/37561816e66b5b9153b1b64c10968c18c1e6f4a0/config.json) использует qwen3_5, 64 layers, 16 full attention +48 linear attention, 4 KV heads, head_dim256, native262144 context.

[Квантование MLX Community](https://huggingface.co/mlx-community/Qwen3.8-27B-4bit/tree/b935172e4bb5dcd0543774a34748fb92422e3027) pinned revision `b935172e4bb5dcd0543774a34748fb92422e3027`, Apache-2.0, affine4bit group64, 16074310928 bytes (~14.97GiB), 3 safetensors shards. README указывает conversion from Qwen/Qwen3.8-27B using mlx-vlm0.6.8, но не сообщает точный base revision; это ограничение provenance. SHA/size каждого файла опубликованы в mlx_meta.json; после download проверяются локально.

[MLX-LM v0.32.2 source](https://github.com/ml-explore/mlx-lm/blob/v0.32.2/mlx_lm/models/qwen3_5.py) поддерживает qwen3_5 и sanitizes мультимодальные веса для text-only. Есть также [llama.cpp qwen35 implementation](https://github.com/ggml-org/llama.cpp/blob/master/src/models/qwen35.cpp) и [Ollama qwen3.8:27b](https://ollama.com/library/qwen3.8:27b) Q4_K_M18GB. Выбран isolated MLX для pin weights/runtime и контроля шаблона; на наличие исходного кода не ссылаемся как на доказательство рабочего инференса.

## Память и стартовый режим

Для неквантованного KV с 2-byte элементами оценка `16*2*4*256*2=65536 bytes/token`: 2GiB при32768 токенах, 4GiB при65536. Linear recurrent state оценивается ~0.15GiB, поверх ~15GiB weights нужны runtime buffers/activations. Это теоретическая оценка, не замер peak. Старт с одним запросом, prefill256, concurrency1, prompt cache1; 32k суммарный контекст контролировать клиентом. MLX server не имеет CLI max-context в просмотренной версии. Нельзя молча резать входной N2 контекст.

До запуска память уже занята приложениями, vm.swapusage used11712.75MiB. Один запуск с мониторингом допустим, но «32GiB значит гарантированно влезает без swap» не доказано. Сторонние процессы не останавливать. Никакую вторую тяжёлую модель не запускать одновременно.

## Шаблон и HTTP

Official template SHA256 `af16f654968d47d09a6c604e00370b12dbc21f76456f59c9e98b82e84d9f6375`; MLX template SHA256 `c3cf9e34abf4f9e36c2d72165aa9c132d3e2a725b6c2586aaa3a8af9d7a81041`. Diff только добавляет training generation/endgeneration annotations и перенос конкатенации; для текстовых сообщений ожидается одинаковая последовательность, но это проверяется tokenizer smoke. По умолчанию thinking=true, reasoning_effort=xhigh. Допустимы xhigh, medium, low. enable_thinking=false отключает thinking.

[MLX server v0.32.2](https://github.com/ml-explore/mlx-lm/blob/v0.32.2/mlx_lm/server.py) читает `chat_template_kwargs`, включая enable_thinking/reasoning_effort. Top-level reasoning_effort и reasoning object сами по себе игнорируются. N2 в low/medium/off одновременно передаёт effective kwargs, поэтому adapter не нужен. Штатный default N2 без hints получает native template defaults. Неизвестно, что делает провайдер платформы.

Для локального сервера выбран 127.0.0.1:18765. Внешние сервисы получают только запросы скачивания публичных пакетов/весов; база, вопросы и ответы наружу не передаются.

## Артефакты

local-model-metadata.json; official_meta.json; mlx_meta.json; gguf_meta.json; official_config.txt; official_template.txt; mlx_config.txt; mlx_template.txt; mlx_readme.txt; mlx_qwen35_source.txt; mlx_server_source.txt; model-runtime/install.log; model-runtime/requirements-frozen.txt; model-runtime/download_weights.py. Крупные веса не входят в конкурсный ZIP.

## Дополнение: проверка tokenizer

MLX и официальный template дали идентичную побайтовую последовательность на 8 synthetic сочетаниях: single/multi-turn × default/off/low/medium. Это не проверка всех допустимых входов. Результат: model-runtime/template-equivalence.json. Готов count_payload_tokens.py для фактических JSON payloads.

## Дополнение: реальные N2 token counts

На известном dev123 точный N2 docs и pinned tokenizer дают input15973–23417 tokens, p50=19342, mean19658.80. С output4096 максимальный резерв27513; 0/123 превышают32768. Все123 character counts совпали с независимым n2-context-sizes.json. Native default xhigh instruction учтён. Это token/preflight audit, не inference и не оценка качества. Артефакт model-runtime/n2-token-audit.json.

Следствие для исправления retry/cap: при реальном32k окне natural overflow на этом известном наборе не ожидается, поэтому synthetic overflow эксперимент не доказывает выигрыш в обычном режиме и может затрагивать редкую ветку. Окно и tokenization скрытого провайдера неизвестны; эти123 сценария не определяют hidden distribution.

## Завершённый запуск

Download занял 1334.08с. Проверены размеры15 файлов; SHA256 трёх safetensors shards и tokenizer совпали с опубликованными HF LFS SHA. Полный локальный manifest: `model-runtime/weights-manifest.json`. Python3.12.1, mlx0.32.4, mlx-metal0.32.4, mlx-lm0.32.2, transformers5.22.2, huggingface-hub2.4.0, tokenizers0.23.3; freeze и module hashes сохранены. Фактически установленный mlx_lm.server/model source совпал с просмотренным v0.32.2 source.

Команда запуска выполнена из `/private/tmp`:

```sh
'/Users/daniellineckij/Хакатон "МТС"/experiments/next75-20261113-codex/model-runtime/venv/bin/python' -u '/Users/daniellineckij/Хакатон "МТС"/experiments/next75-20261113-codex/model-runtime/launch_server.py'
```

Сервер: `http://127.0.0.1:18765/v1`, model ID `/Users/daniellineckij/Хакатон "МТС"/experiments/next75-20261113-codex/model-runtime/weights`. PID83865 на момент запуска; последующие PID могут отличаться. Он использует `HF_HUB_OFFLINE=1`, native unquantized KV (dtype непосредственно не наблюдался), single prompt/decode concurrency1, prefill256, prompt-cache-size1, prompt-cache-bytes3G, default max_tokens4096, chat-template-args={}. MLX cache limit256MiB, memory guideline23GiB — guideline не является жёстким лимитом RAM.

Два synthetic smoke выполнены `model-runtime/smoke_stream.py`, на один и тот же запрос о2+2, temperature0, вначале off128tokens затем native default512tokens. Off: content «Четыре», reasoning пустой, stop, prompt27/completion4, elapsed3.894с, first text3.424с. Default: content «Четыре», reasoning присутствует, stop, prompt67/completion49, elapsed10.369с, first text/reasoning2.170с. Полные payload/hash/SSE events/output/usage: `model-runtime/smoke-results.json`. Это минимальная проверка модели, не quality evaluation. Скрипт smoke_model.py был подготовлен, но не запускался; фактический smoke потоковый.

Во время setup+smoke максимум наблюдаемого MLX allocation peak15864126874 bytes (14.78GiB), max sampled process RSS7005880320 bytes (6.52GiB). Показатели имеют разные semantics и частично общую память, их нельзя складывать. Пассивный sampler каждые2с продолжает `server-memory.jsonl`; поздние строки уже относятся к root diagnostic requests. Native server не отдаёт независимые kernel prefill/decode timings. По короткому default smoke end-to-end completion throughput4.73token/s, после первого текстового события грубо~6token/s; переносить это на20k prompts нельзя.

Из неудач: первый token audit завершился до HTTP из-за отсутствующих обязательных inert LLM env placeholders; исправление и сообщение сохранены в token-audit-initial-failure.txt. Download/install/model smokes ошибок не дали. Никакой второй тяжёлой модели, внешней генерации, остановки стороннего процесса или платформенной загрузки не было. После передачи URL root этот агент больше не отправляет запросы модели, чтобы не наложить генерации.

Уточнение readiness: GET /v1/models перед smoke вернул пустое тело и server traceback CacheNotFound в HF scan_cache_dir: local_dir weights существуют, но hf-cache/hub не создавался. Это metadata endpoint error, сохранён в server.log; последующие POST smoke и long-context prefill работают. Во время root inference runtime не исправлялся.

## Пассивная системная проверка во время длинных запросов

`kern.memorystatus_vm_pressure_level=1` соответствует normal: [Apple XNU handler](https://github.com/apple-oss-distributions/xnu/blob/xnu-10063.101.15/bsd/kern/kern_memorystatus_notify.c#L1639) возвращает dispatch-level, а установленный dispatch/source.h определяет NORMAL1/WARN2/CRITICAL4. Это instantaneous level, не непрерывная история. На первом snapshot во время четвёртого запроса swapused9061.56MiB(~8.85GiB), ниже исходных11712.75MiB(~11.44GiB), wired~21.12GiB и compressor~4.35GiB. Большой wired включает системную и MLX память; нельзя складывать его с MLX allocation. Низкий free page count сам по себе не доказывает критическое давление. Причина снижения tokens/s по этим фактам не установлена.

Утилита memory_pressure на этомMac в help описывает -Q как quiet, а default operation — выделение памяти. Поэтому отдельно -Q не запускался. Использованы только vm_stat и read-only sysctl, без simulate/pressure settings. Журналы: system-memory-observations.jsonl и passive-system-memory.jsonl; второй проверяет pressure каждые15с и сообщает о2/4. Никаких сторонних процессов не останавливали.

## Итог прерванного парного эксперимента

В live-diagnostics-v1 зарегистрировано5 деловых HTTP:4 завершённых непустых ответа с finish_reason=stop, то есть пары np01 и np03; первый запрос np09 прерван, np11 не начат. Отдельно ранее завершены2 synthetic smoke. Ни прерывание, ни незавершённая пара не являются проигрышем качества. Итог сохранён в model-runtime/interrupted-resource-summary.json.

Измерено2 последовательных CRITICAL=4 с интервалом около15с; в наблюдаемом интервале swap used достиг 27544.12MiB, peak swap-out 776.15MiB/s. MLX peak 18.05GiB не отражал общего давления32GiB системы. Был замечен сторонний Ollama llama-server PID8599, которого этот агент не запускал и не останавливал. Одновременная нагрузка — возможный фактор; единственная причина критического давления не установлена.

Root остановил runner85552 через SIGINT и затем наш MLX83865 через SIGTERM; cleanup завершил child6320/proxy6318. Время остановки: 2026-11-13T15:36:46.136755+03:00. Повторная проверка 2026-11-13T16:19:27.507851+03:00: все4PID отсутствуют, listener18765 отсутствует; собственные пассивные мониторы93384/6443/90099 также отсутствуют. Current pressure=1 (NORMAL), vm.swapusage: total = 10240.00M  used = 8641.81M  free = 1598.19M  (encrypted). Полные проверки — final-stop-check.json. Ни один чужой процесс не остановлен.

## Read-only инвентарь после возобновления

На16:21:56МСК resident-моделей на11434 нет;11435 не слушает, llama-server процесса нет, pressure NORMAL1, swap8617.81MiB. Это моментальный снимок, не гарантия отсутствия последующей фоновой загрузки. Готовый dedicated cross-encoder reranker в проверенных путях не найден. Есть BGE-M3 encoder (2.271GB FP32 weights), полный snapshot5617a9f61b028005a4858fdac845db406aefb181 и существующий CPU стек torch2.15.0/sentence-transformers6.3.0. Это embedding model, а не cross-encoder. Другой snapshot9a0624... содержит только safetensors, поэтому версии нельзя молча смешивать. Инвентарь и ограниченный CPU compute plan — local-reranker-readiness.json; новых скачиваний и inference при этом инвентаре не было.

## Новая сессия order-only после возобновления

По отдельному поручению root поднят тот же MLX runtime для нового эксперимента N2 vs order-only. Новый serverPID16257, supervisorPID16242, URL http://127.0.0.1:18765/v1. Все argv inference flags, cache/memory guidelines и KV mode побайтово/структурно совпадают с первым запуском; сравнение сохранено в rerank-order-v1/model-session/prior-runtime-parameter-comparison.json. Логи и новый manifest изолированы в этой папке. Watchdog останавливает только собственный child-server при resident чужой модели/новом llama-server, недоступном для достоверной проверки local endpoint (кроме connection refused) либо двух CRITICAL15с подряд. Root driver отвечает за3600с бюджет серии. На момент передачи ready деловых и smoke запросов от setup-агента0. Эту новую сессию нельзя смешивать с завершёнными4ответами и прерыванием предыдущей.

## Диагностика разрыва wall-clock в order-only сессии

Первый HTTP начат16:26:37.378МСК, final metadata сохранён16:54:16.185МСК: wall 1658.806с против reported monotonic 647.539с. Разница 1011.267с находится внутри HTTP; следующий запрос начался всего через 0.367с после final metadata. Это не1000с задержки runner между запросами.

pmset подтвердил три соответствующие паузы Sleep/Wake, одновременно наблюдаемые в отдельных watchdog и memory sampler процессах. Текущий Python monotonic реализован через mach_absolute_time; [Apple документирует](https://developer.apple.com/documentation/kernel/1462446-mach_absolute_time), что этот clock не растёт во время сна системы. Сон объясняет разницу в пределах точности sampler; дополнительный wall-clock jump для объяснения не требуется. Исторический label Thermal Emergency Sleep не является измерением температуры. Read-only thermal проверка после первого HTTP: NSProcessInfo fair1, pmset без thermal/performance warning, новых emergency-sleep событий не найдено.

Отдельный guardPID24955 контролирует первоначальный3600с real-wall budget: deadline17:26:37.135МСК, без продления по результатам. При deadline/serious/critical thermal он сверяет argv+lstart runner16509, отправляет SIGINT, даёт cleanup, затем завершает только supervisor16242/server16257. Во сне guard исполняться не может; после пробуждения немедленно проверяет фиксированный wall deadline и новые emergency events. Подробная диагностическая записка: rerank-order-v1/model-session/wall-clock-gap-diagnostic.json. Текст модельных ответов/reasoning при этой диагностике не читался.


## Order-only session: thermal interruption (2026-11-13)

The fixed real-wall budget guard observed `NSProcessInfo.thermalState=3` (critical) at 17:02:36.546 Moscow and immediately interrupted verified own runner16509 with SIGINT. It then signalled own supervisor16242. macOS independently recorded a second `Thermal Emergency Sleep`, 17:02:35–17:12:20 (585 seconds), which delayed cleanup while the host slept. At wake, the guard verified and sent fallback SIGTERM only to own MLX16257. All four own processes (including guard24955) were absent on the final check; port18765 had no listener. No foreign process was stopped.

This intervention occurred about2159.45 real-wall seconds after series start, before the unchanged 3600-second deadline (17:26:37.135). There was no result-dependent extension. At17:15:24 the host reported thermal0/nominal, memory pressure1/normal, and swap7985.62MiB. The critical thermal category and logged emergency sleep are observed facts; neither is a temperature reading or proof of single-process causality. The model remains stopped.

Exact records: `rerank-order-v1/model-session/wall-thermal-intervention.json`, `post-thermal-intervention-snapshot.json`, and `thermal-interrupted-resource-summary.json`. The final summary preserves only whitelisted HTTP timing/state metadata, not model text. Interrupted work is not a completed quality result.
