import asyncio
import logging
from typing import Optional

import numpy as np
import av
from av import AudioFrame

logger = logging.getLogger(__name__)


from .base import ConsumerNode


class BgmMixerNode(ConsumerNode):
    """
    Minimal background music mixer.

    Assumptions:
    - Upstream (TrackSourceNode) provides normalized AudioFrame in s16p (planar),
      fixed sample rate, fixed channel layout, fixed samples per frame.
    - We simply add bgm to the speech signal with a linear gain and clip to int16.
    - No additional effects or dynamics processing.

    Behavior:
    - Opens bgm WAV/any supported audio file once on first frame to learn target
      sample rate and layout, creates a resampler to s16p matching upstream.
    - For each incoming frame, reads exactly frame.samples bgm samples (looping
      the file if needed), mixes and forwards a new s16p frame.
    """

    def __init__(self, source_node, *, bgm_path: str, gain: float = 0.2) -> None:
        super().__init__(source_node)
        self.bgm_path = bgm_path
        self.gain = float(gain)

        self.out_queues: list[asyncio.Queue] = []
        self.running = False

        # Initialized on first frame
        self._samplerate: Optional[int] = None
        self._channels: Optional[int] = None
        self._layout_name: Optional[str] = None
        self._time_base = None

        # BGM resources
        self._bgm_container: Optional[av.container.InputContainer] = None
        self._bgm_stream: Optional[av.audio.stream.AudioStream] = None
        self._bgm_resampler: Optional[av.audio.resampler.AudioResampler] = None

    def subscribe(self) -> asyncio.Queue:
        q: asyncio.Queue = asyncio.Queue()
        self.out_queues.append(q)
        return q

    def unsubscribe(self, q: asyncio.Queue) -> None:
        try:
            self.out_queues.remove(q)
        except ValueError:
            pass

    async def start(self):
        if self.running:
            return
        self.running = True
        await super().start()

    async def handle_frame(self, frame: AudioFrame) -> None:
        # initialize format from upstream on first frame
        if self._samplerate is None:
            self._samplerate = int(frame.sample_rate)
            self._channels = len(frame.layout.channels)
            self._layout_name = 'mono' if self._channels == 1 else 'stereo'
            self._time_base = frame.time_base
            # init bgm IO
            try:
                self._bgm_container = av.open(self.bgm_path)
                self._bgm_stream = next(s for s in self._bgm_container.streams if s.type == 'audio')
                self._bgm_resampler = av.audio.resampler.AudioResampler(
                    format='s16p',
                    layout=self._layout_name,
                    rate=self._samplerate,
                )
                logger.info(f"BGM opened {self.bgm_path} -> {self._layout_name}@{self._samplerate}")
            except Exception as e:
                logger.error(f"BGM open failed: {e}")
                self._bgm_container = None

        # get upstream samples (s16p planar ndarray, shape (C, N))
        speech_np = frame.to_ndarray()
        samples = frame.samples

        # prepare bgm samples matching shape
        bgm_np = self._read_bgm_samples(samples, self._channels) if self._bgm_container else None
        if bgm_np is None:
            # no bgm available -> pass-through
            await self.fan_out(frame)
            return

        # Mix in float32, clip, back to int16
        sp_f = speech_np.astype(np.float32) / 32768.0
        bg_f = bgm_np.astype(np.float32) / 32768.0
        mixed = sp_f + self.gain * bg_f
        np.clip(mixed, -1.0, 1.0, out=mixed)
        mixed_i16 = (mixed * 32767.0).astype(np.int16)

        out = AudioFrame.from_ndarray(mixed_i16, format='s16p', layout=self._layout_name)
        out.sample_rate = self._samplerate
        out.pts = frame.pts
        out.time_base = self._time_base

        await self.fan_out(out)

    async def _shutdown(self):
        # close bgm resources
        try:
            if self._bgm_container is not None:
                self._bgm_container.close()
        except Exception:
            pass

    def _read_bgm_samples(self, samples: int, channels: int) -> Optional[np.ndarray]:
        """Return planar int16 ndarray (C, N) of bgm audio with exact sample count.
        Robust to EOF: loops file by seeking(0) when end is reached.
        """
        if self._bgm_container is None or self._bgm_stream is None or self._bgm_resampler is None:
            return None
        out_buf = np.zeros((channels, samples), dtype=np.int16)
        filled = 0
        attempts = 0
        while filled < samples and attempts < 3:
            try:
                for packet in self._bgm_container.demux(self._bgm_stream):
                    for frm in packet.decode():
                        rs = self._bgm_resampler.resample(frm)
                        if rs is None:
                            continue
                        rs = rs[0] if isinstance(rs, list) else rs
                        bg_np = rs.to_ndarray()  # (C, N') int16 planar
                        need = samples - filled
                        take = min(need, bg_np.shape[1])
                        out_buf[:, filled:filled + take] = bg_np[:, :take]
                        filled += take
                        if filled >= samples:
                            break
                    if filled >= samples:
                        break
                if filled < samples:
                    # likely EOF: loop back to start and try again
                    try:
                        self._bgm_container.seek(0)
                    except Exception:
                        logger.debug("BGM seek(0) failed")
                    attempts += 1
                    continue
            except av.AVError as e:
                logger.debug(f"BGM AVError during demux/decode: {e}")
                try:
                    self._bgm_container.seek(0)
                except Exception:
                    pass
                attempts += 1
                continue
            except Exception as e:
                logger.error(f"BGM read error: {e}")
                break
        return out_buf if filled > 0 else None

    async def _fan_out(self, frame: AudioFrame):
        for q in list(self.out_queues):
            try:
                q.put_nowait(frame)
            except asyncio.QueueFull:
                # drop-oldest until enqueue succeeds
                while True:
                    try:
                        _ = q.get_nowait()
                    except asyncio.QueueEmpty:
                        break
                    try:
                        q.put_nowait(frame)
                        break
                    except asyncio.QueueFull:
                        continue
            except Exception as e:
                logger.exception(f"BgmMixerNode fan_out error: {e}")
