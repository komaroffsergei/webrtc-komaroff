# Quickstart

## Локально через Docker

```bash
cd /home/komaroff/dev/monitorsoft/voice-chat/webrtc-komaroff/docker
docker compose --profile langgraph up -d --build
```

Открыть:

- UI: `http://127.0.0.1:8080/`
- Core: `http://127.0.0.1:8000/core`
- NATS WS: `ws://127.0.0.1:9222`

## Текущие ASR пути

### `/chat`

```text
src_front
-> WebRTC
-> src_core
-> inference.whisper.stream.<session>
-> stt_whisper_to_nats (Phraser)
-> ASR_BACKEND=linto|local_whisper
-> inference.whisper.text.<session>
-> src_core
-> agent
```

По умолчанию:

- `ASR_BACKEND=linto`

### `/whisper`

File mode:

```text
Browser
-> /whisper/api/file-transcribe
-> NATS file job
-> stt_whisper_file_worker
-> sequential chunk HTTP to linto_stt_whisper_http
```

Stream debug:

```text
Browser
-> /whisper/ws
-> ASR_IN_PREFIX
-> stt_whisper_to_nats (тот же Phraser)
```

## Что важно

- live ASR не использует debounce/buffer в `src_core`
- live ASR не зависит от streaming partial semantics
- одна завершённая фраза даёт один `text`
- `/whisper` file mode в `main` работает только через `chunked_http_nats`
