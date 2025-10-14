import asyncio
from fractions import Fraction
from typing import Optional, List

import numpy as np
from av import AudioFrame
import logging

logger = logging.getLogger("audio.LossFillerNode")


class LossFillerNode:
    """
    Node that fills missing frames to preserve real-time continuity for consumers.
    - subscribes to a normalized source (e.g., TrackSourceNode producing s16p fixed-size frames)
    - when backlog exceeds latency budget, drains late frames and generates fill frames
    - also fills gaps if upstream PTS jumps unexpectedly
    """

    def __init__(self, source_node, beep_freq=3000.0, tone_gain=0.8,
                 latency_budget_ms: int = 180, backlog_leave_frames: int = 2,
                 fill_mode: str = "beep"):
        self.source_node = source_node
        self.queue = source_node.subscribe()
        self.out_queues: List[asyncio.Queue] = []
        self.running = False

        self.beep_freq = float(beep_freq)
        self.tone_gain = float(tone_gain)
        # fill_mode controls handling of losses:
        # 'glued' -> drop late frames (skip; recording is glued without placeholders)
        # 'silence' -> insert silence for each missing/late frame
        # 'beep' -> insert tone for each missing/late frame
        self.fill_mode = fill_mode
        self.fill_with_silence = (self.fill_mode == "silence")
        self.latency_budget_ms = int(latency_budget_ms)
        self.backlog_leave_frames = max(0, int(backlog_leave_frames))

        self._time_base = None
        self._next_pts = None
        self._channels = None
        self._samples_per_frame = None
        self._phase = 0.0
        self._layout_name = None

    def subscribe(self):
        q = asyncio.Queue()
        self.out_queues.append(q)
        return q

    def unsubscribe(self, q):
        try:
            self.out_queues.remove(q)
        except ValueError:
            pass

    async def start(self):
        if self.running:
            return
        self.running = True
        try:
            loop = asyncio.get_running_loop()
            last_emit = None  # monotonic timestamp of last emitted frame (fill or real)
            while True:
                frame = await self.queue.get()
                if frame is None:
                    break

                # init parameters from first frame
                if self._samples_per_frame is None:
                    self._samples_per_frame = frame.samples
                    self._channels = frame.layout.channels if isinstance(frame.layout.channels, int) else len(frame.layout.channels)
                    self._layout_name = 'mono' if self._channels == 1 else 'stereo'
                    self._time_base = frame.time_base
                    self._next_pts = frame.pts
                    last_emit = loop.time()

                # 1) time-based losses handling (wall-clock)
                frame_dur_ms = (self._samples_per_frame * 1000.0) / float(self._time_base.denominator)
                now = loop.time()
                if last_emit is not None:
                    elapsed_ms = (now - last_emit) * 1000.0
                    if elapsed_ms > frame_dur_ms + self.latency_budget_ms:
                        over_ms = elapsed_ms - (frame_dur_ms + self.latency_budget_ms)
                        missing = int(over_ms // frame_dur_ms) + 1
                        if self.fill_mode == "glued":
                            # drop late portion: advance PTS without emitting placeholders
                            self._next_pts += self._samples_per_frame * missing
                        else:
                            for _ in range(missing):
                                filler = self._make_fill_frame()
                                filler.pts = self._next_pts
                                filler.time_base = self._time_base
                                await self._fan_out(filler)
                                self._next_pts += self._samples_per_frame
                        last_emit = now

                # 2) PTS-based loss handling (if upstream PTS jumped)
                while frame.pts > self._next_pts:
                    if self.fill_mode == "glued":
                        self._next_pts += self._samples_per_frame
                    else:
                        filler = self._make_fill_frame()
                        filler.pts = self._next_pts
                        filler.time_base = self._time_base
                        await self._fan_out(filler)
                        self._next_pts += self._samples_per_frame

                # forward real frame
                frame.pts = self._next_pts
                frame.time_base = self._time_base
                await self._fan_out(frame)
                self._next_pts += self._samples_per_frame
                last_emit = loop.time()

        finally:
            for q in list(self.out_queues):
                q.put_nowait(None)
                self.unsubscribe(q)
            self.running = False

    async def _fan_out(self, frame):
        for q in list(self.out_queues):
            try:
                q.put_nowait(frame)
            except asyncio.QueueFull:
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

    def _make_fill_frame(self):
        if self.fill_with_silence:
            arr = np.zeros((self._channels, self._samples_per_frame), dtype=np.int16)
        else:
            omega = 2 * np.pi * self.beep_freq / self._time_base.denominator
            phases = self._phase + omega * np.arange(self._samples_per_frame, dtype=np.float32)
            self._phase = (self._phase + omega * self._samples_per_frame) % (2 * np.pi)
            wave = (np.sin(phases) * self.tone_gain).astype(np.float32)
            arr = (np.clip(wave, -1.0, 1.0) * 32767).astype(np.int16)
            if self._channels > 1:
                arr = np.vstack([arr] * self._channels)
            else:
                arr = arr[np.newaxis, :]
        out = AudioFrame.from_ndarray(arr, format='s16p', layout=self._layout_name)
        out.sample_rate = self._time_base.denominator
        return out