import asyncio
import logging
import os
from typing import Dict, Any

from aiortc import RTCPeerConnection

from ..processors import TrackSourceNode, BgmMixerNode, LossFillerNode, RecorderNode, EchoTrackNode
from ..processors.graph import AudioGraph
from ..processors.nats_node import NatsNode
from ..utils.config import STATIC_DIR
from ..utils.pc_lifecycle import attach_pc_lifecycle

logger = logging.getLogger("handle_track")


async def handle_track(track, pc, audio_transceiver, app, echo_ref):
    nats_node = await nats_init()
    logger.info(f"on_track: received kind={track.kind}")
    if track.kind == "audio":
        graph = AudioGraph()
        attach_pc_lifecycle(pc, app, graph, audio_transceiver, echo_ref)

        source = graph.add(TrackSourceNode(
            track,
            frame_duration_ms=20,
            target_rate=48000,
            target_channels=1,
            target_output_format='s16'
        ))

        bgm = graph.add(BgmMixerNode(source, bgm_path=os.path.join(STATIC_DIR, "bg.wav"), gain=0.2))
        filler = graph.add(
            LossFillerNode(source, latency_budget_ms=180, backlog_leave_frames=2, fill_mode="silence"))
        recorder = graph.add(RecorderNode(filler, batch_frames=512))

        # Bind upstream audio to pre-initialized NATS node and add into graph
        nats_node.use_source(source)
        graph.add(nats_node)

        echo = EchoTrackNode(bgm)
        audio_transceiver.sender.replaceTrack(echo)
        echo_ref["node"] = echo
        asyncio.create_task(graph.start())

        logger.info("Audio graph started")


async def nats_init():
    nats_node = NatsNode()
    nats_url = os.getenv("NATS_URL", "nats://localhost:4222")
    nats_subject = os.getenv("NATS_SUBJECT", "audio.frames")
    nats_durable = os.getenv("NATS_DURABLE", "debug_reader")
    await nats_node.connect(
        nc_url=nats_url,
        subject=nats_subject
    )
    await nats_node.ensure_nc()

    async def _core_cb(msg):
        await nats_on_message_core(msg)

    await nats_node.nc.subscribe(nats_subject, cb=_core_cb)
    logger.info("Subscribed to NATS subject (core mode, no JetStream)")
    return nats_node

async def nats_on_message_core(msg):
    # Core NATS message (no JS metadata/ack)
    print(f"--- new msg (core): subject={msg.subject} reply={msg.reply}")
    print(f"---- data: {msg.data[:100]}...")
