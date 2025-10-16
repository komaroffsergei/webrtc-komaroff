import asyncio
import logging
import os

from aiortc import RTCPeerConnection, RTCSessionDescription
from aiohttp import web

from .processors.graph import AudioGraph
from .processors import TrackSourceNode, EchoTrackNode, LossFillerNode
from .utils.config import STATIC_DIR
from .utils.pc_lifecycle import attach_pc_lifecycle
from .utils.validate import get_params, validate_sdp

logger = logging.getLogger("webrtc")
MAX_SDP_SIZE = 1_000_000


async def handle_offer(request):
    [params, err] = await get_params(request)
    if err is not None:
        return web.json_response({"error": err}, status=400)

    sdp = params.get("sdp")
    offer_type = params.get("type")

    ok, err = validate_sdp(sdp)
    if not ok:
        return web.json_response({"error": err}, status=400)

    offer = RTCSessionDescription(sdp=sdp, type=offer_type)

    pc = RTCPeerConnection()
    audio_transceiver = pc.addTransceiver("audio", direction="sendrecv")

    pcs = {p for p in request.app["pcs"] if p.connectionState not in ("failed", "closed")}
    request.app["pcs"] = pcs
    pcs.add(pc)

    logger.info("PC created and audio transceiver added (sendrecv)")
    if logger.isEnabledFor(logging.DEBUG):
        logger.debug(f"Active PCs: {len(pcs)}")

    graph = AudioGraph()
    echo_ref = {"node": None}

    attach_pc_lifecycle(pc, request.app, graph, audio_transceiver, echo_ref)

    @pc.on("track")
    async def on_track(track):
        logger.info(f"on_track: received kind={track.kind}")
        if track.kind == "audio":
            source = graph.add(TrackSourceNode(
                track,
                frame_duration_ms=10,
                target_rate=48000,
                target_channels=1,
                target_output_format='s16'
            ))

            filler = graph.add(LossFillerNode(source, latency_budget_ms=100, backlog_leave_frames=1, fill_mode="silence"))

            echo = EchoTrackNode(filler)
            audio_transceiver.sender.replaceTrack(echo)
            echo_ref["node"] = echo
            logger.info("Echo attached")

            asyncio.create_task(graph.start())
            logger.info("Audio graph started")

    try:
        await pc.setRemoteDescription(offer)
        answer = await pc.createAnswer()
        await pc.setLocalDescription(answer)
    except Exception:
        logger.error("Failed to process SDP offer", exc_info=True)
        try:
            await audio_transceiver.sender.replaceTrack(None)
        except Exception:
            logger.debug("replaceTrack(None) failed or not needed", exc_info=True)
        await pc.close()
        return web.json_response({"error": "failed to process offer"}, status=400)

    return web.json_response({
        "sdp": pc.localDescription.sdp,
        "type": pc.localDescription.type
    })


async def handle_index(request):
    logger.debug("Serving index.html")
    return web.FileResponse(os.path.join(STATIC_DIR, "index.html"))


async def handle_shutdown(app):
    logger.info("Shutdown: closing all peer connections")
    pcs = list(app["pcs"])
    await asyncio.gather(*(pc.close() for pc in pcs), return_exceptions=True)
    app["pcs"].clear()
    logger.info("Shutdown complete")