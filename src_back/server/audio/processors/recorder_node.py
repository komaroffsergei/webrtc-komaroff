import asyncio
import wave
from typing import Optional

import numpy as np
from av import AudioFrame

from ...utils.config import RECORDINGS_DIR
import logging

logger = logging.getLogger("audio.RecorderNode")


class RecorderNode:
    """
    Recorder node consuming normalized frames from a source node (subscribe()) and
    periodically flushing to WAV files with fixed batch size.

    Assumes frames are s16 planar with consistent sample_rate, channels and
    fixed samples per frame.
    """

    def __init__(self, source_node, *, batch_frames: int = 128) -> None:
        self.queue: asyncio.Queue = source_node.subscribe()
        self.batch_frames = int(batch_frames)
        self._frames: list[np.ndarray] = []
        self._idx: int = 0
        self._channels: Optional[int] = None
        self._samplerate: Optional[int] = None
        self._task: Optional[asyncio.Task] = None
        self._stopped: bool = False

    def start(self) -> None:
        if self._task is None:
            logger.info("start: recorder task created")
            self._task = asyncio.create_task(self._run())

    async def stop(self) -> None:
        if self._stopped:
            return
        self._stopped = True
        if self._task is not None:
            # signal EOF to loop and wait
            try:
                self.queue.put_nowait(None)
            except Exception:
                pass
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None
        # flush remaining data
        self._flush_batch(force=True)
        logger.info("stop: recorder stopped and flushed")

    async def _run(self) -> None:
        try:
            while True:
                frame = await self.queue.get()
                if frame is None:
                    logger.info("run: EOF received")
                    break
                self._handle_frame(frame)
        except asyncio.CancelledError:
            logger.info("run: cancelled")
        except Exception as e:
            logger.error(f"run: stopped with error: {e}")

    def _handle_frame(self, frame: AudioFrame) -> None:
        if self._samplerate is None:
            self._samplerate = int(frame.sample_rate)
        if self._channels is None:
            try:
                self._channels = len(frame.layout.channels)
            except Exception:
                arr = frame.to_ndarray()
                self._channels = 1 if arr.ndim == 1 else int(arr.shape[0])

        pcm = frame.to_ndarray()
        # Ensure planar [C, S]
        if pcm.ndim == 1:
            pcm = pcm[np.newaxis, :]
        # Convert to interleaved int16 mono for writing simplicity
        if self._channels == 1:
            data = pcm[0]
        else:
            # Downmix to mono for file size; adjust if stereo is needed
            data = pcm.mean(axis=0).astype(pcm.dtype)
        if data.dtype != np.int16:
            if np.issubdtype(data.dtype, np.floating):
                data = (np.clip(data, -1.0, 1.0) * 32767.0).astype(np.int16)
            else:
                data = data.astype(np.int16)

        self._frames.append(data)
        if len(self._frames) >= self.batch_frames:
            self._flush_batch()

    def _flush_batch(self, force: bool = False) -> None:
        if not self._frames:
            return
        data = np.concatenate(self._frames, axis=0)
        self._frames.clear()

        sr = self._samplerate or 48000
        ch = 1  # wrote mono above

        filename = f"{RECORDINGS_DIR}/batch_{self._idx:05d}.wav"
        self._idx += 1

        with wave.open(filename, "wb") as wf:
            wf.setnchannels(ch)
            wf.setsampwidth(2)
            wf.setframerate(sr)
            wf.writeframes(data.tobytes())

        logger.info(f"saved {filename}")
