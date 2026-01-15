import asyncio
import logging
import signal
from typing import Any

import nats
from nats.aio.msg import Msg

from src_llm.settings import STACK_SERVICE_NAME
from src_llm.utils.nats_logger import NatsLogger
from src_llm.utils.nats_publisher import NatsPublisher

logger = logging.getLogger(f"{STACK_SERVICE_NAME}(BaseService)")


class BaseService:
    def __init__(
            self,
            *,
            service_name: str,
            nats_url: str,
            llm_subject: str,
            events_subject: str,
            max_concurrency: int = 1,

    ) -> None:
        self._service_name = service_name
        self._nats_url = nats_url
        self._llm_subject = llm_subject
        self._events_subject = events_subject
        self._nc: nats.NATS
        self._nats_logger: NatsLogger
        self._stop_event = asyncio.Event()
        self._tasks: set[asyncio.Task] = set()
        self._semaphore = asyncio.Semaphore(max(1, max_concurrency))
    def _register_signals(self) -> None:
        loop = asyncio.get_running_loop()
        for sig in (signal.SIGINT, signal.SIGTERM):
            try:
                loop.add_signal_handler(sig, self.stop)
            except NotImplementedError:
                logger.debug("Signal handlers are not supported on this platform")

    async def _connect(self) -> None:
        self._nc = await nats.connect(
            servers=[self._nats_url],
            name=self._service_name,
            max_reconnect_attempts=-1,
            reconnect_time_wait=2,
            ping_interval=10,
        )
        self._publisher = NatsPublisher(self._nc)
        self._nats_logger = NatsLogger(self._nc, self._events_subject, self._service_name)
        await self._nats_logger.info(f"{STACK_SERVICE_NAME} service connected")

        await self._nc.subscribe(self._llm_subject, cb=self._handle_message)
        await self._nats_logger.info(f"Subscribed to {self._llm_subject}")

    async def run(self) -> None:
        await self._connect()
        self._register_signals()
        await self.on_run()
        await self._stop_event.wait()
        await self._shutdown()

    async def _shutdown(self) -> None:
        for task in list(self._tasks):
            task.cancel()

        if self._nc:
            try:
                await self._nc.drain()
            except Exception:
                await self._nc.close()

    def stop(self) -> None:
        self._stop_event.set()

    async def _handle_message(self, msg: Msg) -> None:
        task = asyncio.create_task(self._process_message(msg))
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)

    async def _process_message(self, msg: Msg) -> None:
        if not self._nats_logger:
            return

        async with self._semaphore:
            try:
                text = await asyncio.to_thread(self.on_message, msg)
            except Exception as exc:
                logger.exception("Process message error: %s", exc)
                await self._nats_logger.error(f"Process message error: {exc}")
                await self._reply(
                    msg,
                    {"error": "process_message", "details": str(exc)},
                )
                return

        model_message = text.get("message") if isinstance(text, dict) else text
        await self._nats_logger.log(model_message, name="model_thinking", kind="control")
        await self._nats_logger.info(text, name="llm_result")
        await self._reply(msg, text)


    async def _reply(self, msg: Msg, payload: dict[str, Any]) -> None:
        if not msg.reply or not self._nc:
            return
        await self._publisher.publish(msg.reply, payload)

    def on_message(self, msg: Msg) -> Any:
        raise NotImplementedError

    async def on_run(self) -> None:
        raise NotImplementedError
