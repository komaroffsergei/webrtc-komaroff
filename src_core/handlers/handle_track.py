import asyncio
import logging

from .handle_transcription import handle_transcription
from src_core.processors import (
    PhraseSegmenterNode,
    TrackSourceNode,
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
    # SEGMENTER NODE
    #
    segmenter = graph.add(
        PhraseSegmenterNode(
            app,
            source,
            app['services']['nats_client'],  # publish frames
            app['vars']['NATS_ASR_SUBJECT'],  # whisper input
            on_transcription= lambda data: handle_transcription(app, data) ,  # whisper output
            session_id=session_id,
            sample_rate=16000,
            min_speech_duration_ms=250,
            min_silence_duration_ms=500,
            max_speech_duration_s=30.0,
            speech_pad_ms=30,
            threshold=0.8,
            buffer_check_interval_s=1.0,
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
