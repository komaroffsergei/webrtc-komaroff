# src_core (WebRTC + HTTP ingress)

## Что это

`src_core` предоставляет:

- HTTP endpoints для UI:
  - `GET /core` (index)
  - `POST /core/offer` (WebRTC offer)
  - `POST /core/message` (вход текста пользователя)
  - `POST /core/init_map` (данные для инициализации UI)
- Мост от HTTP-сообщения пользователя к `src_agent` через NATS (req-reply).
- Публикацию UI событий в `nats.events.<user_id>` через общий event bus.

## Как работает `POST /core/message`

1) Валидирует JSON и поле `text`.
2) Вызывает `handle_transcription()`, который делает NATS request в `nats.agent.<user_id>`.
3) Возвращает в браузер `{ status: "ok", session_id }`.

Пользовательский ответ отображается не через HTTP ответ, а через события в `nats.events.<user_id>`, которые UI
подпиской получает и рисует.

## Частая проблема: порт 8000 уже занят

Если запущен docker-compose, то `src_core` внутри Docker уже занимает порт `8000` на хосте.
Если вы запускаете `src_core` локально, получите ошибку:

- `address already in use`

Решение:

- остановить Docker контейнер `webrtc-komaroff-dev-src_core-1`, или
- запустить локально на другом порту: `CORE_PORT=8002` (или любой свободный).

## Конфигурация

Смотрите `src_core/settings.py` и `src_core/env.example`.

Ключевые env vars:

- `CORE_HOST`, `CORE_PORT`
- `NATS_URL` (TCP для req-reply в агент)
- `NATS_EVENTS_SUBJECT`, `NATS_AGENT_SUBJECT` (prefix-ы)
- `API_URL` (для вызовов HTTP mock API из `init_map`)
