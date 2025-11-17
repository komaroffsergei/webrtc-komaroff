import asyncio
import logging

from .handle_transcription import handle_transcription
from ..processors import (
    TrackSourceNode,
    PhraseSegmenterNode,
)
from ..processors.graph import AudioGraph
from ..utils.pc_lifecycle import attach_pc_lifecycle
from ..utils.sse import sse_log

logger = logging.getLogger("track")


async def handle_track(track, pc, audio_transceiver, app, echo_ref):
    if track.kind != "audio":
        return

    await sse_log(app, "Audio track connected", level="info")

    #
    # AUDIO GRAPH
    #
    graph = AudioGraph()
    attach_pc_lifecycle(pc, app, graph, audio_transceiver, echo_ref)

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
            source,
            app['services']['nats_client'],  # publish frames
            app['vars']['NATS_FRAMES_SUBJECT'],  # whisper input
            on_transcription= lambda on_transcription: handle_transcription(app) ,  # whisper output
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
    await sse_log(app, "Audio graph started", level="info")
