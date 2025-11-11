import asyncio
import json
import logging
import os
from typing import Dict, Any

from aiortc import RTCPeerConnection
from ..processors import (
    TrackSourceNode,
    BgmMixerNode,
    LossFillerNode,
    RecorderNode,
    EchoTrackNode,
    AudioMonitorNode,
    NatsNode,
    PhraseSegmenterNode,
)
from ..processors.graph import AudioGraph
from ..utils.config import STATIC_DIR
from ..utils.pc_lifecycle import attach_pc_lifecycle
from ..voice_commands import CommandRegistry, CommandMatcher
from ..commands import register_alert_command
from .sse import sse_command, sse_log, sse_message, sse_warning

logger = logging.getLogger("handle_track")


def _resolve_subject(env_key: str, default: str) -> str:
    value = os.getenv(env_key, "").strip()
    if not value:
        return default
    return value[:-1] if value.endswith(".") else value


async def handle_track(track, pc, audio_transceiver, app, echo_ref):
    nats_node = await nats_init()
    logger.info(f"on_track: received kind={track.kind}")
    await sse_log(app, f"Audio track processing started, kind={track.kind}", level="info")
    
    if track.kind == "audio":
        graph = AudioGraph()
        attach_pc_lifecycle(pc, app, graph, audio_transceiver, echo_ref)

        source = graph.add(TrackSourceNode(
            track,
            frame_duration_ms=20,
            target_rate=16000,
            target_channels=1,
            target_output_format='s16p'
        ))

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

        # Bind upstream audio to pre-initialized NATS node and add into graph
        nats_node.use_source(source)
        graph.add(nats_node)

        await nats_node.ensure_nc()
        nats_whisper_subject = _resolve_subject("NATS_WHISPER_SUBJECT", "whisper.transcription")
        nats_logs_subject = _resolve_subject("NATS_LOGS_SUBJECT", "whisper.logs")

        command_registry = CommandRegistry()
        register_alert_command(command_registry)
        command_matcher = CommandMatcher(command_registry)

        logger.info("Registered %d voice commands", len(command_registry.commands))

        async def handle_transcription(data: Dict[str, Any]) -> None:
            try:
                text = str(data.get("text", "")).strip()
                if not text:
                    return
                service_name = data.get("service") or "src_whisper"

                audio_duration = data.get("audio_duration")
                transcription_time = data.get("transcription_time")
                segment_count = data.get("segments")
                details = []
                if isinstance(audio_duration, (int, float)):
                    details.append(f"audio={audio_duration:.2f}s")
                if isinstance(transcription_time, (int, float)):
                    details.append(f"time={transcription_time:.2f}s")
                if isinstance(segment_count, int):
                    details.append(f"segments={segment_count}")
                details_suffix = f" ({', '.join(details)})" if details else ""

                await sse_log(
                    app,
                    f"Transcription: {text}{details_suffix}",
                    level="info",
                    service=service_name,
                )
                await sse_message(app, text, descr="transcription", service=service_name)

                command_result = await command_matcher.process_transcription(text)
                if command_result:
                    await sse_log(
                        app,
                        f"Voice command: {command_result['command']}",
                        level="info",
                    )
                    cmd_payload = command_result["result"]
                    if isinstance(cmd_payload, dict) and not cmd_payload.get("error"):
                        if cmd_payload.get("type") == "command":
                            await sse_command(
                                app,
                                cmd_payload.get("method"),
                                cmd_payload.get("params", {}),
                            )
            except Exception as exc:
                logger.warning("Transcription handling error: %s", exc, exc_info=True)

        vad_sample_rate = int(os.getenv("VAD_SAMPLE_RATE", "16000"))
        vad_min_speech = int(os.getenv("VAD_MIN_SPEECH_DURATION_MS", "250"))
        vad_min_silence = int(os.getenv("VAD_MIN_SILENCE_DURATION_MS", "500"))
        vad_max_speech = float(os.getenv("VAD_MAX_SPEECH_DURATION_S", "30.0"))
        vad_speech_pad = int(os.getenv("VAD_SPEECH_PAD_MS", "30"))
        vad_threshold = float(os.getenv("VAD_THRESHOLD", "0.8"))
        vad_check_interval = float(os.getenv("VAD_BUFFER_CHECK_INTERVAL", "1.0"))

        segmenter = graph.add(
            PhraseSegmenterNode(
                source,
                nats_node.nc,
                nats_whisper_subject,
                handle_transcription,
                sample_rate=vad_sample_rate,
                min_speech_duration_ms=vad_min_speech,
                min_silence_duration_ms=vad_min_silence,
                max_speech_duration_s=vad_max_speech,
                speech_pad_ms=vad_speech_pad,
                threshold=vad_threshold,
                buffer_check_interval_s=vad_check_interval,
            )
        )
        logger.info("PhraseSegmenterNode configured for subject %s", nats_whisper_subject)
        await sse_log(
            app,
            f"Whisper phrase pipeline ready ({nats_whisper_subject})",
            level="info",
        )
        
        # Подписка на логи от Whisper сервиса
        async def _whisper_logs_cb(msg):
            try:
                log_data = json.loads(msg.data.decode("utf-8"))
                service_name = log_data.get('service') or 'src_whisper'
                message_text = log_data.get('message', '')

                await sse_log(
                    app,
                    message_text,
                    level=log_data.get('type', 'info'),
                    service=service_name,
                    log_time=log_data.get('time'),
                )

            except Exception as e:
                logger.warning(f"Error processing whisper log: {e}")
        
        await nats_node.nc.subscribe(nats_logs_subject, cb=_whisper_logs_cb)
        logger.info(f"Subscribed to whisper logs: {nats_logs_subject}")
        await sse_log(app, f"NATS: Subscribed to {nats_logs_subject}", level="info")

        # Echo back mixed audio to the browser
        # echo = EchoTrackNode(source)
        # audio_transceiver.sender.replaceTrack(echo)
        # echo_ref["node"] = echo
        asyncio.create_task(graph.start())

        logger.info("Audio graph started")
        await sse_log(app, "Audio graph started successfully", level="info")


async def nats_init():
    nats_node = NatsNode()
    nats_url = os.getenv("NATS_URL", "nats://localhost:4222")
    nats_subject = _resolve_subject("NATS_AUDIO_SUBJECT", "audio.frames")
    await nats_node.connect(
        nc_url=nats_url,
        subject=nats_subject
    )
    await nats_node.ensure_nc()

    async def _core_cb(msg):
        await nats_on_message_core(msg)

    # await nats_node.nc.subscribe(nats_subject, cb=_core_cb)
    logger.info("Subscribed to NATS subject (core mode, no JetStream)")
    
    # Сохраняем app для логирования (если доступен через контекст)
    # nats_node._app = app  # Будет добавлено в вызывающей функции
    
    return nats_node

async def nats_on_message_core(msg):
    # Core NATS message (no JS metadata/ack)
    print(f"--- new msg (core): subject={msg.subject} reply={msg.reply}")
    print(f"---- data: {msg.data[:100]}...")
