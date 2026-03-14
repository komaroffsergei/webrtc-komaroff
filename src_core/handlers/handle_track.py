import asyncio
import json
import logging
from fractions import Fraction
from uuid import uuid4

import av
import numpy as np
from av import AudioFrame

from .handle_transcription import handle_transcription
from src_core.utils.event_bus import event_log
from ..settings import STACK_SERVICE_NAME

logger = logging.getLogger("track")


def _subject(prefix: str, token: str) -> str:
    value = str(prefix or "").strip()
    if value and not value.endswith("."):
        value += "."
    return f"{value}{token}"


def _frame_payload(*, session_id: str | None, seq: int, sample_rate: int, pcm: np.ndarray) -> bytes:
    meta: dict[str, object] = {
        "type": "frame",
        "seq": seq,
        "sample_rate": sample_rate,
        "sample_width": 2,
        "channels": 1,
    }
    if session_id:
        meta["session_id"] = session_id
    meta_bytes = json.dumps(meta, ensure_ascii=False).encode("utf-8")
    return len(meta_bytes).to_bytes(4, "big") + meta_bytes + pcm.astype("<i2", copy=False).tobytes()


def _end_payload(*, session_id: str | None, seq: int, sample_rate: int) -> bytes:
    meta: dict[str, object] = {
        "type": "end",
        "seq": seq,
        "sample_rate": sample_rate,
        "sample_width": 2,
        "channels": 1,
    }
    if session_id:
        meta["session_id"] = session_id
    meta_bytes = json.dumps(meta, ensure_ascii=False).encode("utf-8")
    return len(meta_bytes).to_bytes(4, "big") + meta_bytes


async def handle_track(track, pc, audio_transceiver, app, *, session_id: str | None = None):
    if track.kind != "audio":
        return

    await event_log("log", "info", {"text": "Audio track connected"}, app=app, service=STACK_SERVICE_NAME)

    token = session_id or str(uuid4())
    in_subject = _subject(app["vars"]["ASR_IN_PREFIX"], token)
    out_subject = _subject(app["vars"]["ASR_OUT_PREFIX"], token)
    nats_client = app["services"]["nats_client"]
    closed = asyncio.Event()
    cleanup_lock = asyncio.Lock()
    subscription = None

    async def cleanup(*, close_pc: bool) -> None:
        if closed.is_set():
            return
        async with cleanup_lock:
            if closed.is_set():
                return
            closed.set()
            if subscription is not None:
                try:
                    await subscription.unsubscribe()
                except Exception:
                    logger.exception("Failed to unsubscribe from ASR output")
            try:
                await audio_transceiver.sender.replaceTrack(None)
            except Exception:
                logger.debug("replaceTrack(None) failed or not needed", exc_info=True)
            try:
                app["pcs"].discard(pc)
            except Exception:
                logger.debug("Failed to discard PC from app set", exc_info=True)
            if close_pc and pc.connectionState != "closed":
                try:
                    await pc.close()
                except Exception:
                    logger.debug("PC close failed", exc_info=True)

    async def on_transcription(msg) -> None:
        try:
            data = json.loads(msg.data.decode("utf-8"))
        except Exception:
            logger.exception("Invalid JSON from ASR")
            return
        if session_id:
            data.setdefault("session_id", session_id)
        await handle_transcription(app, data)

    subscription = await nats_client.subscribe(out_subject, cb=on_transcription)

    @pc.on("connectionstatechange")
    async def on_connectionstatechange():
        state = pc.connectionState
        logger.info("PC state changed: %s", state)
        if state in ("failed", "closed", "disconnected"):
            await cleanup(close_pc=state != "closed")

    async def publish_audio() -> None:
        seq = 0
        frame_duration_ms = 20
        target_rate = 16000
        samples_per_frame = int(target_rate * frame_duration_ms / 1000)
        resampler = av.audio.resampler.AudioResampler(format="s16p", layout="mono", rate=target_rate)
        time_base = Fraction(1, target_rate)
        next_pts = 0

        try:
            while not closed.is_set():
                try:
                    in_frame: AudioFrame = await track.recv()
                except Exception:
                    break
                frames = resampler.resample(in_frame)
                for rf in frames if isinstance(frames, list) else [frames]:
                    pcm = rf.to_ndarray()
                    if pcm.ndim == 1:
                        pcm = pcm[np.newaxis, :]
                    elif pcm.ndim == 2 and pcm.shape[0] == rf.samples:
                        pcm = pcm.T
                    if pcm.dtype != np.int16:
                        pcm = (np.clip(pcm, -1.0, 1.0) * 32767.0).astype(np.int16)
                    if pcm.shape[0] != 1:
                        pcm = pcm.mean(axis=0, keepdims=True).astype(np.int16)
                    total_samples = pcm.shape[1]
                    offset = 0
                    while offset < total_samples and not closed.is_set():
                        take = min(samples_per_frame, total_samples - offset)
                        piece = np.zeros((1, samples_per_frame), dtype=np.int16)
                        piece[:, :take] = pcm[:, offset:offset + take]
                        out_frame = AudioFrame.from_ndarray(piece, format="s16p", layout="mono")
                        out_frame.sample_rate = target_rate
                        out_frame.time_base = time_base
                        out_frame.pts = next_pts
                        next_pts += samples_per_frame
                        seq += 1
                        await nats_client.publish(
                            in_subject,
                            _frame_payload(
                                session_id=session_id,
                                seq=seq,
                                sample_rate=target_rate,
                                pcm=out_frame.to_ndarray().reshape(-1),
                            ),
                        )
                        offset += take
        finally:
            if not closed.is_set():
                try:
                    seq += 1
                    await nats_client.publish(
                        in_subject,
                        _end_payload(session_id=session_id, seq=seq, sample_rate=16000),
                    )
                except Exception:
                    logger.exception("Failed to publish stream end to ASR")
            await cleanup(close_pc=False)

    asyncio.create_task(publish_audio())
    await event_log("log", "info", {"text": "Direct audio stream started"}, app=app, service=STACK_SERVICE_NAME)
