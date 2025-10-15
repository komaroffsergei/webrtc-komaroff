import asyncio
import logging
from typing import Optional

from av import AudioFrame

logger = logging.getLogger("audio.BlankNode")


from .base import ConsumerNode


class BlankNode(ConsumerNode):
    """
    Pass-through processor node.

    - Subscribes to upstream source (must expose subscribe() -> asyncio.Queue)
    - Forwards frames to its own subscribers unchanged
    - Additionally prints each frame received
    """

    def __init__(self, source_node) -> None:
        super().__init__(source_node)

    async def _run(self) -> None:
        try:
            while True:
                frame: AudioFrame = await self.queue.get()
                if frame is None:
                    break
                # print each frame
                print(f"BlankNode: frame pts={getattr(frame, 'pts', None)} sr={getattr(frame, 'sample_rate', None)} fmt={getattr(frame, 'format', None)}")
                # passthrough to subscribers as-is
                await self.fan_out(frame)
        finally:
            for q in list(self.out_queues):
                try:
                    q.put_nowait(None)
                except Exception:
                    pass
                self.unsubscribe(q)
            self._stopped = True
