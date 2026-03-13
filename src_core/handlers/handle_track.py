import asyncio
import logging
from uuid import uuid4

from .handle_transcription import handle_transcription
from src_core.processors import (
    TrackSourceNode,
    WhisperStreamNode,
)
from src_core.processors.graph import AudioGraph
from src_core.utils.pc_lifecycle import attach_pc_lifecycle
from src_core.utils.event_bus import event_log
from ..settings import STACK_SERVICE_NAME

logger = logging.getLogger("track")


async def handle_track(track, pc, audio_transceiver, app, *, session_id: str | None = None):
    if track.kind != "audio":
        return

    await event_log(
                    "log",
                    "info",
                    {"text": "Audio track connected"},
                    app=app,
                    service=STACK_SERVICE_NAME)

    #
    # AUDIO GRAPH
    #
    graph = AudioGraph()
    attach_pc_lifecycle(pc, app, graph, audio_transceiver)

    source = graph.add(
        TrackSourceNode(
            track,
            frame_duration_ms=20,
            target_rate=16000,
            target_channels=1,
            target_output_format='s16p'
        )
    )

    #
    # WHISPER STREAM NODE (no segmentation in core)
    #
    token = session_id or str(uuid4())
    in_prefix = str(app["vars"]["ASR_IN_PREFIX"] or "").strip()
    out_prefix = str(app["vars"]["ASR_OUT_PREFIX"] or "").strip()
    if in_prefix and not in_prefix.endswith("."):
        in_prefix += "."
    if out_prefix and not out_prefix.endswith("."):
        out_prefix += "."
    in_subject = f"{in_prefix}{token}"
    out_subject = f"{out_prefix}{token}"
    graph.add(
        WhisperStreamNode(
            source,
            app["services"]["nats_client"],
            in_subject,
            out_subject,
            on_transcription=lambda data: handle_transcription(app, data),
            session_id=session_id,
            sample_rate=16000,
        )
    )

    # START GRAPH
    asyncio.create_task(graph.start())
    await event_log(
                    "log",
                    "info",
                    {"text": "Audio graph started"},
                    app=app,
                    service=STACK_SERVICE_NAME)
