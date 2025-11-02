import asyncio
import logging
import os
import json
from typing import Dict, Any

from aiortc import RTCPeerConnection
from ..processors import TrackSourceNode, BgmMixerNode, LossFillerNode, RecorderNode, EchoTrackNode, AudioMonitorNode
from ..processors.graph import AudioGraph
from ..processors.nats_node import NatsNode
from ..utils.config import STATIC_DIR
from .sse import sse_log, sse_message, sse_warning
from ..utils.pc_lifecycle import attach_pc_lifecycle

logger = logging.getLogger("handle_track")


async def handle_track(track, pc, audio_transceiver, app, echo_ref):
    nats_node = await nats_init()
    logger.info(f"on_track: received kind={track.kind}")
    await sse_log(app, f"Audio track processing started, kind={track.kind}", 
                  level="info", category="audio")
    
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
        async def audio_warning_callback(warning_type: str):
            await sse_warning(app, warning_type)

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

        # Subscribe to whisper subject and forward to logs and SSE
        await nats_node.ensure_nc()
        in_subject = os.getenv("AUDIO_SUBJ", "audio.frames")
        whisper_subject = os.getenv("WHISPER_SUBJ") or f"{in_subject}.whisper"

        async def _whisper_cb(msg):
            try:
                # Whisper отправляет JSON напрямую
                try:
                    data = json.loads(msg.data.decode("utf-8"))
                except Exception:
                    # Fallback на старый формат (meta_len + meta + audio)
                    raw_data = msg.data
                    meta_len = int.from_bytes(raw_data[:4], "big") if len(raw_data) >= 4 else 0
                    meta = {}
                    if meta_len and 4 + meta_len <= len(raw_data):
                        try:
                            meta = json.loads(raw_data[4:4+meta_len].decode("utf-8"))
                        except Exception:
                            meta = {}
                    data = meta
                
                msg_type = data.get("type", "unknown")
                
                # Обработка транскрипции
                if msg_type == "transcription":
                    text = data.get("text", "").strip()
                    if text:
                        await sse_log(app, f"Transcription: {text}", 
                                     level="info", category="nats")
                        
                        # Отправляем транскрипцию в чат
                        await sse_message(app, text, descr="transcription")
                
                # Обработка команды от Whisper
                elif msg_type == "command":
                    method = data.get("method")
                    params = data.get("params", {})
                    
                    if method:
                        await sse_log(app, f"Voice command: {method}", 
                                     level="info", category="nats")
                        
                        # Отправляем команду клиенту через SSE
                        from ..handlers.sse import sse_command
                        await sse_command(app, method, params)
                
                # Обработка других типов
                else:
                    text_line = f"[whisper] type={msg_type} data={data}"
                    await sse_log(app, text_line, level="debug", category="nats")
                
            except Exception as e:
                logger.warning(f"whisper cb error: {e}")
                await sse_log(app, f"NATS: Whisper callback error - {str(e)}", 
                             level="error", category="nats")

        await nats_node.nc.subscribe(whisper_subject, cb=_whisper_cb)
        logger.info(f"Subscribed to whisper subject: {whisper_subject}")
        await sse_log(app, f"NATS: Subscribed to {whisper_subject}", 
                     level="info", category="nats")

        # Echo back mixed audio to the browser
        # echo = EchoTrackNode(source)
        # audio_transceiver.sender.replaceTrack(echo)
        # echo_ref["node"] = echo
        asyncio.create_task(graph.start())

        logger.info("Audio graph started")
        await sse_log(app, "Audio graph started successfully", 
                     level="info", category="audio")


async def nats_init():
    nats_node = NatsNode()
    nats_url = os.getenv("NATS_URL", "nats://localhost:4222")
    raw_subj = os.getenv("AUDIO_SUBJ", "audio.frames")
    nats_subject = raw_subj if not str(raw_subj).endswith(".") else f"{raw_subj}frames"
    nats_durable = os.getenv("NATS_DURABLE", "debug_reader")
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
