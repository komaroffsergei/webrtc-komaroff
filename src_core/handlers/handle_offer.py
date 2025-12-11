import asyncio
import logging

from aiohttp import web
from aiortc import RTCSessionDescription, RTCConfiguration, RTCPeerConnection

from .handle_track import handle_track
from src_core.utils.event_bus import event_log
from src_core.utils.validate import get_params, validate_sdp
logger = logging.getLogger("handle_offer")


async def handle_offer(request):
    [params, err] = await get_params(request)
    if err is not None:
        return web.json_response({"error": err}, status=400)

    sdp = params.get("sdp")
    ok, err = validate_sdp(sdp)
    if not ok:
        return web.json_response({"error": err}, status=400)

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

    pcs = request.app["pcs"]
    alive = {p for p in pcs if p.connectionState not in ("failed", "closed")}
    pcs.clear()
    pcs.update(alive)
    pcs.add(pc)
    await event_log(
        f"WebRTC: Creating peer connection (total active: {len(pcs)})",
        level="info",
    )
    
    echo_ref = {"node": None}
    @pc.on("track")
    async def on_track(track):
        await event_log(f"WebRTC: Track received, kind={track.kind}", level="info")
        await handle_track(
            track, 
            pc, 
            audio_transceiver, 
            request.app,
            echo_ref
        )

    try:
        resp = await establish_connection(pc, offer)
        await event_log("WebRTC: Connection established successfully", level="info")
        return resp, None
    except Exception as e:
        logger.error("Failed to process SDP offer", exc_info=True)
        await event_log(f"WebRTC: Connection failed - {str(e)}", level="error")
        try:
            await audio_transceiver.sender.replaceTrack(None)
        except Exception:
            logger.debug("replaceTrack(None) failed or not needed", exc_info=True)
        await pc.close()
        return None, "failed to process offer"



async def establish_connection(pc, offer):
    await pc.setRemoteDescription(offer)
    logger.debug("Remote description set")
    
    answer = await pc.createAnswer()
    await pc.setLocalDescription(answer)
    logger.debug("Local description set")

    while getattr(pc, "iceGatheringState", None) != "complete":
        await asyncio.sleep(0.05)
    
    logger.debug("ICE gathering complete")
    return {"sdp": pc.localDescription.sdp, "type": pc.localDescription.type}
