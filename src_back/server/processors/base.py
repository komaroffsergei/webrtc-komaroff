import asyncio
import logging
from typing import List, Optional

from av import AudioFrame

logger = logging.getLogger("audio.BaseNode")


class FanOutNode:
    """Common fan-out helpers for nodes that multiplex frames to multiple subscribers."""

    def __init__(self) -> None:
        self.out_queues: List[asyncio.Queue] = []

    def subscribe(self) -> asyncio.Queue:
        q: asyncio.Queue = asyncio.Queue()
        self.out_queues.append(q)
        return q

    def unsubscribe(self, q: asyncio.Queue) -> None:
        try:
            self.out_queues.remove(q)
        except ValueError:
            pass

    async def fan_out(self, frame: AudioFrame) -> None:
        """Enqueue a frame for all subscribers with drop-oldest backpressure."""
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
                logger.debug(f"fan_out error: {e}")

    async def close_downstreams(self) -> None:
        for q in list(self.out_queues):
            try:
                q.put_nowait(None)
            except Exception:
                pass
            self.unsubscribe(q)


class ConsumerNode(FanOutNode):
    """
    A base class for nodes that consume frames from an upstream source and optionally
    emit frames to downstream subscribers.

    Subclasses must implement async handle_frame(frame: AudioFrame) -> None
    and call await self.fan_out(frame_or_new) when they want to forward.

    Supports late binding: node may be constructed without a source and bound later
    via bind_source(source_node) before start().
    """

    def __init__(self, source_node: Optional[FanOutNode] = None) -> None:
        super().__init__()
        self.source_node: Optional[FanOutNode] = None
        self.queue: Optional[asyncio.Queue] = None
        self._task: Optional[asyncio.Task] = None
        self._stopped: bool = False
        if source_node is not None:
            self.bind_source(source_node)

    def bind_source(self, source_node: FanOutNode) -> None:
        self.source_node = source_node
        self.queue = source_node.subscribe()

    async def start(self) -> None:
        if self._task is not None:
            return
        if self.queue is None:
            raise RuntimeError("ConsumerNode.start() called before binding a source via bind_source().")
        self._task = asyncio.create_task(self._run())

    async def stop(self) -> None:
        if self._stopped:
            return
        self._stopped = True
        try:
            if self.queue is not None:
                self.queue.put_nowait(None)
        except Exception:
            pass
        if self._task is not None:
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None
        await self.close_downstreams()

    async def _run(self) -> None:
        assert self.queue is not None, "_run requires queue to be bound"
        try:
            while True:
                frame = await self.queue.get()
                if frame is None:
                    break
                await self.handle_frame(frame)
        finally:
            await self.close_downstreams()

    async def handle_frame(self, frame: AudioFrame) -> None:
        raise NotImplementedError


# Optional: base class for nodes that expose AudioStreamTrack semantics
try:
    from aiortc import AudioStreamTrack  # type: ignore
except Exception:  # pragma: no cover
    AudioStreamTrack = object  # fallback for environments without aiortc


class TrackRelayNode(AudioStreamTrack):
    """
    Base class for AudioStreamTrack implementations that relay frames from a source node.
    Subclasses may override transform_frame(frame) -> AudioFrame to adjust format.
    """

    def __init__(self, source_node) -> None:
        try:
            super().__init__()
        except Exception:
            # When AudioStreamTrack is a no-op object
            pass
        self.source_node = source_node
        self.queue: asyncio.Queue = source_node.subscribe()
        self._closed = False

    async def recv(self) -> AudioFrame:
        if self._closed:
            raise asyncio.CancelledError
        frame = await self.queue.get()
        if frame is None:
            raise asyncio.CancelledError
        # optionally drain backlog in subclass if required
        return await self.transform_frame(frame)

    async def transform_frame(self, frame: AudioFrame) -> AudioFrame:
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
        try:
            super().stop()
        except Exception:
            pass
