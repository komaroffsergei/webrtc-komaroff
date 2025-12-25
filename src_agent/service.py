import asyncio
import json
import logging
import signal
import sys
from nats.aio.client import Client as NATS
from settings import (
    NATS_URL,
    STACK_SERVICE_NAME
)
from agent import MCPAgent
from src_agent.utils.db import create_session
# from src_agent.utils.db import Database, create_session
from utils.nats_logger import NatsLogger
# from src_agent.repositories.sessions import create_session
# from src_agent.repositories.events import log_event

logger = logging.getLogger(STACK_SERVICE_NAME)


class AgentServer:
    def __init__(
        self,
        *,
        nats_url: str,
        agent_subject: str,
        llm_subject: str,
        events_subject: str,
        max_steps: int = 10,
        db_url: str = None,
        user_id: str = None,

    ):
        self.nats_url = nats_url
        self.agent_subject = agent_subject      # ← nats.src_agent.user123
        self.llm_subject = llm_subject          # ← nats.src_llm.user123
        self.events_subject = events_subject        # ← nats.events.user123
        self.max_steps = max_steps
        self.nc = None
        self.agent = None
        self.nats_logger = None
        self.stop_event = asyncio.Event()
        self.db_url = db_url
        self.db = None
        self.user_id = user_id

    async def connect(self):
        """Подключение к NATS"""
        self.nc = NATS()
        await self.nc.connect(
            servers=[NATS_URL],
            name=STACK_SERVICE_NAME,
            max_reconnect_attempts=-1,
            reconnect_time_wait=2,
            ping_interval=10,
        )
        self.nats_logger = NatsLogger(self.nc, self.events_subject, STACK_SERVICE_NAME)
        # self.db = Database(db_url=self.db_url)
        # await self.db.connect()
        await self.nats_logger.info(f"{STACK_SERVICE_NAME} connected to Database")
        self.agent = MCPAgent(self.nc,
                              llm_subject=self.llm_subject,
                              events_subject=self.events_subject,
                              max_steps=self.max_steps,
                              db=self.db)
        await self.nats_logger.info(f"{STACK_SERVICE_NAME} connected to NATS {NATS_URL}")

    async def subscribe(self):
        """Подписка на темы NATS"""
        await self.nc.subscribe(self.agent_subject, cb=self.handle_request)
        await self.nats_logger.info(f"Subscribed to {self.agent_subject}")

    async def handle_request(self, msg):
        """Обработка входящего запроса на выполнение агента"""
        try:
            data = json.loads(msg.data.decode("utf-8"))
            prompt = data.get("text", "").strip()
            session_id = data.get("session_id")

            if not prompt:
                raise ValueError("Empty text in request")
            #
            if not session_id:
                session_id = create_session(self.user_id)


            #Логируем пользовательский ввод
            # await log_event(
            #     self.db,
            #     session_id=session_id,
            #     intent_id=None,
            #     role="USER",
            #     event_type="MESSAGE",
            #     name=None,
            #     input={"text": user_text},
            #     output=None,
            # )

            # Запуск агента
            result = await self.agent.run(prompt=prompt, session_id=session_id)
            payload = json.dumps(
                result,
                ensure_ascii=False
            ).encode("utf-8")

            await msg.respond(payload)
            # await self.nats_logger.info(f"Request processed successfully")
            # logger.info("Request processed successfully")

        except Exception as e:
            logger.error(f"Error processing request: {e}", exc_info=True)
            await self.nats_logger.error(f"Processing error: {e}")

            error_response = {
                "status": "error",
                "error": str(e)
            }
            try:
                await msg.respond(json.dumps(error_response, ensure_ascii=False).encode('utf-8'))
            except Exception as respond_error:
                logger.error(f"Error sending error response: {respond_error}")

    def setup_signal_handlers(self):
        """Настройка обработчиков сигналов для graceful shutdown"""
        loop = asyncio.get_running_loop()

        for sig in (signal.SIGINT, signal.SIGTERM):
            loop.add_signal_handler(
                sig,
                lambda s=sig: asyncio.create_task(self.shutdown(s))
            )

    async def shutdown(self, signal=None):
        """Graceful shutdown сервера"""
        if signal:
            logger.info(f"Received exit signal {signal.name}")

        logger.info("Shutting down agent server...")
        self.stop_event.set()

        if self.nc:
            try:
                await self.nc.drain()
            except Exception as e:
                logger.error(f"Error draining NATS connection: {e}")
            finally:
                await self.nc.close()
                logger.info("NATS connection closed")

    async def run(self):
        """Запуск сервера"""
        try:
            await self.connect()
            await self.subscribe()
            self.setup_signal_handlers()

            logger.info(f"{STACK_SERVICE_NAME} is running and waiting for requests...")
            await self.nats_logger.info(f"{STACK_SERVICE_NAME} is ready")

            # Ожидание сигнала остановки
            await self.stop_event.wait()

        except Exception as e:
            logger.exception(f"Server error: {e}")
            sys.exit(1)
        finally:
            await self.shutdown()