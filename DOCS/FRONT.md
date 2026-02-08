# src_front (Web UI)

## Что это

`src_front` — браузерный UI:

- Поднимает WebRTC сессию с `src_core` (signaling endpoints под `/core/*`).
- Подключается к NATS по WebSocket и подписывается на `nats.events.<user_id>`.
- Отправляет текст пользователя в `src_core` через `POST /core/message`.
- Отрисовывает UI-команды, которые приходят через NATS events.

## Как запустить и открыть

- Docker UI: `http://127.0.0.1:8080/`
- Dev mode (Vite): из `src_front/` запустите `npm run dev` (см. `README.md`)

## Какой трафик и куда

### Исходящий (пользователь -> backend)

- HTTP: `POST /core/message` (в `src_core`)
- Payload: `{ text, session_id?, edit? }`

### Входящий (backend -> пользователь)

- NATS WS subscription: `nats.events.<user_id>`
- UI ожидает JSON-события (строка/utf-8).

## UI-команды

Хендлеры UI-команд зарегистрированы в `src_front/src/agentCommands/commands/index.ts`.
Демо-workflows используют:

- `SHOW_MESSAGE`
- `ASK_USER_INPUT`
- `SHOW_AIRPORTS`
- `SHOW_ERROR_MESSAGE`

## Привязка к пользователю (subjects)

Сейчас subjects в UI захардкожены на `user123`:

- events: `nats.events.user123`
- agent: `nats.agent.user123`

Если нужна изоляция по пользователям, конфиг надо брать из runtime settings (например, из `window.SETTINGS` или env),
а subjects формировать на основе реального `user_id`.

## Код (куда смотреть)

- NATS WS клиент и подписки: `src_front/src/net/natsClient.ts`
- Роутинг UI-команд: `src_front/src/agentCommands/commands/index.ts`
- Логирование событий в консоли: `src_front/src/net/logging.ts`

## Частые ошибки

### UI не получает ответы (пусто после отправки текста)

Проверьте:

- открыт ли UI: `http://127.0.0.1:8080/`
- доступен ли NATS WebSocket: `ws://127.0.0.1:9222`
- совпадает ли `user_id` в subjects (сейчас захардкожено `user123`)

### Дубли команд (одно и то же сообщение показывается 2+ раза)

Причины:

- одновременно запущены 2 экземпляра backend-сервиса (контейнер + локально), или
- UI подписался на один и тот же subject несколько раз (обычно после реконнекта).

Что делать:

- убедиться, что запущен только один инстанс каждого сервиса (`docker compose ps` + не запускать локально тот же сервис)
