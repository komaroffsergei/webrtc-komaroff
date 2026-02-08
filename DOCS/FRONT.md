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
