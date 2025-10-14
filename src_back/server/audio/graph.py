import asyncio
import inspect
import logging
from typing import List

logger = logging.getLogger("audio.Graph")


class AudioGraph:
    """
    Simple graph orchestrator for audio processing nodes.

    Responsibilities:
    - Keep a registry of nodes participating in the graph
    - Start nodes: for async start() create tasks, for sync start() call directly
    - Stop nodes: call stop() if provided and cancel background tasks

    A node may implement:
    - subscribe() -> asyncio.Queue            # to expose frames
    - start() -> coroutine or None            # to start consuming/producing
    - stop() -> coroutine or None             # to gracefully stop (optional)
    """

    def __init__(self) -> None:
        self.nodes: List[object] = []
        self.tasks: List[asyncio.Task] = []
        self.started: bool = False

    def add(self, node: object) -> object:
        self.nodes.append(node)
        return node

    async def start(self) -> None:
        if self.started:
            return
        self.started = True

        for node in self.nodes:
            start_fn = getattr(node, "start", None)
            if start_fn is None:
                continue
            try:
                ret = start_fn()
                if inspect.isawaitable(ret):
                    task = asyncio.create_task(ret)
                    self.tasks.append(task)
                    logger.info(f"started async node {node.__class__.__name__}")
                else:
                    logger.info(f"started sync node {node.__class__.__name__}")
            except Exception as e:
                logger.error(f"node start error in {node.__class__.__name__}: {e}")

    async def stop(self) -> None:
        # try graceful stop() on nodes first
        for node in self.nodes:
            stop_fn = getattr(node, "stop", None)
            if stop_fn is None:
                continue
            try:
                ret = stop_fn()
                if inspect.isawaitable(ret):
                    await ret
                    logger.info(f"stopped async node {node.__class__.__name__}")
                else:
                    logger.info(f"stopped sync node {node.__class__.__name__}")
            except Exception as e:
                logger.error(f"node stop error in {node.__class__.__name__}: {e}")

        # cancel any remaining tasks
        for t in self.tasks:
            if not t.done():
                t.cancel()
                try:
                    await t
                except asyncio.CancelledError:
                    pass
                except Exception as e:
                    logger.error(f"task cancel error: {e}")
        self.tasks.clear()
        self.started = False
