import asyncio
import logging
from uuid import uuid4, UUID

from aiohttp import web
from aiortc import RTCSessionDescription, RTCConfiguration, RTCPeerConnection

from opentelemetry import trace
from opentelemetry.trace import StatusCode

from .handle_track import handle_track
from src_core.utils.event_bus import event_log
from src_core.utils.validate import get_params, validate_sdp
from ..settings import STACK_SERVICE_NAME

logger = logging.getLogger("handle_offer")
tracer = trace.get_tracer(__name__)


async def handle_offer(request):
    # Child span under the auto-created aiohttp server span
    with tracer.start_as_current_span("core.offer") as span:
        span.set_attribute("http.route", "/core/offer")
        span.set_attribute("service.name", STACK_SERVICE_NAME)

        try:
            with tracer.start_as_current_span("offer.get_params") as sp:
                [params, err] = await get_params(request)
                sp.set_attribute("params.ok", err is None)
                if err is not None:
                    sp.set_attribute("error.message", str(err))
                    span.set_status(StatusCode.ERROR)
                    return web.json_response({"error": err}, status=400)

            sdp = params.get("sdp")
            with tracer.start_as_current_span("offer.validate_sdp") as sp:
                ok, err = validate_sdp(sdp)
                sp.set_attribute("sdp.valid", bool(ok))
                if not ok:
                    if err:
                        sp.set_attribute("error.message", str(err))
                    span.set_status(StatusCode.ERROR)
                    return web.json_response({"error": err}, status=400)

            with tracer.start_as_current_span("offer.connect") as sp:
                resp, error = await handle_offer_connect(request, params, parent_span=sp)

            if error:
                span.set_status(StatusCode.ERROR)
                span.set_attribute("offer.error", str(error))
                return web.json_response({"error": error}, status=400)

            span.set_attribute("offer.ok", True)
            return web.json_response(resp)

        except Exception as e:
            # Safety net: any unexpected crash gets recorded
            span.record_exception(e)
            span.set_status(StatusCode.ERROR)
            logger.error("Unhandled error in handle_offer", exc_info=True)
            return web.json_response({"error": "internal error"}, status=500)


async def handle_offer_connect(request, params, parent_span=None):
    with tracer.start_as_current_span("webrtc.offer_connect") as span:
        try:
            sdp = params.get("sdp")
            offer_type = params.get("type")
            raw_session_id = params.get("session_id")

            span.set_attribute("webrtc.offer.type", str(offer_type or ""))
            span.set_attribute("webrtc.session_id.raw_present", bool(raw_session_id))

            offer = RTCSessionDescription(sdp=sdp, type=offer_type)

            # --- Create PC & transceiver
            with tracer.start_as_current_span("webrtc.pc.create") as sp:
                conf = RTCConfiguration()
                conf.iceServers = []
                pc = RTCPeerConnection(configuration=conf)
                audio_transceiver = pc.addTransceiver("audio", direction="sendrecv")

                sp.set_attribute("webrtc.ice_servers.count", 0)
                sp.set_attribute("webrtc.transceiver.kind", "audio")
                sp.set_attribute("webrtc.transceiver.direction", "sendrecv")

            # --- Session id normalization
            with tracer.start_as_current_span("webrtc.session_id.normalize") as sp:
                session_id = str(uuid4())
                if isinstance(raw_session_id, str) and raw_session_id:
                    try:
                        session_id = str(UUID(raw_session_id))
                        sp.set_attribute("webrtc.session_id.valid_uuid", True)
                    except ValueError:
                        session_id = str(uuid4())
                        sp.set_attribute("webrtc.session_id.valid_uuid", False)

                setattr(pc, "_session_id", session_id)
                span.set_attribute("webrtc.session_id", session_id)

            # --- Track active pcs and cleanup dead ones
            with tracer.start_as_current_span("webrtc.pcs.maintain") as sp:
                pcs = request.app["pcs"]
                before = len(pcs)
                alive = {p for p in pcs if p.connectionState not in ("failed", "closed")}
                pcs.clear()
                pcs.update(alive)
                pcs.add(pc)

                sp.set_attribute("webrtc.pcs.before", before)
                sp.set_attribute("webrtc.pcs.after", len(pcs))
                sp.set_attribute("webrtc.pc.connection_state", getattr(pc, "connectionState", "unknown"))

            # --- event_log (can also be slow)
            with tracer.start_as_current_span("event_log.info.pc_created") as sp:
                sp.set_attribute("event.type", "log")
                sp.set_attribute("event.level", "info")
                sp.set_attribute("webrtc.pcs.total_active", len(request.app["pcs"]))
                await event_log(
                    "log",
                    "info",
                    {"text": f"WebRTC: Creating peer connection (total active: {len(request.app['pcs'])})"},
                    app=request.app,
                    service=STACK_SERVICE_NAME,
                )

            echo_ref = {"node": None}

            @pc.on("track")
            async def on_track(track):
                # This callback runs within the PC context; we still create a span
                with tracer.start_as_current_span("webrtc.on_track") as sp:
                    sp.set_attribute("webrtc.session_id", session_id)
                    sp.set_attribute("webrtc.track.kind", getattr(track, "kind", "unknown"))

                    with tracer.start_as_current_span("event_log.info.track_received") as spp:
                        spp.set_attribute("event.type", "log")
                        spp.set_attribute("event.level", "info")
                        await event_log(
                            "log",
                            "info",
                            {"text": f"WebRTC: Track received, kind={track.kind}"},
                            app=request.app,
                            service=STACK_SERVICE_NAME,
                        )

                    # Hand off to your track handler
                    with tracer.start_as_current_span("webrtc.handle_track") as spp:
                        await handle_track(
                            track,
                            pc,
                            audio_transceiver,
                            request.app,
                            echo_ref,
                            session_id=session_id,
                        )

            # --- Establish connection
            with tracer.start_as_current_span("webrtc.establish_connection") as sp:
                resp = await establish_connection(pc, offer, session_id=session_id)
                resp["session_id"] = session_id

            with tracer.start_as_current_span("event_log.info.established") as sp:
                sp.set_attribute("event.type", "log")
                sp.set_attribute("event.level", "info")
                await event_log(
                    "log",
                    "info",
                    {"text": "WebRTC: Connection established successfully"},
                    app=request.app,
                    service=STACK_SERVICE_NAME,
                )

            span.set_attribute("webrtc.ok", True)
            return resp, None

        except Exception as e:
            span.record_exception(e)
            span.set_status(StatusCode.ERROR)
            logger.error("Failed to process SDP offer", exc_info=True)

            with tracer.start_as_current_span("event_log.error.connection_failed") as sp:
                sp.set_attribute("event.type", "log")
                sp.set_attribute("event.level", "error")
                sp.set_attribute("error.message", str(e))
                await event_log(
                    "log",
                    "error",
                    {"text": f"WebRTC: Connection failed - {str(e)}"},
                    app=request.app,
                    service=STACK_SERVICE_NAME,
                )

            # Cleanup best-effort
            try:
                with tracer.start_as_current_span("webrtc.cleanup.replace_track_none"):
                    await audio_transceiver.sender.replaceTrack(None)
            except Exception:
                logger.debug("replaceTrack(None) failed or not needed", exc_info=True)

            try:
                with tracer.start_as_current_span("webrtc.cleanup.pc_close"):
                    await pc.close()
            except Exception:
                # don't mask the original failure
                pass

            return None, "failed to process offer"


async def establish_connection(pc, offer, session_id: str = ""):
    with tracer.start_as_current_span("webrtc.establish") as span:
        if session_id:
            span.set_attribute("webrtc.session_id", session_id)

        # Step 1: set remote description
        with tracer.start_as_current_span("webrtc.set_remote_description"):
            await pc.setRemoteDescription(offer)
        logger.debug("Remote description set")

        # Step 2: create answer
        with tracer.start_as_current_span("webrtc.create_answer"):
            answer = await pc.createAnswer()

        # Step 3: set local description
        with tracer.start_as_current_span("webrtc.set_local_description"):
            await pc.setLocalDescription(answer)
        logger.debug("Local description set")

        # Step 4: wait for ICE gathering
        with tracer.start_as_current_span("webrtc.ice_gathering.wait") as sp:
            loops = 0
            while getattr(pc, "iceGatheringState", None) != "complete":
                loops += 1
                await asyncio.sleep(0.05)
            sp.set_attribute("webrtc.ice_gathering.loops", loops)

        logger.debug("ICE gathering complete")

        # Return SDP
        local = pc.localDescription
        span.set_attribute("webrtc.local_description.type", getattr(local, "type", ""))
        # Не пихаем SDP в атрибуты. Оно длинное. Будешь плакать в Tempo.
        return {"sdp": local.sdp, "type": local.type}
