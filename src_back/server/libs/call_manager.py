import asyncio
import ipaddress
import logging
import os
import time

from aiortc import RTCPeerConnection, RTCSessionDescription, RTCIceGatherer, RTCIceServer
from aiortc.rtcicetransport import Connection

from ..libs.aiortc_patch import get_component_candidates, getDefaultIceServers
from ..processors.graph import AudioGraph
from ..processors import TrackSourceNode, EchoTrackNode, LossFillerNode, RecorderNode, BgmMixerNode
from ..utils.config import STATIC_DIR
from ..utils.pc_lifecycle import attach_pc_lifecycle

logger = logging.getLogger("webrtc")




class CallManager:
    def __init__(self, app):
        self.app = app
        RTCIceGatherer.getDefaultIceServers = getDefaultIceServers
        Connection.get_component_candidates = get_component_candidates

    async def establish_connection(self, pc, offer):
        await pc.setRemoteDescription(offer)
        answer = await pc.createAnswer()
        await pc.setLocalDescription(answer)
        while getattr(pc, "iceGatheringState", None) != "complete":
            await asyncio.sleep(0.05)

    async def start_audio_pipeline(self, graph, track, audio_transceiver, echo_ref):
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

        echo = EchoTrackNode(bgm)
        audio_transceiver.sender.replaceTrack(echo)
        echo_ref["node"] = echo
        asyncio.create_task(graph.start())

    async def handle_offer(self, params):
        sdp = params.get("sdp")
        offer_type = params.get("type")
        offer = RTCSessionDescription(sdp=sdp, type=offer_type)

        t_create_start = time.monotonic()
        # Configure ICE servers and transport policy from environment if provided
        ice_servers_json = os.getenv("ICE_SERVERS_JSON")
        ice_servers = None
        if ice_servers_json:
            try:
                import json
                ice_servers = json.loads(ice_servers_json)
            except Exception:
                logger.warning("Invalid ICE_SERVERS_JSON, ignoring", exc_info=True)
        force_relay = os.getenv("ICE_FORCE_RELAY", "0") in ("1", "true", "True")
        config_kwargs = {}
        if ice_servers:
            config_kwargs["iceServers"] = ice_servers
        if force_relay:
            config_kwargs["iceTransportPolicy"] = "relay"
        pc = RTCPeerConnection(configuration=config_kwargs if config_kwargs else None)
        t_pc_created = time.monotonic()
        audio_transceiver = pc.addTransceiver("audio", direction="sendrecv")
        t_transceiver_added = time.monotonic()
        logger.info(
            "offer_timing_pc: create=%.2fms addTransceiver=%.2fms",
            (t_pc_created - t_create_start) * 1000,
            (t_transceiver_added - t_pc_created) * 1000,
        )

        pcs = {p for p in self.app["pcs"] if p.connectionState not in ("failed", "closed")}
        self.app["pcs"] = pcs
        pcs.add(pc)

        logger.info("PC created and audio transceiver added (sendrecv)")
        if logger.isEnabledFor(logging.DEBUG):
            logger.debug(f"Active PCs: {len(pcs)}")

        echo_ref = {"node": None}

        @pc.on("track")
        async def on_track(track):
            logger.info(f"on_track: received kind={track.kind}")
            if track.kind == "audio":
                graph = AudioGraph()
                attach_pc_lifecycle(pc, self.app, graph, audio_transceiver, echo_ref)
                await self.start_audio_pipeline(graph, track, audio_transceiver, echo_ref)
                logger.info("Audio graph started")

        try:
            resp = await self.establish_connection(pc, offer)
            return resp, None
        except Exception:
            logger.error("Failed to process SDP offer", exc_info=True)
            try:
                await audio_transceiver.sender.replaceTrack(None)
            except Exception:
                logger.debug("replaceTrack(None) failed or not needed", exc_info=True)
            await pc.close()
            return None, "failed to process offer"
