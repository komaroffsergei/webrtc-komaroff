import asyncio
import logging
import json
from uuid import uuid4, UUID

from aiohttp import web
from aiortc import RTCSessionDescription, RTCConfiguration, RTCPeerConnection

from opentelemetry.trace import StatusCode

from otel import OTelBootstrap
from .handle_track import handle_track
from src_core.utils.event_bus import event_log
from src_core.utils.validate import get_params, validate_sdp
from ..settings import STACK_SERVICE_NAME

logger = logging.getLogger("handle_offer")


@OTelBootstrap.span(
    "offer.get_params",
    attributes_from_result=lambda r: {
        "params.ok": r[1] is None,
        "error.message": str(r[1]) if r[1] is not None else None,
    },
    status_from_result=lambda r: StatusCode.ERROR if r[1] is not None else None,
)
async def _offer_get_params(request):
    params, err = await get_params(request)
    return params, err


@OTelBootstrap.span(
    "offer.validate_sdp",
    attributes_from_result=lambda r: {
        "sdp.valid": bool(r[0]),
        "error.message": str(r[1]) if (not r[0] and r[1]) else None,
    },
    status_from_result=lambda r: StatusCode.ERROR if not r[0] else None,
)
def _offer_validate_sdp(sdp):
    ok, err = validate_sdp(sdp)
    return ok, err


@OTelBootstrap.span(
    "offer.connect",
    record_exceptions_from_result=lambda r: (r[2],) if r[2] else (),
    status_from_result=lambda r: StatusCode.ERROR if r[1] is not None else None,
)
async def _offer_connect(request, params):
    return await handle_offer_connect(request, params, parent_span=None)


@OTelBootstrap.span(
    "webrtc.pc.create",
    attributes={
        "webrtc.ice_servers.count": 0,
        "webrtc.transceiver.kind": "audio",
        "webrtc.transceiver.direction": "sendrecv",
    },
)
def _webrtc_pc_create():
    conf = RTCConfiguration()
    conf.iceServers = []
    pc = RTCPeerConnection(configuration=conf)
    audio_transceiver = pc.addTransceiver("audio", direction="sendrecv")
    return pc, audio_transceiver


@OTelBootstrap.span(
    "webrtc.session_id.normalize",
    attributes_from_result=lambda r: {
        "webrtc.session_id.valid_uuid": r[1] if r[1] is not None else None,
    },
)
def _webrtc_normalize_session_id(raw_session_id):
    session_id = str(uuid4())
    valid_uuid: bool | None = None
    if isinstance(raw_session_id, str) and raw_session_id:
        try:
            session_id = str(UUID(raw_session_id))
            valid_uuid = True
        except ValueError:
            session_id = str(uuid4())
            valid_uuid = False
    return session_id, valid_uuid


@OTelBootstrap.span(
    "webrtc.pcs.maintain",
    attributes_from_result=lambda attrs: attrs,
)
def _webrtc_pcs_maintain(app, pc):
    pcs = app["pcs"]
    before = len(pcs)
    alive = {p for p in pcs if p.connectionState not in ("failed", "closed")}
    pcs.clear()
    pcs.update(alive)
    pcs.add(pc)
    return {
        "webrtc.pcs.before": before,
        "webrtc.pcs.after": len(pcs),
        "webrtc.pc.connection_state": getattr(pc, "connectionState", "unknown"),
    }


@OTelBootstrap.span(
    "event_log.info.pc_created",
    attributes_from_args=lambda app: {
        "event.type": "log",
        "event.level": "info",
        "webrtc.pcs.total_active": len(app["pcs"]),
    },
)
async def _event_log_pc_created(app):
    await event_log(
        "log",
        "info",
        {"text": f"WebRTC: Creating peer connection (total active: {len(app['pcs'])})"},
        app=app,
        service=STACK_SERVICE_NAME,
    )


@OTelBootstrap.span(
    "event_log.info.track_received",
    attributes={"event.type": "log", "event.level": "info"},
)
async def _event_log_track_received(app, *, track_kind: str):
    await event_log(
        "log",
        "info",
        {"text": f"WebRTC: Track received, kind={track_kind}"},
        app=app,
        service=STACK_SERVICE_NAME,
    )


@OTelBootstrap.span("webrtc.handle_track")
async def _webrtc_handle_track(track, pc, audio_transceiver, app, echo_ref, *, session_id: str):
    await handle_track(
        track,
        pc,
        audio_transceiver,
        app,
        echo_ref,
        session_id=session_id,
    )


@OTelBootstrap.span("webrtc.establish_connection")
async def _webrtc_establish_connection(pc, offer, *, session_id: str):
    resp = await establish_connection(pc, offer, session_id=session_id)
    resp["session_id"] = session_id
    return resp


@OTelBootstrap.span(
    "event_log.info.established",
    attributes={"event.type": "log", "event.level": "info"},
)
async def _event_log_established(app):
    await event_log(
        "log",
        "info",
        {"text": "WebRTC: Connection established successfully"},
        app=app,
        service=STACK_SERVICE_NAME,
    )


@OTelBootstrap.span(
    "event_log.error.connection_failed",
    attributes_from_args=lambda app, exc: {
        "event.type": "log",
        "event.level": "error",
        "error.message": str(exc),
    },
)
async def _event_log_connection_failed(app, exc: Exception) -> None:
    await event_log(
        "log",
        "error",
        {"text": f"WebRTC: Connection failed - {str(exc)}"},
        app=app,
        service=STACK_SERVICE_NAME,
    )


@OTelBootstrap.span("webrtc.cleanup.replace_track_none")
async def _cleanup_replace_track_none(audio_transceiver) -> None:
    await audio_transceiver.sender.replaceTrack(None)


@OTelBootstrap.span("webrtc.cleanup.pc_close")
async def _cleanup_pc_close(pc) -> None:
    await pc.close()


def _attrs_from_offer_response(resp: web.StreamResponse):
    status = getattr(resp, "status", 200)
    attrs = {"offer.ok": status < 400}

    body = getattr(resp, "body", None)
    if not body:
        return attrs
    try:
        data = json.loads(body.decode("utf-8"))
    except Exception:
        return attrs
    if isinstance(data, dict) and "error" in data:
        attrs["offer.error"] = str(data.get("error"))
    return attrs


@OTelBootstrap.span(
    "core.offer",
    attributes={"http.route": "/core/offer", "service.name": STACK_SERVICE_NAME},
    attributes_from_result=_attrs_from_offer_response,
    set_status_from_http_response=True,
)
async def handle_offer(request):
    try:
        params, err = await _offer_get_params(request)
        if err is not None:
            return web.json_response({"error": err}, status=400)

        sdp = params.get("sdp")
        ok, err = _offer_validate_sdp(sdp)
        if not ok:
            return web.json_response({"error": err}, status=400)

        resp, error, _exc = await _offer_connect(request, params)
        if error is not None:
            return web.json_response({"error": error}, status=400)

        return web.json_response(resp)

    except web.HTTPException:
        raise
    except Exception as exc:
        logger.error("Unhandled error in handle_offer", exc_info=True)
        raise web.HTTPInternalServerError(
            text=json.dumps({"error": "internal error"}),
            content_type="application/json",
        ) from exc


@OTelBootstrap.span(
    "webrtc.offer_connect",
    attributes_from_args=lambda request, params, parent_span=None: {
        "webrtc.offer.type": str((params or {}).get("type") or ""),
        "webrtc.session_id.raw_present": bool((params or {}).get("session_id")),
    },
    attributes_from_result=lambda r: {
        "webrtc.ok": r[1] is None,
        "webrtc.session_id": (r[0] or {}).get("session_id") if isinstance(r[0], dict) else None,
    },
    record_exceptions_from_result=lambda r: (r[2],) if r[2] else (),
    status_from_result=lambda r: StatusCode.ERROR if r[1] is not None else None,
)
async def handle_offer_connect(request, params, parent_span=None):
    pc = None
    audio_transceiver = None
    captured_exc: Exception | None = None

    try:
        sdp = params.get("sdp")
        offer_type = params.get("type")
        raw_session_id = params.get("session_id")

        offer = RTCSessionDescription(sdp=sdp, type=offer_type)

        pc, audio_transceiver = _webrtc_pc_create()

        session_id, _valid_uuid = _webrtc_normalize_session_id(raw_session_id)
        setattr(pc, "_session_id", session_id)

        _webrtc_pcs_maintain(request.app, pc)
        await _event_log_pc_created(request.app)

        echo_ref = {"node": None}

        @pc.on("track")
        @OTelBootstrap.span(
            "webrtc.on_track",
            attributes_from_args=lambda track: {
                "webrtc.session_id": session_id,
                "webrtc.track.kind": getattr(track, "kind", "unknown"),
            },
        )
        async def on_track(track):
            await _event_log_track_received(request.app, track_kind=getattr(track, "kind", "unknown"))
            await _webrtc_handle_track(
                track,
                pc,
                audio_transceiver,
                request.app,
                echo_ref,
                session_id=session_id,
            )

        resp = await _webrtc_establish_connection(pc, offer, session_id=session_id)
        await _event_log_established(request.app)

        return resp, None, None

    except Exception as exc:
        logger.error("Failed to process SDP offer", exc_info=True)
        captured_exc = exc

        try:
            await _event_log_connection_failed(request.app, exc)
        except Exception:
            # Keep the original error as the main reason for failure.
            logger.debug("Failed to log connection failure to event bus", exc_info=True)

        # Cleanup best-effort
        if audio_transceiver is not None:
            try:
                await _cleanup_replace_track_none(audio_transceiver)
            except Exception:
                logger.debug("replaceTrack(None) failed or not needed", exc_info=True)

        if pc is not None:
            try:
                await _cleanup_pc_close(pc)
            except Exception:
                # Do not mask the original failure.
                pass

        return None, "failed to process offer", captured_exc


@OTelBootstrap.span("webrtc.set_remote_description")
async def _webrtc_set_remote_description(pc, offer) -> None:
    await pc.setRemoteDescription(offer)


@OTelBootstrap.span("webrtc.create_answer")
async def _webrtc_create_answer(pc):
    return await pc.createAnswer()


@OTelBootstrap.span("webrtc.set_local_description")
async def _webrtc_set_local_description(pc, answer) -> None:
    await pc.setLocalDescription(answer)


@OTelBootstrap.span(
    "webrtc.ice_gathering.wait",
    attributes_from_result=lambda loops: {"webrtc.ice_gathering.loops": loops},
)
async def _webrtc_ice_gathering_wait(pc):
    loops = 0
    while getattr(pc, "iceGatheringState", None) != "complete":
        loops += 1
        await asyncio.sleep(0.05)
    return loops


@OTelBootstrap.span(
    "webrtc.establish",
    attributes_from_args=lambda pc, offer, session_id="": {"webrtc.session_id": session_id} if session_id else {},
    attributes_from_result=lambda r: {"webrtc.local_description.type": r.get("type", "")} if isinstance(r, dict) else {},
)
async def establish_connection(pc, offer, session_id: str = ""):
    await _webrtc_set_remote_description(pc, offer)
    logger.debug("Remote description set")

    answer = await _webrtc_create_answer(pc)

    await _webrtc_set_local_description(pc, answer)
    logger.debug("Local description set")

    await _webrtc_ice_gathering_wait(pc)
    logger.debug("ICE gathering complete")

    local = pc.localDescription
    # Do not attach SDP to span attributes: it's huge and will bloat traces.
    return {"sdp": local.sdp, "type": local.type}
