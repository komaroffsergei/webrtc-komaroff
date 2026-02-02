from __future__ import annotations

import asyncio
import json
import logging
import time
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import nats
from aiohttp import web, WSMsgType

from src_whisper.tools.whisper_probe import build_wire_packet, _validate_exact_subject

logger = logging.getLogger("whisper_webui")


def _default_out_dir() -> Path:
    return (Path(__file__).resolve().parent / "out").resolve()


def _normalize_base_path(value: str) -> str:
    p = (value or "").strip()
    if not p or p == "/":
        return ""
    if not p.startswith("/"):
        p = "/" + p
    return p.rstrip("/")


INDEX_HTML_TEMPLATE = """<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8"/>
  <meta name="viewport" content="width=device-width, initial-scale=1"/>
  <title>src_whisper WebUI</title>
  <style>
    :root { color-scheme: light dark; }
    body { font-family: system-ui, -apple-system, Segoe UI, Roboto, Arial, sans-serif; margin: 16px; max-width: 980px; }
    h1 { font-size: 18px; margin: 0 0 12px; }
    label { display: block; font-size: 12px; margin: 10px 0 4px; }
    input, select, button, textarea { width: 100%; box-sizing: border-box; padding: 8px; }
    .row { display: grid; grid-template-columns: 1fr 1fr; gap: 12px; }
    .row3 { display: grid; grid-template-columns: 1fr 1fr 1fr; gap: 12px; }
    .actions { display: grid; grid-template-columns: 1fr 1fr 1fr; gap: 12px; margin-top: 12px; }
    pre { white-space: pre-wrap; word-break: break-word; background: rgba(127,127,127,.12); padding: 10px; border-radius: 8px; }
    .muted { opacity: 0.75; font-size: 12px; }
    .ok { color: #0a7; }
    .err { color: #d33; }
  </style>
</head>
<body>
  <h1>src_whisper WebUI</h1>
  <div class="muted">Uploads stay in your browser. Audio is decoded and split into frames client-side.</div>

  <label>WAV file</label>
  <input id="wav" type="file" accept="audio/wav"/>

  <div class="row">
    <div>
      <label>NATS URL</label>
      <input id="natsUrl" type="text" value="ws://127.0.0.1:9222"/>
    </div>
    <div>
      <label>Session ID</label>
      <input id="sessionId" type="text" value="s1"/>
    </div>
  </div>

  <div class="row">
    <div>
      <label>In subject</label>
      <input id="inSubject" type="text" value="nats.asr.input.test123"/>
    </div>
    <div>
      <label>Out subject</label>
      <input id="outSubject" type="text" value="nats.asr.output.test123"/>
    </div>
  </div>

  <div class="row3">
    <div>
      <label>Sample rate</label>
      <input id="sampleRate" type="number" value="16000" min="8000" step="1000"/>
    </div>
    <div>
      <label>Frame (ms)</label>
      <input id="frameMs" type="number" value="20" min="10" step="10"/>
    </div>
    <div>
      <label>Reply timeout (s)</label>
      <input id="timeoutS" type="number" value="10" min="1" step="1"/>
    </div>
  </div>

  <div class="actions">
    <button id="start">Start</button>
    <button id="stop" disabled>Stop</button>
    <button id="genToken">Generate token</button>
  </div>

  <label>Status</label>
  <pre id="status"></pre>

  <label>Replies (JSON)</label>
  <pre id="replies"></pre>

<script>
window.__WEBUI_BASE_PATH__ = __WEBUI_BASE_PATH_VALUE__;
const statusEl = document.getElementById('status');
const repliesEl = document.getElementById('replies');
const startBtn = document.getElementById('start');
const stopBtn = document.getElementById('stop');
const genBtn = document.getElementById('genToken');

function basePath() {
  return (window.__WEBUI_BASE_PATH__ || '');
}

function wsUrl() {
  const proto = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
  return proto + '//' + window.location.host + basePath() + '/ws';
}

function setStatus(text, cls='') {
  statusEl.className = cls;
  statusEl.textContent = text;
}

function appendReply(obj) {
  const line = JSON.stringify(obj);
  repliesEl.textContent = (repliesEl.textContent ? repliesEl.textContent + '\\n' : '') + line;
}

function sleep(ms) { return new Promise(r => setTimeout(r, ms)); }

function resampleLinear(input, inRate, outRate) {
  if (inRate === outRate) return input;
  const ratio = outRate / inRate;
  const outLen = Math.max(1, Math.floor(input.length * ratio));
  const out = new Float32Array(outLen);
  for (let i = 0; i < outLen; i++) {
    const t = i / ratio;
    const idx = Math.floor(t);
    const frac = t - idx;
    const s0 = input[idx] || 0;
    const s1 = input[idx + 1] || s0;
    out[i] = s0 + (s1 - s0) * frac;
  }
  return out;
}

function floatToPcm16leFrame(samples, offset, frameSamples) {
  const buf = new ArrayBuffer(frameSamples * 2);
  const view = new DataView(buf);
  for (let i = 0; i < frameSamples; i++) {
    const v = samples[offset + i] || 0;
    const clamped = Math.max(-1, Math.min(1, v));
    const s = clamped < 0 ? Math.round(clamped * 32768) : Math.round(clamped * 32767);
    view.setInt16(i * 2, s, true);
  }
  return buf;
}

async function decodeWavToMonoFloat32(file) {
  const arrayBuffer = await file.arrayBuffer();
  const ac = new (window.AudioContext || window.webkitAudioContext)();
  const audioBuf = await ac.decodeAudioData(arrayBuffer.slice(0));
  const ch = audioBuf.numberOfChannels;
  const len = audioBuf.length;
  let mono = new Float32Array(len);
  for (let c = 0; c < ch; c++) {
    const data = audioBuf.getChannelData(c);
    for (let i = 0; i < len; i++) mono[i] += data[i];
  }
  for (let i = 0; i < len; i++) mono[i] /= Math.max(1, ch);
  return { samples: mono, sampleRate: audioBuf.sampleRate };
}

function randomToken() {
  const a = crypto.getRandomValues(new Uint8Array(16));
  const hex = Array.from(a).map(b => b.toString(16).padStart(2,'0')).join('');
  return [hex.slice(0,8), hex.slice(8,12), hex.slice(12,16), hex.slice(16,20), hex.slice(20)].join('-');
}

genBtn.addEventListener('click', () => {
  const t = randomToken();
  document.getElementById('inSubject').value = 'nats.asr.input.' + t;
  document.getElementById('outSubject').value = 'nats.asr.output.' + t;
});

let ws = null;
let stopped = false;

stopBtn.addEventListener('click', () => {
  stopped = true;
  try { ws && ws.close(); } catch (_) {}
});

startBtn.addEventListener('click', async () => {
  const file = document.getElementById('wav').files[0];
  if (!file) { setStatus('Select a WAV file first', 'err'); return; }

  const natsUrl = document.getElementById('natsUrl').value.trim();
  const inSubject = document.getElementById('inSubject').value.trim();
  const outSubject = document.getElementById('outSubject').value.trim();
  const sessionId = document.getElementById('sessionId').value.trim();
  const sampleRate = parseInt(document.getElementById('sampleRate').value, 10);
  const frameMs = parseInt(document.getElementById('frameMs').value, 10);
  const timeoutS = parseFloat(document.getElementById('timeoutS').value);

  repliesEl.textContent = '';
  stopped = false;
  startBtn.disabled = true;
  stopBtn.disabled = false;

  setStatus('Decoding WAV in browser...', '');
  let decoded;
  try {
    decoded = await decodeWavToMonoFloat32(file);
  } catch (e) {
    setStatus('Failed to decode WAV in browser: ' + (e && e.message ? e.message : String(e)), 'err');
    startBtn.disabled = false;
    stopBtn.disabled = true;
    return;
  }
  const resampled = resampleLinear(decoded.samples, decoded.sampleRate, sampleRate);
  const frameSamples = Math.round(sampleRate * frameMs / 1000);
  const totalFrames = Math.ceil(resampled.length / frameSamples);

  ws = new WebSocket(wsUrl());
  ws.binaryType = 'arraybuffer';

  ws.onmessage = (ev) => {
    if (typeof ev.data === 'string') {
      let msg;
      try { msg = JSON.parse(ev.data); } catch (_) { return; }
      if (msg.type === 'reply') appendReply(msg.data);
      if (msg.type === 'stats') setStatus(JSON.stringify(msg, null, 2), 'ok');
      if (msg.type === 'done') setStatus(JSON.stringify(msg, null, 2), 'ok');
      if (msg.type === 'error') setStatus(JSON.stringify(msg, null, 2), 'err');
      return;
    }
  };

  ws.onclose = () => {
    startBtn.disabled = false;
    stopBtn.disabled = true;
  };

  ws.onerror = () => {
    setStatus('WebSocket error', 'err');
  };

  await new Promise((resolve) => ws.onopen = resolve);
  ws.send(JSON.stringify({
    type: 'start',
    nats_url: natsUrl,
    in_subject: inSubject,
    out_subject: outSubject,
    session_id: sessionId,
    sample_rate: sampleRate,
    frame_ms: frameMs,
    timeout_s: timeoutS,
    file_name: file.name,
  }));

  setStatus('Sending frames...', '');
  for (let i = 0; i < totalFrames; i++) {
    if (stopped) break;
    const off = i * frameSamples;
    const buf = floatToPcm16leFrame(resampled, off, frameSamples);
    ws.send(buf);
    if (i % 20 === 0) {
      setStatus(JSON.stringify({ type: 'sending', frames_sent: i, total_frames: totalFrames }, null, 2));
      while (ws.bufferedAmount > 4 * 1024 * 1024) await sleep(20);
      await sleep(0);
    }
  }

  if (!stopped) ws.send(JSON.stringify({ type: 'end' }));
});
</script>
</body>
</html>
"""


@dataclass(slots=True)
class _ProbeRun:
    nc: nats.NATS
    sub: Any
    out_file: Path
    file_handle: Any
    replies_task: asyncio.Task
    replies_received: int = 0
    frames_sent: int = 0
    last_reply_at: float = 0.0
    seq: int = 0


async def _ws_handler(request: web.Request) -> web.WebSocketResponse:
    ws = web.WebSocketResponse(autoping=True, heartbeat=30.0, max_msg_size=16 * 1024 * 1024)
    await ws.prepare(request)

    run: _ProbeRun | None = None
    replies_queue: asyncio.Queue[bytes] | None = None
    ended = False
    timeout_s = 10.0
    session_id = "webui"
    sample_rate = 16000
    frame_ms = 20
    in_subject = ""
    out_subject = ""
    file_name = "audio.wav"

    async def send_json(payload: dict[str, Any]) -> None:
        try:
            await ws.send_str(json.dumps(payload, ensure_ascii=False))
        except Exception:
            return

    async def shutdown() -> None:
        nonlocal run
        if not run:
            return
        try:
            await run.sub.unsubscribe()
        except Exception:
            pass
        try:
            await run.nc.drain()
        except Exception:
            try:
                await run.nc.close()
            except Exception:
                pass
        try:
            run.replies_task.cancel()
            await asyncio.gather(run.replies_task, return_exceptions=True)
        except Exception:
            pass
        try:
            run.file_handle.close()
        except Exception:
            pass
        run = None

    async def pump_replies() -> None:
        assert replies_queue is not None
        assert run is not None
        while True:
            data = await replies_queue.get()
            try:
                obj = json.loads(data.decode("utf-8", errors="replace"))
            except Exception:
                continue
            run.replies_received += 1
            run.last_reply_at = time.monotonic()
            try:
                run.file_handle.write(json.dumps(obj, ensure_ascii=False) + "\n")
                run.file_handle.flush()
            except Exception:
                pass
            await send_json({"type": "reply", "data": obj})
            if run.replies_received % 1 == 0:
                await send_json(
                    {
                        "type": "stats",
                        "frames_sent": run.frames_sent,
                        "replies_received": run.replies_received,
                        "out_file": str(run.out_file),
                    }
                )

    try:
        async for msg in ws:
            if msg.type == WSMsgType.TEXT:
                try:
                    payload = json.loads(msg.data)
                except Exception:
                    await send_json({"type": "error", "error": "invalid_json"})
                    continue

                if payload.get("type") == "start":
                    if run:
                        await send_json({"type": "error", "error": "already_started"})
                        continue

                    try:
                        in_subject = _validate_exact_subject(payload.get("in_subject") or "", arg_name="in_subject")
                        out_subject = _validate_exact_subject(payload.get("out_subject") or "", arg_name="out_subject")
                    except SystemExit as exc:
                        await send_json({"type": "error", "error": "invalid_subject", "details": str(exc)})
                        continue

                    nats_url = str(payload.get("nats_url") or "")
                    session_id = str(payload.get("session_id") or "webui")
                    sample_rate = int(payload.get("sample_rate") or 16000)
                    frame_ms = int(payload.get("frame_ms") or 20)
                    timeout_s = float(payload.get("timeout_s") or 10.0)
                    file_name = str(payload.get("file_name") or "audio.wav")

                    out_dir = _default_out_dir()
                    out_dir.mkdir(parents=True, exist_ok=True)
                    run_id = str(uuid.uuid4())
                    safe_name = Path(file_name).name.replace("/", "_")
                    out_file = out_dir / f"webui.{run_id}.{safe_name}.{session_id}.jsonl"
                    f = out_file.open("w", encoding="utf-8")

                    nc = await nats.connect(
                        servers=[nats_url],
                        max_reconnect_attempts=0,
                        connect_timeout=2.0,
                    )

                    replies_queue = asyncio.Queue()

                    async def _on_reply(nmsg):
                        assert replies_queue is not None
                        await replies_queue.put(bytes(nmsg.data))

                    sub = await nc.subscribe(out_subject, cb=_on_reply)
                    run = _ProbeRun(
                        nc=nc,
                        sub=sub,
                        out_file=out_file,
                        file_handle=f,
                        replies_task=asyncio.create_task(pump_replies()),
                        last_reply_at=time.monotonic(),
                    )

                    await send_json(
                        {
                            "type": "stats",
                            "frames_sent": 0,
                            "replies_received": 0,
                            "out_file": str(out_file),
                        }
                    )
                    continue

                if payload.get("type") == "end":
                    if not run or ended:
                        continue
                    ended = True
                    meta_end = {
                        "type": "end",
                        "seq": run.seq,
                        "sample_rate": sample_rate,
                        "sample_width": 2,
                        "channels": 1,
                        "session_id": session_id,
                    }
                    await run.nc.publish(in_subject, build_wire_packet(meta_end, None))

                    # Wait for silence (no replies) after end, then finish.
                    while True:
                        await asyncio.sleep(0.2)
                        if (time.monotonic() - run.last_reply_at) >= timeout_s:
                            break

                    await send_json(
                        {
                            "type": "done",
                            "frames_sent": run.frames_sent,
                            "replies_received": run.replies_received,
                            "out_file": str(run.out_file),
                        }
                    )
                    await shutdown()
                    await ws.close()
                    break

                if payload.get("type") == "stop":
                    await shutdown()
                    await ws.close()
                    break

            if msg.type == WSMsgType.BINARY:
                if not run or ended:
                    continue
                run.seq += 1
                run.frames_sent += 1
                meta = {
                    "type": "frame",
                    "seq": run.seq,
                    "sample_rate": sample_rate,
                    "sample_width": 2,
                    "channels": 1,
                    "session_id": session_id,
                }
                await run.nc.publish(in_subject, build_wire_packet(meta, bytes(msg.data)))
                if run.frames_sent % 50 == 0:
                    await send_json(
                        {
                            "type": "stats",
                            "frames_sent": run.frames_sent,
                            "replies_received": run.replies_received,
                            "out_file": str(run.out_file),
                        }
                    )

            if msg.type in (WSMsgType.ERROR, WSMsgType.CLOSE, WSMsgType.CLOSING, WSMsgType.CLOSED):
                break

    except Exception as exc:
        logger.exception("WebUI WS session failed: %s", exc)
        try:
            await send_json({"type": "error", "error": "server_error", "details": str(exc)})
        except Exception:
            pass
    finally:
        await shutdown()

    return ws


def create_app(*, base_path: str) -> web.Application:
    base = _normalize_base_path(base_path)
    app = web.Application(client_max_size=64 * 1024 * 1024)

    html = INDEX_HTML_TEMPLATE.replace("__WEBUI_BASE_PATH_VALUE__", json.dumps(base, ensure_ascii=True))

    async def index(_: web.Request) -> web.Response:
        return web.Response(text=html, content_type="text/html", charset="utf-8")

    async def index_redirect(_: web.Request) -> web.Response:
        raise web.HTTPFound(location=f"{base}/")

    async def health(_: web.Request) -> web.Response:
        return web.json_response({"status": "ok"})

    async def get_run(request: web.Request) -> web.Response:
        run_id = str(request.match_info.get("run_id") or "")
        out_dir = _default_out_dir()
        matches = list(out_dir.glob(f"webui.{run_id}.*.jsonl"))
        if not matches:
            raise web.HTTPNotFound()
        return web.FileResponse(path=matches[0])

    if base:
        app.router.add_get(f"{base}", index_redirect)
    app.router.add_get(f"{base}/", index)
    app.router.add_get(f"{base}/health", health)
    app.router.add_get(f"{base}/runs/{{run_id}}", get_run)
    app.router.add_get(f"{base}/ws", _ws_handler)
    return app


async def run_webui(*, host: str, port: int, base_path: str) -> None:
    app = create_app(base_path=base_path)
    runner = web.AppRunner(app, access_log=None)
    await runner.setup()
    site = web.TCPSite(runner, host=host, port=int(port))
    await site.start()
    logger.info("WebUI listening on %s:%s (base_path=%s)", host, port, base_path or "/")
    try:
        await asyncio.Event().wait()
    finally:
        await runner.cleanup()
