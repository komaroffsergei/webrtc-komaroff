import asyncio
import logging
import os

from aiortc import RTCPeerConnection, RTCSessionDescription, RTCIceCandidate
from aiohttp import web

from .processors.graph import AudioGraph
from .processors import TrackSourceNode, EchoTrackNode, LossFillerNode, RecorderNode, BgmMixerNode
from .processors.nats_node import NatsNode
from .utils.config import STATIC_DIR
from .utils.pc_lifecycle import attach_pc_lifecycle
from .utils.validate import get_params, validate_sdp

logger = logging.getLogger("webrtc")
MAX_SDP_SIZE = 1_000_000


# In-memory mapping from client id -> pc and pending server candidates
PENDING = {}

# Helpers split: connection setup vs stream processing
async def establish_connection(pc, offer, client_id):
    await pc.setRemoteDescription(offer)
    answer = await pc.createAnswer()
    await pc.setLocalDescription(answer)

    @pc.on("icecandidate")
    def on_server_candidate(event):
        cand = event.candidate
        if not cand:
            return
        if client_id in PENDING:
            PENDING[client_id]["candidates"].append({
                "candidate": cand.to_sdp(),
                "sdpMid": cand.sdpMid,
                "sdpMLineIndex": cand.sdpMLineIndex,
            })

    return {"sdp": pc.localDescription.sdp, "type": pc.localDescription.type, "clientId": client_id}


async def start_audio_pipeline(graph, track, audio_transceiver, echo_ref):
    # Build modular audio pipeline only when audio track arrives
    source = graph.add(TrackSourceNode(
        track,
        frame_duration_ms=20,
        target_rate=48000,
        target_channels=1,
        target_output_format='s16'
    ))

    bgm = graph.add(BgmMixerNode(source, bgm_path=os.path.join(STATIC_DIR, "bg.wav"), gain=0.2))
    filler = graph.add(LossFillerNode(source, latency_budget_ms=180, backlog_leave_frames=2, fill_mode="silence"))
    recorder = graph.add(RecorderNode(filler, batch_frames=512))

    # Optional NATS tap if present
    try:
        nats_node = NatsNode()
        await nats_node.connect(
            nc_url=os.getenv("NATS_URL", "nats://localhost:4222"),
            subject=os.getenv("NATS_SUBJECT", "audio.frames")
        )
        nats_node.use_source(source)
        graph.add(nats_node)
    except Exception:
        logger.debug("NATS node init failed or not configured", exc_info=True)

    echo = EchoTrackNode(bgm)
    audio_transceiver.sender.replaceTrack(echo)
    echo_ref["node"] = echo

    # Start graph if not running
    asyncio.create_task(graph.start())


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

    # Generate a simple client id and register in memory
    client_id = params.get("clientId") or os.urandom(6).hex()
    PENDING[client_id] = {"pc": pc, "candidates": []}

    logger.info("PC created and audio transceiver added (sendrecv)")
    if logger.isEnabledFor(logging.DEBUG):
        logger.debug(f"Active PCs: {len(pcs)}")


    echo_ref = {"node": None}



    @pc.on("track")
    async def on_track(track):
        logger.info(f"on_track: received kind={track.kind}")
        if track.kind == "audio":
            graph = AudioGraph()
            attach_pc_lifecycle(pc, request.app, graph, audio_transceiver, echo_ref)
            await start_audio_pipeline(graph, track, audio_transceiver, echo_ref)
            logger.info("Audio graph started")

    try:
        resp = await establish_connection(pc, offer, client_id)
    except Exception:
        logger.error("Failed to process SDP offer", exc_info=True)
        try:
            await audio_transceiver.sender.replaceTrack(None)
        except Exception:
            logger.debug("replaceTrack(None) failed or not needed", exc_info=True)
        await pc.close()
        return web.json_response({"error": "failed to process offer"}, status=400)

    return web.json_response(resp)


async def handle_index(request):
    logger.debug("Serving index.html")
    return web.FileResponse(os.path.join(STATIC_DIR, "index.html"))


async def handle_trickle_post(request):
    data = await request.json()
    client_id = data.get("clientId")
    if not client_id or client_id not in PENDING:
        return web.json_response({"error": "unknown clientId"}, status=400)
    pc = PENDING[client_id]["pc"]

    # Accept either a single candidate or a batch { candidates: [{...}, ...] }
    batch = data.get("candidates")
    items = batch if isinstance(batch, list) else [
        {
            "candidate": data.get("candidate"),
            "sdpMid": data.get("sdpMid"),
            "sdpMLineIndex": data.get("sdpMLineIndex"),
        }
    ]

    for item in items:
        cand = item.get("candidate")
        if not cand:
            continue
        try:
            await pc.addIceCandidate(RTCIceCandidate(
                sdpMid=item.get("sdpMid"),
                sdpMLineIndex=item.get("sdpMLineIndex"),
                candidate=cand
            ))
        except Exception:
            logger.warning("addIceCandidate failed", exc_info=True)

    return web.json_response({"ok": True, "count": len([i for i in items if i.get('candidate')])})


async def handle_trickle_get(request):
    client_id = request.query.get("clientId")
    if not client_id or client_id not in PENDING:
        return web.json_response({"candidates": []})
    out = PENDING[client_id]["candidates"]
    PENDING[client_id]["candidates"] = []
    return web.json_response({"candidates": out})


async def handle_shutdown(app):
    logger.info("Shutdown: closing all peer connections")
    pcs = list(app["pcs"])
    await asyncio.gather(*(pc.close() for pc in pcs), return_exceptions=True)
    app["pcs"].clear()
    logger.info("Shutdown complete")