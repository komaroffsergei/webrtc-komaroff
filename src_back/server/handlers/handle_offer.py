import asyncio
import logging
import os

from aiohttp import web
from aiortc import RTCSessionDescription, RTCConfiguration, RTCPeerConnection

from .handle_track import handle_track
from ..utils.validate import get_params, validate_sdp
logger = logging.getLogger("handle_offer")


async def handle_offer(request):
    [params, err] = await get_params(request)
    if err is not None:
        return web.json_response({"error": err}, status=400)

    sdp = params.get("sdp")
    ok, err = validate_sdp(sdp)
    if not ok:
        return web.json_response({"error": err}, status=400)

    # call_manager = request.app["call_manager"]
    resp, error = await handle_offer_connect(request, params)

    if error:
        return web.json_response({"error": error}, status=400)

    return web.json_response(resp)


async def handle_offer_connect(request, params):
    sdp = params.get("sdp")
    offer_type = params.get("type")
    offer = RTCSessionDescription(sdp=sdp, type=offer_type)
    conf = RTCConfiguration()
    conf.iceServers = []
    pc = RTCPeerConnection(configuration=conf)
    audio_transceiver = pc.addTransceiver("audio", direction="sendrecv")

    pcs = {p for p in request.app["pcs"] if p.connectionState not in ("failed", "closed")}
    request.app["pcs"] = pcs
    pcs.add(pc)
    echo_ref = {"node": None}
    @pc.on("track")
    async def on_track(track):
        await handle_track(
            track, 
            pc, 
            audio_transceiver, 
            request.app,
            echo_ref
        )

    try:
        resp = await establish_connection(pc, offer)
        return resp, None
    except Exception:
        logger.error("Failed to process SDP offer", exc_info=True)
        try:
            await audio_transceiver.sender.replaceTrack(None)
        except Exception:
            logger.debug("replaceTrack(None) failed or not needed", exc_info=True)
        await pc.close()
        return None, "failed to process offer"



async def establish_connection(pc, offer):
    await pc.setRemoteDescription(offer)
    answer = await pc.createAnswer()
    await pc.setLocalDescription(answer)

    while getattr(pc, "iceGatheringState", None) != "complete":
        await asyncio.sleep(0.05)

    return {"sdp": pc.localDescription.sdp, "type": pc.localDescription.type}