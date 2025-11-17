import asyncio
import logging
import os
import json

from aiohttp import web
from ..processors import (
    TrackSourceNode,
    PhraseSegmenterNode,
)
from ..processors.graph import AudioGraph
from ..utils.pc_lifecycle import attach_pc_lifecycle
from ..utils.sse import sse_log

from ..voice_commands import CommandRegistry, CommandMatcher
from ..commands import register_alert_command

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

    # Callback для отправки предупреждений об уровне звука
    # async def audio_warning_callback(warning_type: str):
    #     await sse_warning(app, warning_type)

    # Нода мониторинга аудио (встраивается в граф)
    # monitor = graph.add(AudioMonitorNode(
    #     source,
    #     warning_callback=audio_warning_callback,
    #     check_interval=2.0,
    #     loud_threshold=0.9,
    #     quiet_threshold=0.02,
    #     noise_threshold=0.15,
    #     min_frames_for_check=10,
    #     warning_cooldown=10.0
    # ))

    # Build BGM mixer on top of monitored source
    # bgm = graph.add(BgmMixerNode(monitor, bgm_path=os.path.join(STATIC_DIR, "bg.wav"), gain=0.2))

    # filler = graph.add(
    #     LossFillerNode(monitor, latency_budget_ms=180, backlog_leave_frames=2, fill_mode="silence"))
    # recorder = graph.add(RecorderNode(monitor, batch_frames=512))

    #
    # NATS for audio + whisper
    #
    nc = app["services"]['nats_client']

    nats_whisper_subject = app['vars']['NATS_FRAMES_SUBJECT']

    #
    # COMMANDS
    #
    registry = CommandRegistry()
    register_alert_command(registry)
    matcher = CommandMatcher(registry)

    #
    # TRANSCRIPTION CALLBACK
    #
    async def handle_transcription(data):
        try:
            text = data.get("text", "").strip()
            if not text:
                return

            await sse_log(app, f"Transcription: {text}", level="info")

            cmd = await matcher.process_transcription(text)
            if cmd:
                await sse_log(app, f"VoiceCommand: {cmd['command']}", level="info")

        except Exception as e:
            logger.warning(f"transcription error: {e}")

    #
    # SEGMENTER NODE
    #
    segmenter = graph.add(
        PhraseSegmenterNode(
            source,
            app['services']['nats_client'],                                         # publish frames
            nats_whisper_subject,                       # whisper input
            handle_transcription,                       # whisper output
            sample_rate=16000,
            min_speech_duration_ms=250,
            min_silence_duration_ms=500,
            max_speech_duration_s=30.0,
            speech_pad_ms=30,
            threshold=0.8,
            buffer_check_interval_s=1.0,
        )
    )

    await sse_log(app, f"Segmenter ready ({nats_whisper_subject})", level="info")

    #
    # START GRAPH
    #
    asyncio.create_task(graph.start())
    await sse_log(app, "Audio graph started", level="info")
