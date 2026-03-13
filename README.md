# webrtc-komaroff

Локальный стек WebRTC + NATS + agent/runtime.

## Основные сервисы

- `src_front` — браузерный UI
- `src_core` — HTTP/WebRTC ingress
- `src_agent` — оркестрация пользовательского шага
- `src_langgraph` — runtime сценариев
- `src_llm` — LLM gateway
- `src_api_gateway` — tools runtime
- `src_postgres` — storage
- `nats` — шина сообщений
- `stt_whisper_to_nats` — canonical ASR service для `/chat` и `/whisper`

## Текущие ASR режимы

- live `/chat`:
  `WebRTC -> src_core -> inference.whisper.stream.<session> -> stt_whisper_to_nats(Phraser) -> ASR backend -> inference.whisper.text.<session>`
- `/whisper` file mode:
  `Browser -> HTTP upload -> NATS file job -> stt_whisper_file_worker -> LinTO HTTP`
- `/whisper` stream debug:
  `Browser -> /whisper/ws -> NATS -> stt_whisper_to_nats(Phraser) -> ASR backend`

Важно:

- основной live backend по умолчанию: `ASR_BACKEND=linto`
- `src_core` не буферизует live ASR и не решает, когда коммитить фразу
- `stt_whisper_to_nats` режет поток на фразы сам
- агент получает один final result на фразу

Подробная схема: [ASR_BRIDGE_FLOW.md](/home/komaroff/dev/monitorsoft/voice-chat/ASR_BRIDGE_FLOW.md)

## Быстрый запуск

```bash
cd docker
docker compose --profile langgraph up -d --build
```

Открыть:

- UI: `http://127.0.0.1:8080/`
- Core: `http://127.0.0.1:8000/core`
- API Gateway: `http://127.0.0.1:8101/api`
- NATS WS: `ws://127.0.0.1:9222`

## Что происходит в `/chat`

1. `src_front` захватывает микрофон через WebRTC.
2. `src_core` нормализует track и публикует binary packets в `inference.whisper.stream.<session_id>`.
3. `stt_whisper_to_nats` режет поток на phrase chunks.
4. Каждая завершённая фраза транскрибируется backend-ом:
   - `linto` по умолчанию
   - `local_whisper` опционально
5. Один final phrase result возвращается в `inference.whisper.text.<session_id>`.
6. `src_core` сразу отправляет этот текст агенту.

`/chat` не использует file-mode `/whisper` и не зависит от streaming partial semantics.

## Что происходит в `/whisper`

### File mode

- браузер делает `POST /whisper/api/file-transcribe`
- gateway создаёт file job
- worker режет длинный файл на чанки
- chunk-и последовательно идут в `linto_stt_whisper_http`
- браузер получает progress/result напрямую через NATS WS по `job_id`

### Stream debug

- браузер вручную шлёт `frame/end` через `/whisper/ws`
- backend прокидывает эти пакеты в `ASR_IN_PREFIX`
- дальше работает тот же `Phraser`, что и в `/chat`

## NATS subjects

- `nats.agent.<user_id>` — вход в `src_agent`
- `nats.events.<user_id>` — UI events
- `inference.whisper.stream.<session_id>` — live audio in
- `inference.whisper.text.<session_id>` — final phrase results out
- `inference.whisper.file.job` — file jobs
- `inference.whisper.file.event.<job_id>` — file progress/result

## Документация

- [DOCS/START_HERE.md](/home/komaroff/dev/monitorsoft/voice-chat/webrtc-komaroff/DOCS/START_HERE.md)
- [DOCS/QUICKSTART.md](/home/komaroff/dev/monitorsoft/voice-chat/webrtc-komaroff/DOCS/QUICKSTART.md)
- [DOCS/CORE.md](/home/komaroff/dev/monitorsoft/voice-chat/webrtc-komaroff/DOCS/CORE.md)
- [DOCS/FRONT.md](/home/komaroff/dev/monitorsoft/voice-chat/webrtc-komaroff/DOCS/FRONT.md)
