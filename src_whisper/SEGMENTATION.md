## Stream phrase segmentation (src_whisper)

This service supports two input formats:

1. **Streaming frames**: `[meta_len:u32 BE][meta JSON][pcm int16 LE bytes]` with `meta.type=frame` and `meta.type=end`.
2. **Single phrase packets** (legacy): the same container, but `meta.type=phrase` and PCM is a whole phrase.

This document describes **stream segmentation**, which is performed **inside `src_whisper`**.

### Wire protocol (stream mode)

Clients publish audio packets to an input subject derived from a token:

- **Input**: `nats.asr.input.{token}`
- **Output**: `nats.asr.output.{token}`

The token may contain dots.

### NATS subject subscription

The service subscribes to a wildcard input subject and derives the output subject from the incoming subject.

Config (env vars):

- `ASR_IN_SUBSCRIBE` (default `nats.asr.input.>`)
- `ASR_IN_PREFIX` (default `nats.asr.input.`)
- `ASR_OUT_PREFIX` (default `nats.asr.output.`)

For every received NATS message:

1) Ensure `msg.subject` starts with `ASR_IN_PREFIX`.
2) `suffix = msg.subject[len(ASR_IN_PREFIX):]`
3) `suffix` must be non-empty.
4) `out_subject = ASR_OUT_PREFIX + suffix`
5) Publish all replies to `out_subject` (no request/reply inbox routing).

Incoming `meta` fields (required/used):

- `type`: `"frame"` or `"end"`
- `seq`: integer (optional; ignored by segmentation)
- `sample_rate`: integer (optional; defaults to `VAD_SAMPLE_RATE`)
- `session_id`: string (optional; forwarded back in replies)

### Segmentation algorithm (compatibility mode)

Behavior is intentionally aligned with the original core-side segmenter (Silero VAD timestamps + trailing-silence flush):

- Audio frames are appended to a per-stream buffer.
- The buffer is checked only when:
  - accumulated buffer duration is at least `BUFFER_CHECK_INTERVAL_S`, and
  - the concatenated audio duration (after resampling to `VAD_SAMPLE_RATE`) is at least `1.0s`, and
  - no other check is currently running for the same stream.
- On check, Silero VAD (`get_speech_timestamps`) is executed on the whole buffered audio with:
  - `threshold=VAD_THRESHOLD`
  - `sampling_rate=VAD_SAMPLE_RATE`
  - `min_speech_duration_ms=MIN_SPEECH_DURATION_MS`
  - `min_silence_duration_ms=MIN_SILENCE_DURATION_MS`
  - `max_speech_duration_s=MAX_SPEECH_DURATION_S`
  - `speech_pad_ms=SPEECH_PAD_MS`
- If no timestamps are detected and the buffered audio exceeds `5.0s`, the buffer is dropped (anti-OOM guard).
- A phrase flush happens when either:
  - stream receives `type=end` (forced flush), or
  - trailing silence after the last speech segment is at least `MIN_SILENCE_DURATION_MS`.
- On flush, **all** detected VAD segments are emitted as phrases and the stream buffer is cleared.

### Replies

For each flushed phrase, whisper publishes a JSON message to the derived output subject:

- `phrase_id`: UUID
- `text`: transcription text
- `duration`: phrase duration in seconds
- `transcribe_time`: seconds spent in the model
- `session_id`: included when present in input meta

### Configuration

All segmentation parameters are configurable via env vars (see `src_whisper/settings.py` and `src_whisper/env.example`).

### Manual test

Use `src_whisper/tools/whisper_probe.py` to publish a WAV as frames and collect replies:

```bash
python -m src_whisper.tools.whisper_probe ./test.wav --in-subject nats.asr.input.test123 --out-subject nats.asr.output.test123 --session-id test_session --timeout-s 10
```

If `nats://127.0.0.1:4222` is not reachable in your setup, you can use NATS WebSocket listener:

```bash
python -m src_whisper.tools.whisper_probe ./test.wav --nats-url ws://127.0.0.1:9222 --in-subject nats.asr.input.test123 --out-subject nats.asr.output.test123 --session-id test_session --timeout-s 10
```
