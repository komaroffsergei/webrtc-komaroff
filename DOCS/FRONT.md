# src_front

## Responsibility

`src_front` — браузерный UI для диалога, микрофона и карты.

Он:

- отправляет текст в `/core/message`
- открывает WebRTC-сессию в `/core/offer`
- слушает `nats.events.<user_id>` через NATS WS
- рендерит команды и артефакты агента

## Voice behavior

- микрофон берётся через `getUserMedia`
- по умолчанию включены:
  - `echoCancellation`
  - `noiseSuppression`
- фронт не режет поток на фразы
- live partial transcript в диалог не рисуется
- user bubble появляется только когда `src_core` получает final phrase result

Во время `command/voice { blocked: true }` фронт блокирует:

- кнопку микрофона
- текстовый ввод

## Incoming events

Основные команды из `nats.events.<user_id>`:

- `command/message`
- `command/client`
- `command/thought`
- `command/transcription`
- `command/voice`

## Network flow

Outgoing:

- `POST /core/message`
- `GET /core/history`
- `POST /core/init_map`
- `POST /core/offer`

Incoming:

- NATS WS subscription to `nats.events.<user_id>`

## Code pointers

- app flow: [src_front/src/assistant/assistantApp.ts](/home/komaroff/dev/monitorsoft/voice-chat/webrtc-komaroff/src_front/src/assistant/assistantApp.ts)
- WebRTC session: [src_front/src/webrtc/session.ts](/home/komaroff/dev/monitorsoft/voice-chat/webrtc-komaroff/src_front/src/webrtc/session.ts)
- chat UI: [src_front/src/ui/chatUi.ts](/home/komaroff/dev/monitorsoft/voice-chat/webrtc-komaroff/src_front/src/ui/chatUi.ts)
- command/event handling: [src_front/src/core/commandHandler.ts](/home/komaroff/dev/monitorsoft/voice-chat/webrtc-komaroff/src_front/src/core/commandHandler.ts)
- event logging: [src_front/src/core/logging.ts](/home/komaroff/dev/monitorsoft/voice-chat/webrtc-komaroff/src_front/src/core/logging.ts)
