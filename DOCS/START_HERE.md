# С чего начать (пользовательский сценарий)

Этот проект — стек микросервисов WebRTC + NATS, где n8n выступает оркестратором сценариев (workflows).

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

- `echo@1.0.0`: попробуйте `hello`
- `collect_name@1.0.0`: попробуйте `name`, затем `my name is Alice`
- `airports_and_weather@1.0.0`: попробуйте `airport weather moscow`, затем `250`

## 4) Где теперь живут сценарии

Вся логика сценариев находится в workflows n8n (визуальный редактор + хранение в Postgres schema `n8n`).
В `src_agent` больше нет выбора сценария, извлечения параметров или registry сценариев.
