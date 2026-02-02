from __future__ import annotations

import asyncio
import json
import logging
import os
import time
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import nats
from aiohttp import WSMsgType, web

logger = logging.getLogger("whisper_webui")


def _src_whisper_dir() -> Path:
    return Path(__file__).resolve().parents[1]


def _out_dir() -> Path:
    return (_src_whisper_dir() / "out").resolve()


def _static_dir() -> Path:
    return (Path(__file__).resolve().parent / "static").resolve()


def _normalize_base_path(value: str) -> str:
    p = (value or "").strip()
    if not p or p == "/":
        return ""
    if not p.startswith("/"):
        p = "/" + p
    return p.rstrip("/")


def _validate_exact_subject(value: str, *, arg_name: str) -> str:
    s = (value or "").strip()
    if not s:
        raise ValueError(f"{arg_name} is required")
    if "*" in s or ">" in s:
        raise ValueError(f"{arg_name} must be an exact subject (wildcards are not allowed): {s}")
    if s.startswith(".") or s.endswith(".") or ".." in s:
        raise ValueError(f"{arg_name} is not a valid subject (empty token): {s}")
    return s


def build_wire_packet(meta: dict[str, Any], pcm_bytes: bytes | None) -> bytes:
    meta_bytes = json.dumps(meta, ensure_ascii=True).encode("utf-8")
    payload = len(meta_bytes).to_bytes(4, "big") + meta_bytes
    if pcm_bytes:
        payload += pcm_bytes
    return payload


@dataclass(slots=True)
class _ProbeRun:
    nc: nats.NATS
    sub: Any
    out_file: Path
    file_handle: Any
    replies_task: asyncio.Task
    run_id: str
    replies_received: int = 0
    frames_sent: int = 0
    last_reply_at: float = 0.0
    seq: int = 0


def _load_index_html(*, base_path: str) -> str:
    html_path = _static_dir() / "index.html"
    html = html_path.read_text(encoding="utf-8")
    default_nats_url = (os.getenv("WEBUI_NATS_DEFAULT_URL") or os.getenv("NATS_URL") or "nats://localhost:4222").strip()
    return (
        html.replace("__WEBUI_BASE_PATH__", base_path)
        .replace("__WEBUI_NATS_DEFAULT_URL__", default_nats_url)
    )


async def _ws_handler(request: web.Request) -> web.WebSocketResponse:
    ws = web.WebSocketResponse(autoping=True, heartbeat=30.0, max_msg_size=16 * 1024 * 1024)
    await ws.prepare(request)

    run: _ProbeRun | None = None
    replies_queue: asyncio.Queue[bytes] | None = None
    ended = False
    timeout_s = 10.0
    session_id = "webui"
    sample_rate = 16000
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
            await send_json(
                {
                    "type": "stats",
                    "frames_sent": run.frames_sent,
                    "replies_received": run.replies_received,
                    "run_id": run.run_id,
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

                msg_type = payload.get("type")
                if msg_type == "start":
                    if run:
                        await send_json({"type": "error", "error": "already_started"})
                        continue

                    try:
                        in_subject = _validate_exact_subject(payload.get("in_subject") or "", arg_name="in_subject")
                        out_subject = _validate_exact_subject(payload.get("out_subject") or "", arg_name="out_subject")
                    except ValueError as exc:
                        await send_json({"type": "error", "error": "invalid_subject", "details": str(exc)})
                        continue

                    nats_url = str(payload.get("nats_url") or "")
                    session_id = str(payload.get("session_id") or "webui")
                    sample_rate = int(payload.get("sample_rate") or 16000)
                    timeout_s = float(payload.get("timeout_s") or 10.0)
                    file_name = str(payload.get("file_name") or "audio.wav")

                    out_dir = _out_dir()
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
                        run_id=run_id,
                        last_reply_at=time.monotonic(),
                    )

                    await send_json(
                        {
                            "type": "stats",
                            "frames_sent": 0,
                            "replies_received": 0,
                            "run_id": run_id,
                        }
                    )
                    continue

                if msg_type == "end":
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

                    while True:
                        await asyncio.sleep(0.2)
                        if (time.monotonic() - run.last_reply_at) >= timeout_s:
                            break

                    await send_json(
                        {
                            "type": "done",
                            "frames_sent": run.frames_sent,
                            "replies_received": run.replies_received,
                            "run_id": run.run_id,
                        }
                    )
                    await shutdown()
                    await ws.close()
                    break

                if msg_type == "stop":
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
                            "run_id": run.run_id,
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

    html = _load_index_html(base_path=base)

    async def index(_: web.Request) -> web.Response:
        return web.Response(text=html, content_type="text/html", charset="utf-8")

    async def index_redirect(_: web.Request) -> web.Response:
        raise web.HTTPFound(location=f"{base}/")

    async def health(_: web.Request) -> web.Response:
        return web.json_response({"status": "ok"})

    async def get_run(request: web.Request) -> web.Response:
        run_id = str(request.match_info.get("run_id") or "")
        matches = list(_out_dir().glob(f"webui.{run_id}.*.jsonl"))
        if not matches:
            raise web.HTTPNotFound()
        return web.FileResponse(path=matches[0])

    if base:
        app.router.add_get(f"{base}", index_redirect)
    app.router.add_get(f"{base}/", index)
    app.router.add_get(f"{base}/health", health)
    app.router.add_get(f"{base}/runs/{{run_id}}", get_run)
    app.router.add_get(f"{base}/ws", _ws_handler)
    app.router.add_static(f"{base}/static/", path=str(_static_dir()), name="static")
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
