import asyncio
from aiohttp import web

from opentelemetry.trace import StatusCode

from otel import OTelBootstrap


@OTelBootstrap.span(
    "webrtc.live_asr.cancel_tasks",
    attributes_from_args=lambda app: {
        "webrtc.live_asr.sessions": len(app.get("live_asr_sessions", {})),
    },
)
async def _cancel_live_asr_tasks(app: web.Application) -> None:
    sessions = app.get("live_asr_sessions", {})
    tasks = []
    if isinstance(sessions, dict):
        for state in sessions.values():
            task = getattr(state, "commit_task", None)
            if task and not task.done():
                task.cancel()
                tasks.append(task)
    if tasks:
        await asyncio.gather(*tasks, return_exceptions=True)
    if isinstance(sessions, dict):
        sessions.clear()


@OTelBootstrap.span(
    "webrtc.pcs.close_all",
    attributes_from_result=lambda errors: {"webrtc.pcs.close.errors": len(errors)},
    record_exceptions_from_result=lambda errors: errors[:1],
    status_from_result=lambda errors: StatusCode.ERROR if errors else None,
)
async def _pcs_close_all(pcs):
    results = await asyncio.gather(*(pc.close() for pc in pcs), return_exceptions=True)
    return [r for r in results if isinstance(r, Exception)]


@OTelBootstrap.span("webrtc.pcs.clear")
def _pcs_clear(app: web.Application) -> None:
    if "pcs" in app:
        app["pcs"].clear()


@OTelBootstrap.span(
    "otel.shutdown",
    attributes_from_args=lambda otel_obj: {"otel.present": otel_obj is not None},
)
def _otel_shutdown(otel_obj) -> None:
    if otel_obj is not None:
        otel_obj.shutdown()


@OTelBootstrap.span(
    "app.shutdown",
    attributes_from_args=lambda app: {"webrtc.pcs.count": len(app.get("pcs", []))},
    ok_attributes={"shutdown.ok": True},
)
async def handle_shutdown(app: web.Application):
    pcs = list(app.get("pcs", []))
    await _cancel_live_asr_tasks(app)
    await _pcs_close_all(pcs)
    _pcs_clear(app)
    _otel_shutdown(app.get("otel"))
