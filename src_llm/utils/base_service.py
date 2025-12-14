import asyncio
import json
import logging
import signal
import time
from typing import Any, Dict

import nats
from nats.aio.msg import Msg

from src_llm.settings import STACK_SERVICE_NAME
from src_llm.utils.nats_logger import NatsLogger

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

        self._nats_logger = NatsLogger(self._nc, self._events_subject, self._service_name)
        await self._nats_logger.info(f"{STACK_SERVICE_NAME} service connected")

        await self._nc.subscribe(self._llm_subject, cb=self._handle_message)
        await self._nats_logger.info(f"Subscribed to {self._llm_subject}")

    async def run(self) -> None:
        await self._connect()
        self._register_signals()
        await self._stop_event.wait()
        await self._shutdown()
        await self.on_run()

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

    async def _log_error(self, message: str) -> None:
        if self._nats_logger:
            await self._nats_logger.error(message)

    async def _handle_message(self, msg: Msg) -> None:
        task = asyncio.create_task(self._process_message(msg))
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)

    async def _process_message(self, msg: Msg) -> None:
        if not self._nats_logger:
            return

        started = time.perf_counter()

        # msg.data – bytes, делаем человекочитаемую строку
        try:
            msg_str = msg.data.decode("utf-8", errors="replace")
        except Exception:
            msg_str = repr(msg.data)

        # await self._nats_logger.info(f"Process message data={msg_str}")

        async with self._semaphore:
            try:
                # ВАЖНО: передаём msg в on_message
                text = await asyncio.to_thread(self.on_message, msg)
            except Exception as exc:
                logger.exception("Process message error: %s", exc)
                await self._log_error(f"Process message error: {exc}")
                await self._reply(
                    msg,
                    {"data": msg_str, "error": "process_message", "details": str(exc)},
                )
                return

        transcribe_time = time.perf_counter() - started
        # message = {
        #     "input": msg_str,
        #     "output": text,
        #     "time": transcribe_time,
        # }

        await self._nats_logger.info(
            f"Process message finished data={msg_str} time={transcribe_time:.3f}s"
        )
        await self._nats_logger.info(text, name="llm_result")
        await self._reply(msg, text)


    async def _reply(self, msg: Msg, payload: dict[str, Any]) -> None:
        if not msg.reply or not self._nc:
            return
        await self._nc.publish(msg.reply, self.to_json_safe(payload))

    def on_message(self, msg: Msg) -> None:
        raise NotImplementedError

    async def on_run(self) -> None:
        raise NotImplementedError

    def to_json_safe(self, obj):
        if obj is None:
            return None

        if isinstance(obj, (str, int, float, bool)):
            return obj

        if isinstance(obj, dict):
            return {k: self.to_json_safe(v) for k, v in obj.items()}

        if isinstance(obj, list):
            return [self.to_json_safe(v) for v in obj]

        # SDK-объекты (Message, ToolCall и т.п.)
        if hasattr(obj, "__dict__"):
            return self.to_json_safe(vars(obj))

        # крайний случай
        return str(obj)
