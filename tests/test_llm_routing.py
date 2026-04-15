import unittest
from uuid import uuid4

from src_llm.service import LLMService
from src_shared.contracts import LlmRequest


class LlmRoutingDecisionTest(unittest.TestCase):
    @staticmethod
    def _service(payload: dict):
        service = object.__new__(LLMService)
        service._routing_input_normalized = LLMService._routing_input_normalized
        service._infer_json = lambda _req, _schema: payload
        return service

    @staticmethod
    def _request(*, text: str, allowlist: list[str]) -> LlmRequest:
        return LlmRequest(
            trace_id=uuid4(),
            correlation_id=None,
            request_id=uuid4(),
            session_id=None,
            ts_ms=1,
            mode="routing_decision",
            input={
                "text": text,
                "allowlist_workflows": allowlist,
            },
            constraints={},
        )

    def test_normalize_routing_workflow_id_maps_current_aliases(self) -> None:
        allowset = {
            "where_my_flight@2.0.0",
            "find_nearest_airport@2.0.0",
            "free_speech@2.0.0",
            "echo@2.0.0",
        }

        self.assertEqual(
            "free_speech@2.0.0",
            LLMService._normalize_routing_workflow_id("free_speech", allowset),
        )
        self.assertEqual(
            "echo@2.0.0",
            LLMService._normalize_routing_workflow_id("echo", allowset),
        )

    def test_routing_decision_rejects_legacy_workflow_id_and_falls_back_to_free_speech(self) -> None:
        service = self._service(
            {
                "workflow_id": "no_found_command@2.0.0",
                "reason": "legacy fallback",
                "confidence": 0.2,
            }
        )

        result = service._routing_decision(
            self._request(
                text="что ты умеешь",
                allowlist=[
                    "where_my_flight@2.0.0",
                    "find_nearest_airport@2.0.0",
                    "free_speech@2.0.0",
                    "echo@2.0.0",
                ],
            )
        )

        self.assertEqual("free_speech@2.0.0", result.workflow_id)

    def test_routing_decision_filters_legacy_allowlist_entries(self) -> None:
        service = self._service({})

        result = service._routing_decision(
            self._request(
                text="расскажи что-нибудь",
                allowlist=[
                    "no_found_command@2.0.0",
                    "free_speech@2.0.0",
                ],
            )
        )

        self.assertEqual("free_speech@2.0.0", result.workflow_id)


if __name__ == "__main__":
    unittest.main()
