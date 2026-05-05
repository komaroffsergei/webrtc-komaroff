# Voice Chat Diagnostics

Страница быстрой диагностики живет на `/status/` основного host-а `webrtc-komaroff`. `/health/` оставлен как compatibility alias.

Она проверяет не только сам WebUI-контейнер, а рабочие границы voice-chat:

- browser -> `/ws` NATS WebSocket
- `src_front`, `src_core`, `src_api_gateway`
- `audio_nats`, leafnode/import к H100 inference NATS
- `src_agent`, active workflow runtime, tools, LLM
- `py_faster_whisper` страницы и live bridge
- LinTO HTTP на GPU
- diarization sidecar-ы `pyannote`, `sherpa-onnx`, `sortformer`

Обычный `Refresh` делает быстрые health/request-reply проверки. `Run smoke` дополнительно запускает безопасные smoke-тесты: короткий LinTO `/transcribe`, diarization `/diarize` smoke для sidecar-ов, live ASR bridge controlled-error test и LLM routing request.

LinTO HTTP smoke отправляет `Accept: application/json`. Это важно: текущий LinTO `/transcribe` отвергает default `Accept: */*` и возвращает `400 Not accepted header`, хотя GPU backend при этом может быть жив.

## Проверка После Деплоя

1. В Insight stack `web-rtc-komaroff` должен появиться сервис `web-rtc-komaroff_py_faster_whisper_status`.
2. `GET https://webrtc-komaroff.gis-master.ru/status/` должен открыть страницу `Voice Chat Status`.
3. `GET https://webrtc-komaroff.gis-master.ru/status/api/diagnostics` должен вернуть `Content-Type: application/json` и payload со статусами групп.
4. `GET https://webrtc-komaroff.gis-master.ru/health/` должен открыть тот же diagnostics WebUI через compatibility rewrite.

Если `/status/` открывает старый `Voice Assistant`, а `/status/api/diagnostics` возвращает HTML, значит новый route не попал в Docker stack/Traefik, даже если image `py_faster_whisper` уже обновился.

## GitLab Deploy Access

`/status/` появляется только после успешного deploy job в GitLab для `webrtc-komaroff`, потому что именно этот job добавляет route и service `py_faster_whisper_status` в stack `web-rtc-komaroff`.

Deploy не должен чиниться ручными командами на `gis-master`. Доступ для `dry-stack` должен прийти в GitLab runner одним из двух способов:

1. восстановить identities в runner volume `ssh-agent-socket`;
2. добавить GitLab CI/CD variable `GIS_MASTER_SSH_PRIVATE_KEY_B64`.

Рекомендуемый вариант для проекта или группы `voice-chat`:

```bash
base64 -w0 ~/.ssh/<deploy-key>
```

Результат кладется в protected CI/CD variable `GIS_MASTER_SSH_PRIVATE_KEY_B64`. Ключ должен быть уже разрешен для `root@gis-master.ru`, потому что Docker SSH context внутри deploy container идет как root. После этого надо rerun pipeline `webrtc-komaroff` на `main`. В trace должно появиться:

```text
[deploy] loading SSH key from GitLab CI base64 variable GIS_MASTER_SSH_PRIVATE_KEY_B64
[deploy] dry-stack endpoint ssh://gis-master.ru
```

Если вместо этого видно `The agent has no identities` или `no SSH identity is available for dry-stack`, GitLab runner всё еще не получил deploy identity.

## Статусы

- `OK` - все обязательные и optional проверки зеленые.
- `DEGRADED` - основной production path жив, но сломан optional sidecar или необязательная страница.
- `FAIL` - сломана обязательная граница: HTTP core, NATS, LinTO HTTP, shared pyannote, active workflow, tools, history/Postgres или browser `/ws`.

Optional сервисы не валят всю страницу в `FAIL`: `pyannote_isolated`, `sherpa_onnx`, `sortformer`, `/whisper-staged`, `/whisper-bench`.

## Общая Схема

```mermaid
flowchart LR
    Browser["Browser /status/"] --> HealthWeb["py_faster_whisper_status WebUI"]
    Browser --> BrowserWs["browser NATS WS check /ws"]

    HealthWeb --> Front["src_front /"]
    HealthWeb --> Core["src_core /core"]
    HealthWeb --> Api["src_api_gateway /api/pilot/location"]
    HealthWeb --> Lock["whisper_file_job_lock /health"]

    HealthWeb --> LocalNats["audio_nats"]
    LocalNats --> Workflow["nats.workflow.health.<active>"]
    LocalNats --> Tools["nats.tools.discover"]
    LocalNats --> History["nats.agent.history.<user>"]
    LocalNats --> JsInfo["JS.INF.API.INFO"]

    HealthWeb --> WhisperPages["/whisper-* WebUI services"]
    HealthWeb --> Linto["LinTO HTTP GPU /healthcheck, /transcribe"]
    HealthWeb --> Diar["Diarization sidecars /healthz, /diarize smoke"]

    LocalNats -. leafnode .-> InferenceNats["rag-stack inference_nats"]
    Linto --> H100["H100 MIG GPU"]
    Diar --> H100
```

## Sequence Diagram

```mermaid
sequenceDiagram
    participant B as Browser
    participant H as /status WebUI
    participant N as audio_nats
    participant R as rag-stack/H100
    participant A as agent/workflow

    B->>H: GET /status/
    H-->>B: diagnostics page
    B->>H: GET /status/api/diagnostics
    par HTTP health
        H->>H: check src_front/core/api/job-lock/whisper pages
        H->>R: GET LinTO /healthcheck with Host
        H->>R: GET pyannote/sherpa/sortformer /healthz with Host
        H->>R: POST pyannote/sherpa/sortformer /diarize smoke with Host
    and NATS health
        H->>N: connect NATS
        H->>N: request JS.INF.API.INFO
        H->>A: request workflow health subject
        H->>A: request tools discover
        H->>A: request agent history
    end
    H-->>B: status groups JSON
    B->>N: NATS WebSocket connect /ws
    N-->>B: browser ws status
```

## UML State Diagram

```mermaid
stateDiagram-v2
    [*] --> Running
    Running --> OK: all required ok\nall optional ok
    Running --> Degraded: all required ok\nsome optional fail/skip
    Running --> Fail: any required fail
    OK --> Running: refresh
    Degraded --> Running: refresh
    Fail --> Running: refresh
```

## Data Shape

```mermaid
classDiagram
    class DiagnosticsPayload {
      string status
      bool smoke
      int generated_at_ms
      int duration_ms
      DiagnosticGroup[] groups
    }

    class DiagnosticGroup {
      string id
      string label
      string status
      DiagnosticCheck[] checks
    }

    class DiagnosticCheck {
      string id
      string group
      string label
      bool required
      string status
      int latency_ms
      string target
      object details
      string error
    }

    DiagnosticsPayload --> DiagnosticGroup
    DiagnosticGroup --> DiagnosticCheck
```

## NATS Связи

```mermaid
flowchart LR
    Health["py_faster_whisper_status"] --> AudioNats["audio_nats local account"]

    AudioNats --> Js["JS.INF.API.INFO"]
    AudioNats --> Workflow["nats.workflow.health.ruby.node"]
    AudioNats --> Tools["nats.tools.discover"]
    AudioNats --> History["nats.agent.history.user123"]
    AudioNats --> Llm["nats.llm.user123"]

    Health -- smoke publish --> AsrIn["inference.whisper.stream.<diagnostics>"]
    AsrOut["inference.whisper.text.<diagnostics>"] -- controlled invalid_packet --> Health
    AsrIn --> Bridge["py_faster_whisper live bridge"]
    Bridge --> AsrOut

    AudioNats -. service import .-> InferenceJs["rag-stack $JS.dinf.API"]
```

## Что Смотреть При Поломке

- LinTO `502`: если `/healthcheck` красный, но контейнер `running`, смотреть startup/model-load path и порт `80` внутри LinTO.
- NATS `NoResponders`: смотреть subject из `target`, активный `WORKFLOW_RUNTIME` и подписку соответствующего runtime.
- `agent history / Postgres` красный: NATS дошел до `src_agent`, но DB/history boundary не отвечает.
- Browser `/ws` красный при зеленом backend NATS: проблема на ingress/websocket path, auth или browser-facing NATS config.
- Optional diarization красный и общий `DEGRADED`: основной путь может работать, но сравнение/альтернативный backend недоступен.
