import asyncio
import importlib
import json
import sys
import types
import unittest
from unittest.mock import AsyncMock

aiohttp_module = types.ModuleType("aiohttp")
web_app_module = types.ModuleType("aiohttp.web_app")


class _FakeApplication(dict):
    pass


web_app_module.Application = _FakeApplication
aiohttp_module.web_app = web_app_module
sys.modules.setdefault("aiohttp", aiohttp_module)
sys.modules.setdefault("aiohttp.web_app", web_app_module)

src_shared_module = types.ModuleType("src_shared")
contracts_module = types.ModuleType("src_shared.contracts")
common_module = types.ModuleType("src_shared.contracts.common")


def _now_ts_ms() -> int:
    return 0


common_module.now_ts_ms = _now_ts_ms
contracts_module.common = common_module
src_shared_module.contracts = contracts_module
sys.modules.setdefault("src_shared", src_shared_module)
sys.modules.setdefault("src_shared.contracts", contracts_module)
sys.modules.setdefault("src_shared.contracts.common", common_module)

handle_transcription_module = importlib.import_module("src_core.handlers.handle_transcription")


class _DummyMsg:
    def __init__(self, payload: dict) -> None:
        self.data = json.dumps(payload, ensure_ascii=False).encode("utf-8")


class _DummyNatsClient:
    def __init__(self) -> None:
        self.requests: list[tuple[str, bytes, float]] = []

    async def request(self, subject: str, data: bytes, timeout: float):
        self.requests.append((subject, data, timeout))
        payload = {"ok": True, "session_id": "s1"}
        return _DummyMsg(payload)


class _DummyEventBus:
    def __init__(self) -> None:
        self.log = AsyncMock(return_value="evt")


class HandleTranscriptionTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.nats_client = _DummyNatsClient()
        self.app = {
            "services": {"nats_client": self.nats_client},
            "vars": {
                "NATS_AGENT_SUBJECT": "nats.agent.user123",
                "USER_ID": "user123",
                "LIVE_ASR_COMMIT_IDLE_MS": "20",
            },
            "event_bus": _DummyEventBus(),
            "live_asr_sessions": {},
        }
        self.event_log = self.app["event_bus"].log

    async def asyncTearDown(self) -> None:
        sessions = self.app.get("live_asr_sessions", {})
        if isinstance(sessions, dict):
            tasks = []
            for state in sessions.values():
                task = getattr(state, "commit_task", None)
                if task and not task.done():
                    task.cancel()
                    tasks.append(task)
            if tasks:
                await asyncio.gather(*tasks, return_exceptions=True)

    async def test_live_asr_segments_commit_once_after_idle(self) -> None:
        await handle_transcription_module.handle_transcription(
            self.app,
            {"session_id": "s1", "event": "partial", "partial": "первая"},
        )
        await handle_transcription_module.handle_transcription(
            self.app,
            {"session_id": "s1", "event": "final_received", "text": "первая часть", "phrase_id": "p1"},
        )
        await handle_transcription_module.handle_transcription(
            self.app,
            {"session_id": "s1", "event": "final_received", "text": "вторая часть", "phrase_id": "p2"},
        )

        await asyncio.sleep(0.18)

        self.assertEqual(len(self.nats_client.requests), 1)
        subject, raw_payload, timeout = self.nats_client.requests[0]
        self.assertEqual(subject, "nats.agent.user123")
        self.assertGreater(timeout, 0)
        payload = json.loads(raw_payload.decode("utf-8"))
        self.assertEqual(payload["text"], "первая часть вторая часть")
        self.assertEqual(payload["session_id"], "s1")

        transcription_calls = [
            call for call in self.event_log.await_args_list
            if call.args[:2] == ("command", "transcription")
        ]
        self.assertEqual(len(transcription_calls), 1)
        self.assertEqual(transcription_calls[0].args[2]["text"], "первая часть вторая часть")

    async def test_partial_only_does_not_call_agent(self) -> None:
        await handle_transcription_module.handle_transcription(
            self.app,
            {"session_id": "s1", "event": "partial", "partial": "черновик"},
        )

        await asyncio.sleep(0.18)

        self.assertEqual(self.nats_client.requests, [])
        voice_calls = [
            call for call in self.event_log.await_args_list
            if call.args[:2] == ("command", "voice")
        ]
        self.assertGreaterEqual(len(voice_calls), 2)
        self.assertTrue(any(call.args[2]["blocked"] is True for call in voice_calls))
        self.assertTrue(any(call.args[2]["blocked"] is False for call in voice_calls))

    async def test_text_message_still_calls_agent_immediately(self) -> None:
        response = await handle_transcription_module.handle_transcription(
            self.app,
            {"text": "привет", "session_id": "s1"},
        )

        self.assertEqual(len(self.nats_client.requests), 1)
        payload = json.loads(self.nats_client.requests[0][1].decode("utf-8"))
        self.assertEqual(payload["text"], "привет")
        self.assertEqual(response["ok"], True)
        self.assertEqual(self.app["live_asr_sessions"], {})


if __name__ == "__main__":
    unittest.main()
