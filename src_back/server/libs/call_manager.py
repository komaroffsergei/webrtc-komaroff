import asyncio
import logging
import os
import time

from aiortc import RTCPeerConnection, RTCSessionDescription
from ..processors.graph import AudioGraph
from ..processors import TrackSourceNode, EchoTrackNode, LossFillerNode, RecorderNode, BgmMixerNode
from ..utils.config import STATIC_DIR
from ..utils.pc_lifecycle import attach_pc_lifecycle

logger = logging.getLogger("webrtc")


class CallManager:
    def __init__(self, app):
        self.app = app

    async def establish_connection(self, pc, offer):
        t0 = time.monotonic()
        await pc.setRemoteDescription(offer)
        t_set_remote = time.monotonic()
        answer = await pc.createAnswer()
        t_create_answer = time.monotonic()
        await pc.setLocalDescription(answer)
        t_set_local = time.monotonic()
        logger.info(
            "offer_timing: setRemote=%.2fms createAnswer=%.2fms setLocal=%.2fms",
            (t_set_remote - t0) * 1000,
            (t_create_answer - t_set_remote) * 1000,
            (t_set_local - t_create_answer) * 1000,
        )


        while getattr(pc, "iceGatheringState", None) != "complete":
            await asyncio.sleep(0.05)

        return {"sdp": pc.localDescription.sdp, "type": pc.localDescription.type}

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
        pc = RTCPeerConnection()
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
