# src_core

## Responsibility

`src_core` — HTTP/WebRTC ingress для браузера.

Он:

- принимает `POST /core/message`
- принимает `POST /core/offer`
- публикует live audio в NATS
- принимает final phrase results из ASR
- пересылает готовый текст агенту

Он не режет живой поток на фразы и не выполняет workflow logic.

## Endpoints

- `GET /core`
- `POST /core/offer`
- `POST /core/message`
- `GET /core/history`
- `POST /core/init_map`

## Message flow

### Text input

1. Browser делает `POST /core/message`.
2. `src_core` нормализует `turn_id`.
3. Дальше идёт req/reply в `nats.agent.<user_id>`.

### Live ASR

1. Browser отправляет WebRTC audio track в `POST /core/offer`.
2. `handle_track.py` строит:
   - `TrackSourceNode`
   - `WhisperStreamNode`
3. `TrackSourceNode` нормализует аудио в mono `16kHz`.
4. `WhisperStreamNode` публикует binary wire packets в `inference.whisper.stream.<session_id>`.
5. `stt_whisper_to_nats` режет поток на phrase chunks и публикует final result в `inference.whisper.text.<session_id>`.
6. `handle_transcription.py`:
   - принимает final `text`
   - публикует `command/voice`
   - публикует `command/transcription`
   - сразу делает запрос в агент

`src_core` не буферизует несколько ASR сегментов и не использует debounce-коммит.

## NATS subjects

- `nats.agent.<user_id>`
- `nats.agent.history.<user_id>`
- `nats.events.<user_id>`
- `inference.whisper.stream.<session_id>`
- `inference.whisper.text.<session_id>`

## Environment

- `CORE_HOST`
- `CORE_PORT`
- `NATS_URL`
- `NATS_EVENTS_SUBJECT`
- `NATS_AGENT_SUBJECT`
- `NATS_AGENT_HISTORY_SUBJECT`
- `NATS_REQUEST_TIMEOUT`
- `ASR_IN_PREFIX`
- `ASR_OUT_PREFIX`
- `API_URL`
- `USER_ID`

## Code pointers

- entry: [src_core/main.py](/home/komaroff/dev/monitorsoft/voice-chat/webrtc-komaroff/src_core/main.py)
- offer handler: [src_core/handlers/handle_offer.py](/home/komaroff/dev/monitorsoft/voice-chat/webrtc-komaroff/src_core/handlers/handle_offer.py)
- track handler: [src_core/handlers/handle_track.py](/home/komaroff/dev/monitorsoft/voice-chat/webrtc-komaroff/src_core/handlers/handle_track.py)
- ASR out handler: [src_core/handlers/handle_transcription.py](/home/komaroff/dev/monitorsoft/voice-chat/webrtc-komaroff/src_core/handlers/handle_transcription.py)
- stream node: [src_core/processors/whisper_stream_node.py](/home/komaroff/dev/monitorsoft/voice-chat/webrtc-komaroff/src_core/processors/whisper_stream_node.py)
