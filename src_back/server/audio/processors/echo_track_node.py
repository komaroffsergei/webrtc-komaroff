import asyncio
from typing import Optional

from aiortc import AudioStreamTrack
from av import AudioFrame
import av
import logging

logger = logging.getLogger("audio.EchoTrackNode")


class EchoTrackNode(AudioStreamTrack):
    def __init_subclass__(cls, **kwargs):
        return super().__init_subclass__(**kwargs)

    """
    Audio sink/source node for WebRTC echo.

    Subscribes to a source node (with subscribe() -> asyncio.Queue) and exposes
    frames via AudioStreamTrack.recv() to be sent back over RTCPeerConnection.

    Responsibilities: play back audio to the browser only. No transformation,
    no modification of the stream, no influence on upstream nodes.
    """

    def __init__(self, source_node) -> None:
        super().__init__()
        self.source_node = source_node
        self.queue: asyncio.Queue = source_node.subscribe()
        self._closed = False
        logger.info("initialized and subscribed to source")

    async def recv(self) -> AudioFrame:
        if self._closed:
            raise asyncio.CancelledError
        # get first frame
        frame = await self.queue.get()
        if frame is None:
            raise asyncio.CancelledError
        # drain backlog aggressively to keep echo near real-time
        try:
            leave = 1
            last = frame
            while self.queue.qsize() > leave:
                maybe = self.queue.get_nowait()
                if maybe is None:
                    break
                last = maybe
            frame = last
        except Exception:
            pass
        # Frames are already normalized to s16p in TrackSourceNode; convert to packed on the fly if needed
        try:
            if frame.format.name == 's16p':
                # repack to s16 without resampling
                out = AudioFrame.from_ndarray(frame.to_ndarray(), format='s16', layout=frame.layout.name)
                out.sample_rate = frame.sample_rate
                out.pts = frame.pts
                out.time_base = frame.time_base
                return out
        except Exception:
            pass
        return frame

    def stop(self):
        if self._closed:
            return
        self._closed = True
        try:
            self.queue.put_nowait(None)
        except Exception:
            pass
        try:
            self.source_node.unsubscribe(self.queue)
        except Exception:
            pass
        logger.info("EchoTrackNode stopped and unsubscribed")
        try:
            super().stop()
        except Exception:
            pass
