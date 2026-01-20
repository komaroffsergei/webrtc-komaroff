import asyncio
import json
import logging
import signal
import sys

from nats.aio.client import Client as NATS

from src_agent.settings import (
    NATS_URL,
    STACK_SERVICE_NAME
)
from src_agent.agent import MCPAgent
from src_agent.utils.db import Database, create_session
from src_agent.utils.nats_logger import NatsLogger

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
        self.agent_subject = agent_subject      # e.g. nats.src_agent.user123
        self.llm_subject = llm_subject          # e.g. nats.src_llm.user123
        self.events_subject = events_subject    # e.g. nats.events.user123
        self.max_steps = max_steps

        self.nc = None
        self.agent = None
        self.nats_logger = None
        self.stop_event = asyncio.Event()

        self.db_url = db_url
        self.db: Database | None = None
        self.user_id = user_id or "anonymous"

    async def connect(self):
        """Connect to NATS + database."""
        self.nc = NATS()
        await self.nc.connect(
            servers=[NATS_URL],
            name=STACK_SERVICE_NAME,
            max_reconnect_attempts=-1,
            reconnect_time_wait=2,
            ping_interval=10,
        )
        self.nats_logger = NatsLogger(self.nc, self.events_subject, STACK_SERVICE_NAME)

        if not self.db_url:
            raise RuntimeError("db_url is not set for src_agent")

        self.db = Database(db_url=self.db_url)
        await self.db.connect()
        await self.nats_logger.info(f"{STACK_SERVICE_NAME} connected to Database")

        self.agent = MCPAgent(
            self.nc,
            llm_subject=self.llm_subject,
            max_steps=self.max_steps,
            events=self.nats_logger,
            db=self.db,
            user_id=self.user_id,
        )
        await self.nats_logger.info(f"{STACK_SERVICE_NAME} connected to NATS {NATS_URL}")

    async def subscribe(self):
        """Subscribe to NATS subjects."""
        await self.nc.subscribe(self.agent_subject, cb=self.handle_request)
        await self.nats_logger.info(f"Subscribed to {self.agent_subject}")

    async def handle_request(self, msg):
        """Handle an incoming agent request."""
        try:
            data = json.loads(msg.data.decode("utf-8"))
            prompt = (data.get("text") or "").strip()
            session_id = data.get("session_id")
            edit = data.get("edit")

            if not prompt:
                raise ValueError("Empty text in request")

            if not self.db:
                raise RuntimeError("Database is not connected")

            if not session_id:
                session_id = await create_session(self.db, user_id=self.user_id)

            result = await self.agent.run(prompt=prompt, session_id=session_id, edit=edit)
            await self._publish_result_event(result)

            payload = json.dumps(result, ensure_ascii=False).encode("utf-8")
            await msg.respond(payload)

        except Exception as e:
            logger.error(f"Error processing request: {e}", exc_info=True)
            if self.nats_logger:
                await self.nats_logger.error(f"Processing error: {e}")

            error_response = {
                "success": False,
                "error": {"type": "SERVER_EXCEPTION", "message": str(e)},
            }
            try:
                await msg.respond(json.dumps(error_response, ensure_ascii=False).encode("utf-8"))
            except Exception as respond_error:
                logger.error(f"Error sending error response: {respond_error}")

    def setup_signal_handlers(self):
        """Configure signal handlers for graceful shutdown."""
        loop = asyncio.get_running_loop()
        for sig in (signal.SIGINT, signal.SIGTERM):
            loop.add_signal_handler(
                sig,
                lambda s=sig: asyncio.create_task(self.shutdown(s))
            )

    async def shutdown(self, signal=None):
        """Gracefully shutdown the server."""
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

        if self.db:
            try:
                await self.db.close()
            except Exception as e:
                logger.error(f"Error closing DB pool: {e}")

    async def run(self):
        """Run the server."""
        try:
            await self.connect()
            await self.subscribe()
            self.setup_signal_handlers()

            logger.info(f"{STACK_SERVICE_NAME} is running and waiting for requests...")
            if self.nats_logger:
                await self.nats_logger.info(f"{STACK_SERVICE_NAME} is ready")

            await self.stop_event.wait()

        except Exception as e:
            logger.exception(f"Server error: {e}")
            sys.exit(1)
        finally:
            await self.shutdown()

    async def _publish_result_event(self, result: object) -> None:
        if not self.nats_logger or not isinstance(result, dict):
            return

        client_handler = result.get("client_handler") if isinstance(result.get("client_handler"), dict) else {}
        raw_artifacts = client_handler.get("artifacts") if isinstance(client_handler.get("artifacts"), dict) else None
        artifacts = self._normalize_artifacts(raw_artifacts)

        text = self._extract_message_text(result, artifacts)
        if not text and result.get("success") is True:
            text = "Done."
        if text:
            data: dict[str, object] = {
                "type": "answer" if result.get("success") is True else "system",
                "text": text,
            }
            if artifacts:
                data["artifacts"] = artifacts
            await self.nats_logger.log("command", "message", data)

        command = client_handler.get("command")
        if isinstance(command, str) and command and command not in ("ASK_USER_INPUT", "SHOW_MESSAGE", "SHOW_ERROR_MESSAGE"):
            data: dict[str, object] = {"command": command}
            if artifacts:
                data["artifacts"] = artifacts
            await self.nats_logger.log("command", "client_handler", data)

    def _normalize_artifacts(self, raw: object) -> dict[str, object] | None:
        if not isinstance(raw, dict):
            return None
        all_keys_raw = raw.get("all")
        all_keys = [str(x) for x in all_keys_raw] if isinstance(all_keys_raw, list) else []
        last_raw = raw.get("last")
        last = str(last_raw) if isinstance(last_raw, str) else None
        payload = raw.get("payload") if isinstance(raw.get("payload"), dict) else {}
        if not all_keys and last is None and not payload:
            return None
        return {"all": all_keys, "last": last, "payload": payload}

    def _extract_message_text(self, result: dict, artifacts: dict[str, object] | None) -> str | None:
        if isinstance(result.get("result"), str) and result["result"].strip():
            return result["result"].strip()

        err = result.get("error") if isinstance(result.get("error"), dict) else None
        if err and isinstance(err.get("message"), str) and err["message"].strip():
            return err["message"].strip()

        if not artifacts:
            return None
        payload = artifacts.get("payload")
        last = artifacts.get("last")
        if not isinstance(payload, dict) or not isinstance(last, str) or last not in payload:
            return None
        last_payload = payload.get(last)
        if not isinstance(last_payload, dict):
            return None
        for key in ("message", "summary", "prompt", "text"):
            val = last_payload.get(key)
            if isinstance(val, str) and val.strip():
                return val.strip()
        return None
