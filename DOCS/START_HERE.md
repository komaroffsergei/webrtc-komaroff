# START_HERE

## 1) Подними стек

```bash
cd docker
docker compose down --remove-orphans
docker compose up -d --build
```

Активный runtime для локального Docker задается в `docker/.env`:
- `COMPOSE_PROFILES=langgraph_rb` + Ruby subjects
- `COMPOSE_PROFILES=langgraph` + Python subjects

## 2) Открой UI

- `http://127.0.0.1:8080/`

## 3) Что происходит в системе

- text turn: `src_front -> /core/message -> nats.agent.* -> runtime -> nats.llm.* / nats.tools.* -> nats.events.*`
- live voice: `WebRTC -> src_core -> inference.whisper.stream.* -> stt_whisper_to_nats -> inference.whisper.text.* -> src_core -> nats.agent.*`
- file transcription: `Browser -> /whisper/api/file-transcribe -> inference.whisper.file.* -> file worker -> NATS WS progress/result`
- LLM inference идет через `src_llm` и внешний `rag-stack` / `llm-models`.

Полная карта сервисов, subject-ов, payload-ов и `rag-stack` integration: [`ARCHITECTURE.md`](/home/komaroff/dev/monitorsoft/voice-chat/webrtc-komaroff/DOCS/ARCHITECTURE.md)

## 4) Проверка сценариев

1. `где мой рейс`
2. `SU123`
3. `найди аэропорт`
4. `как дела`

## 5) Где менять сценарии

- `src_langgraph/config/scenarios/*.json` — промпты, tool names, схемы.
- `src_langgraph/scenarios/*.py` — логика сценариев.
- `src_langgraph/engine.py` — подключение сценария в граф.
- Ruby runtime и DSL: [`src_langgraph_rb/README.md`](/home/komaroff/dev/monitorsoft/voice-chat/webrtc-komaroff/src_langgraph_rb/README.md)
