import asyncio
import json
import logging
import signal
import sys
from nats.aio.client import Client as NATS
from settings import (
    NATS_URL,
    NATS_AGENT_SUBJECT,
    NATS_LOGS_SUBJECT,
    STACK_SERVICE_NAME
)
from agent import MCPAgent
from utils.sse import NatsLogger

logger = logging.getLogger(STACK_SERVICE_NAME)


class AgentServer:
    def __init__(self):
        self.nc = None
        self.agent = None
        self.nats_logger = None
        self.stop_event = asyncio.Event()

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

        self.nats_logger = NatsLogger(self.nc, NATS_LOGS_SUBJECT, STACK_SERVICE_NAME)
        self.agent = MCPAgent(self.nc)

        await self.nats_logger.info(f"{STACK_SERVICE_NAME} connected to NATS")
        logger.info(f"Connected to NATS at {NATS_URL}")

    async def subscribe(self):
        """Подписка на темы NATS"""
        await self.nc.subscribe(NATS_AGENT_SUBJECT, cb=self.handle_request)
        await self.nats_logger.info(f"Subscribed to {NATS_AGENT_SUBJECT}")
        logger.info(f"Subscribed to {NATS_AGENT_SUBJECT}")

    async def handle_request(self, msg):
        """Обработка входящего запроса на выполнение агента"""
        try:
            data = json.loads(msg.data.decode('utf-8'))
            user_text = data.get('text', '').strip()

            if not user_text:
                raise ValueError("Empty text in request")

            await self.nats_logger.info(f"Processing request: {user_text[:50]}...")
            logger.info(f"Processing request: {user_text[:50]}...")

            # Запуск агента
            result = await self.agent.run(user_text)

            # Отправка результата
            response = {
                "status": "success",
                "result": result
            }

            await msg.respond(json.dumps(response, ensure_ascii=False).encode('utf-8'))
            await self.nats_logger.info(f"Request processed successfully")
            logger.info("Request processed successfully")

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