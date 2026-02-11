# С чего начать (пользовательский сценарий)

Этот проект — стек микросервисов WebRTC + NATS, где n8n выступает оркестратором сценариев (workflows).
Код n8n-стека и bridge находится в отдельном репозитории: `~/dev/monitorsoft/voice-chat/n8n`.

Быстрый старт (как поднять стек/что менять в env): `DOCS/QUICKSTART.md`.

## 1) Откройте клиент (src_front) в браузере

- Откройте `http://127.0.0.1:8080/`.
- UI подключается к NATS по WebSocket:
  - dev (Vite): `ws://localhost:9222`
  - docker-версия (nginx): `ws(s)://<host>/ws` (это прокси на NATS WebSocket)

UI подписывается на `nats.events.<user_id>` и отрисовывает команды/события, которые приходят от backend.

## 2) Отправьте сообщение

Когда вы отправляете сообщение в UI, происходит следующее:

1) `src_front` делает HTTP POST в `src_core`:
   - endpoint: `POST /core/message`
   - body: `{ "text": "...", "session_id": "<uuid | null>", "edit": {...} | null }`
2) `src_core` пересылает текст в `src_agent` через NATS (req-reply):
   - subject: `nats.agent.<user_id>`
3) `src_agent` — тонкий раннер:
   - создаёт/обновляет сессию в Postgres (`sessions`)
   - загружает `runtime_state` из Postgres
   - делает NATS-request в `src_n8n` (`nats.n8n.run`)
   - сохраняет `next_runtime` обратно в Postgres (optimistic lock по `runtime_state.version`)
   - публикует команды/события для UI в `nats.events.<user_id>`
4) `src_front` получает UI-команды из `nats.events.<user_id>` и отображает результат.

Важно: `POST /core/message` отвечает быстро (`{status, session_id}`), а сам ответ пользователю приходит в UI через NATS
события.

Важно для отладки: не запускайте одновременно по два экземпляра одного и того же сервиса (например, контейнер + процесс из IDE),
иначе вы получите дубли/нестабильное поведение. Для `src_n8n` см. `DOCS/N8N_BRIDGE.md`.

## 3) Примеры сообщений (демо-сценарии)

Router workflow выбирает один из демо-workflows:

- `echo@1.0.0`: попробуйте `привет` или `повтори: тест`
- `collect_name@1.0.0`: попробуйте `как меня зовут?` (попросит имя), затем `меня зовут Алексей`
- `airports_and_weather@1.0.0`: попробуйте `найди аэропорты рядом с Москвой` (попросит город/радиус), затем ответьте:
  - `Москва`
  - `50`

## 4) Где теперь живут сценарии

Вся логика сценариев находится в workflows n8n (визуальный редактор + хранение в Postgres schema `n8n`).
В `src_agent` больше нет выбора сценария, извлечения параметров или registry сценариев.

## 5) Частые ошибки и быстрые решения

### 5.1 `Cannot bind to 0.0.0.0:8000` / `address already in use`

Причина: порт `8000` на хосте уже занят (обычно запущен контейнер `src_core`).

Решения:

- остановить контейнер: `docker compose -f docker/docker-compose.yml stop src_core`
- или запустить локальный `src_core` на другом порту: `CORE_PORT=8002 python -m src_core.main`

### 5.2 `ConnectionRefusedError ... ('127.0.0.1', 4222)`

Причина: NATS не запущен на хосте.

Решение:

- `docker compose -f docker/docker-compose.yml up -d nats`

### 5.3 `Failed to call n8n webhook` / `n8n returned 500`

Чаще всего причина — n8n workflow не может вызвать tool proxy (URL/резолвинг/переменные окружения).

Что проверить:

1) `n8n` доступен: `http://127.0.0.1:5679/`
2) В контейнерах n8n корректен `TOOL_PROXY_URL`:
   - `docker compose -f ~/dev/monitorsoft/voice-chat/n8n/docker/docker-compose.yml exec -T n8n sh -lc 'echo $TOOL_PROXY_URL'`
3) Убедитесь, что `src_n8n` запущен в Docker (tool proxy доступен как `http://src_n8n:9000/tool` внутри сети).

Подробности: `DOCS/N8N_BRIDGE.md`.

Дополнительно: подробный end-to-end пример "найди ближайший аэропорт" (где LLM, где tools, какие subjects):

- `DOCS/example.md`

### 5.4 Дубли сообщений/команд в UI

Причины:

- одновременно запущены два экземпляра одного сервиса (контейнер + локально), или
- UI подписался на один subject несколько раз (обычно после реконнекта).

Решение: убедитесь, что запущен только один инстанс каждого сервиса; для `src_n8n` см. `DOCS/N8N_BRIDGE.md`.
