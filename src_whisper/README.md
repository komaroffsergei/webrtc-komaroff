# src_whisper (ASR service)

`src_whisper` consumes streaming audio packets from NATS, performs VAD-based phrase segmentation, transcribes phrases with Whisper, and publishes JSON replies back to NATS.

## NATS routing (token-based)

The service works for **any token** without restarts.

- Clients publish audio packets to: `nats.asr.input.{token}`
- Service publishes replies to: `nats.asr.output.{token}`

The token may contain dots.

### Prefix mapping (Variant A)

Env configuration:

- `ASR_IN_SUBSCRIBE` (default: `nats.asr.input.>`)
- `ASR_IN_PREFIX` (default: `nats.asr.input.`)
- `ASR_OUT_PREFIX` (default: `nats.asr.output.`)

For every received NATS message:

1. Ensure `msg.subject` starts with `ASR_IN_PREFIX`
2. `suffix = msg.subject[len(ASR_IN_PREFIX):]`
3. `suffix` must be non-empty (otherwise the message is dropped)
4. `out_subject = ASR_OUT_PREFIX + suffix`
5. Publish all replies to `out_subject`

## Incoming packets (wire format)

Inbound payload format is unchanged:

`[meta_len:u32 BE][meta JSON UTF-8][pcm int16 LE bytes]`

`meta` fields:

- `type`: `"frame"` or `"end"` (required)
- `seq`: integer (optional)
- `sample_rate`: integer (optional; defaults to `VAD_SAMPLE_RATE`)
- `session_id`: string (optional; forwarded back in replies)
- `sample_width`: integer (optional; expected `2`)
- `channels`: integer (optional; expected `1`)

Notes:

- `"frame"` packets must include PCM bytes.
- `"end"` packets typically have no PCM bytes (flushes any pending buffered audio).

## Outgoing replies (JSON)

For each flushed phrase, the service publishes a JSON message to `nats.asr.output.{token}`:

- `phrase_id`: UUID string
- `text`: transcription text
- `duration`: phrase duration in seconds (float)
- `transcribe_time`: time spent in the model in seconds (float)
- `session_id`: present if it was present in the incoming `meta`

On errors, a reply may contain:

- `error`: string error code (e.g. `invalid_packet`, `model_error`, `transcription_failed`)
- `details`: optional string with extra info

## Configuration (env vars)

Core settings:

- `NATS_URL` (default: `nats://localhost:4222`)
- `NATS_EVENTS_SUBJECT` (default: `nats.events.`)
- `STACK_SERVICE_NAME` (default: `src_whisper_python`)

ASR routing:

- `ASR_IN_SUBSCRIBE` (default: `nats.asr.input.>`)
- `ASR_IN_PREFIX` (default: `nats.asr.input.`)
- `ASR_OUT_PREFIX` (default: `nats.asr.output.`)

Models:

- `ASR_MODELS` (default: `models/asr`)
- `ASR_MODEL_ID` (default: `Systran/faster-whisper-small`)

Segmentation (Silero VAD):

- `VAD_MODELS` (default: `models/vad`)
- `VAD_MODEL_URL` (default: Silero VAD ONNX URL)
- `VAD_SAMPLE_RATE` (default: `16000`)
- `MIN_SPEECH_DURATION_MS` (default: `250`)
- `MIN_SILENCE_DURATION_MS` (default: `500`)
- `MAX_SPEECH_DURATION_S` (default: `30.0`)
- `SPEECH_PAD_MS` (default: `30`)
- `VAD_THRESHOLD` (default: `0.8`)
- `BUFFER_CHECK_INTERVAL_S` (default: `1.0`)

Whisper:

- `WHISPER_LANGUAGE` (default: `ru`)
- `WHISPER_BEAM_SIZE` (default: `1`)
- `WHISPER_MAX_CONCURRENCY` (default: `1`)

## Running locally

From repo root:

```bash
python -m src_whisper.main
```

## Tooling: whisper_probe

`whisper_probe` publishes a WAV as `"frame"` packets + final `"end"` packet and collects JSON replies from the output subject.

Basic example:

```bash
TOKEN=test123

python -m src_whisper.tools.whisper_probe ./src_whisper/tools/test1.wav \
  --nats-url ws://127.0.0.1:9222 \
  --in-subject  "nats.asr.input.${TOKEN}" \
  --out-subject "nats.asr.output.${TOKEN}" \
  --session-id  "s1" \
  --timeout-s   10
```

Notes:

- `--in-subject` and `--out-subject` must be exact subjects (no wildcards, no trailing `.`).
- Use different tokens to run probes concurrently without mixing replies.
