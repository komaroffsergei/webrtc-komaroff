import asyncio
import time
from uuid import uuid4
from src_langgraph.engine import WorkflowEngine
from src_shared.contracts import LlmResponse, WorkflowRunRequest, WorkflowRuntimeState


class MockIO:
    def __init__(self, events):
        self.events = events

    async def call_llm(self, *, parent, mode, input_data, constraints=None):
        self.events.append({'stage': 'mock_llm', 'mode': mode, 'at': time.time()})
        if parent.text == 'таймаут':
            await asyncio.sleep(10)
        data = {'workflow_id': 'free_speech@2.0.0', 'reason': 'Детерминированный demo router', 'confidence': 1.0} if mode == 'routing_decision' else {'response_text': 'Демонстрационный ответ: сообщение получено через WebRTC, обработано исходным LangGraph и возвращено по DataChannel. Внешняя модель не вызывалась.'}
        return LlmResponse(trace_id=parent.trace_id, request_id=uuid4(), session_id=parent.session_id, ts_ms=int(time.time()*1000), ok=True, data=data)

    async def call_tool(self, **kwargs):
        raise RuntimeError('External tools are disabled in this demo')


class DemoRuntime:
    def __init__(self):
        self.session_id = uuid4()
        self.runtime = WorkflowRuntimeState()

    async def run(self, text):
        events = []
        engine = WorkflowEngine(MockIO(events), memory_recent_messages=6, memory_summary_max_chars=1000, memory_context_max_chars=2000)
        request = WorkflowRunRequest(trace_id=uuid4(), request_id=uuid4(), session_id=self.session_id, ts_ms=int(time.time()*1000), text=text, runtime=self.runtime)
        started = time.perf_counter()
        response = await asyncio.wait_for(engine.run(request), timeout=2)
        self.runtime = response.next_runtime
        return {'text': response.result, 'status': response.status, 'events': events, 'elapsedMs': round((time.perf_counter()-started)*1000,2), 'runtimeVersion': self.runtime.version, 'traceId': str(response.trace_id)}
