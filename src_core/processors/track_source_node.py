import asyncio
from fractions import Fraction

import av
import numpy as np
from av import AudioFrame

from .base import FanOutNode


class TrackSourceNode(FanOutNode):
    """
    Audio source node wrapping an aiortc MediaStreamTrack and normalizing audio:
    - Fixed frame duration (frame_duration_ms)
    - Fixed sample rate (target_rate)
    - Fixed channel count (target_channels)
    - Planar s16p numpy representation internally, emits AudioFrame in 's16p'

    Responsibilities:
    - Pull frames from aiortc track, resample/convert to the target format
    - Slice into equal-length chunks, pad the tail if needed
    - Monotonic PTS based on time_base = 1 / target_rate
    - Fan-out frames to subscribers via asyncio.Queue

    Does NOT handle losses/delay classification. That logic belongs to LossFillerNode.
    """

    def __init__(self, track,
                 frame_duration_ms: int = 20,
                 target_rate: int = 48000,
                 target_output_format: str = 's16p',
                 target_channels: int = 1):
        """Initialize source normalization.

        Args:
            track: aiortc MediaStreamTrack (audio) to read from.
            frame_duration_ms: desired duration of emitted chunks (e.g., 20 ms).
            target_rate: output sample rate (Hz), typically 48000 for WebRTC.
            target_output_format: PyAV audio format string; default 's16p' (planar int16).
            target_channels: output channel count (1=mono, 2=stereo).
        """
        super().__init__()
        self.track = track
        self.frame_duration_ms = frame_duration_ms
        self.target_rate = target_rate
        self.target_channels = target_channels

        self.layout_name = "mono" if target_channels == 1 else "stereo"
        self.output_format = target_output_format

        self.resampler = av.audio.resampler.AudioResampler(
            format=self.output_format,
            layout=self.layout_name,
            rate=self.target_rate,
        )

        self.running = False

        self._time_base = Fraction(1, self.target_rate)
        self._samples_per_frame = int(self.target_rate * self.frame_duration_ms / 1000)
        
        # Pre-allocate padding buffer for performance
        self._padding_buffer = np.zeros((self.target_channels, self._samples_per_frame), dtype=np.int16)

    def samples_per_frame(self) -> int:
        """Return the fixed number of samples per emitted frame.

        Calculated as int(target_rate * frame_duration_ms / 1000).
        """
        return self._samples_per_frame

    async def start(self) -> None:
        """Run producer loop and fan-out normalized frames to subscribers.

        Reads from aiortc track, normalizes to target format, and enqueues frames
        to all subscriber queues. On cancellation or stop, enqueues None (EOF)
        to each subscriber and clears internal references.
        """
        if self.running:
            return
        self.running = True

        try:
            async for frame in self._normalized_chunk_stream():
                await self.fan_out(frame)
        except asyncio.CancelledError:
            raise
        finally:
            await self.close_downstreams()
            self.running = False

    def _normalize_pcm_shape(self, pcm: np.ndarray, rf: AudioFrame) -> np.ndarray:
        """Normalize PCM array to (channels, samples) shape."""
        if pcm.ndim == 1:
            return pcm[np.newaxis, :]
        elif pcm.ndim == 2 and pcm.shape[0] == rf.samples and pcm.shape[1] == rf.layout.channels:
            return pcm.T
        return pcm

    def _convert_channels(self, pcm: np.ndarray) -> np.ndarray:
        """Convert PCM to target channel count."""
        C = pcm.shape[0]
        if C == self.target_channels:
            return pcm
        
        if self.target_channels == 1:
            # Downmix to mono
            return pcm.mean(axis=0, keepdims=True).astype(pcm.dtype)
        elif self.target_channels > C:
            # Upmix by repeating last channel
            return np.repeat(pcm[-1:, :], self.target_channels, axis=0)
        else:
            # Downmix by truncating channels
            return pcm[:self.target_channels, :]

    def _convert_to_int16(self, pcm: np.ndarray) -> np.ndarray:
        """Convert PCM to int16 format if needed."""
        if pcm.dtype == np.int16:
            return pcm
        return (np.clip(pcm, -1.0, 1.0) * 32767.0).astype(np.int16)

    async def _normalized_chunk_stream(self):
        """Async generator yielding normalized AudioFrame chunks.

        - Receives AudioFrame from aiortc
        - Resamples/normalizes to 's16p' with target rate/layout
        - Slices into equal-length frames, padding the tail of each chunk
        - Sets PTS monotonically with step = samples_per_frame
        """
        next_pts = 0
        spf = self._samples_per_frame
        target_channels = self.target_channels
        output_format = self.output_format
        layout_name = self.layout_name
        target_rate = self.target_rate
        time_base = self._time_base
        
        while True:
            try:
                in_frame: AudioFrame = await self.track.recv()
            except Exception:
                break

            resampled = self.resampler.resample(in_frame)
            frames = resampled if isinstance(resampled, list) else [resampled]

            for rf in frames:
                pcm = self._normalize_pcm_shape(rf.to_ndarray(), rf)
                pcm = self._convert_channels(pcm)
                pcm = self._convert_to_int16(pcm)

                S = pcm.shape[1]
                i = 0
                while i < S:
                    take = min(spf, S - i)
                    if take == spf:
                        # Fast path: no padding needed
                        piece = pcm[:, i:i + spf]
                    else:
                        # Slow path: padding required
                        piece = self._padding_buffer[:, :spf].copy()
                        piece[:, :take] = pcm[:, i:i + take]

                    out = AudioFrame.from_ndarray(piece, format=output_format, layout=layout_name)
                    out.sample_rate = target_rate
                    out.time_base = time_base
                    out.pts = next_pts
                    next_pts += spf
                    yield out
                    i += take
