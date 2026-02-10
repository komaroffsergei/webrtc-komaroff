from __future__ import annotations

import asyncio
import json
import logging
import signal
from dataclasses import dataclass
from typing import Any, Optional
from uuid import UUID, uuid4

import asyncpg
import httpx
from fastapi import FastAPI
from nats.aio.client import Client as NATS
from nats.aio.msg import Msg
from pydantic import BaseModel
import uvicorn

from src_n8n.settings import (
    WORKFLOW_ENTITY_IDS,
    WORKFLOW_ROUTER,
    WORKFLOW_WEBHOOK_PATHS,
    NATS_LLM_SUBJECT_PREFIX,
    NATS_TOOLS_PREFIX,
)
from src_shared.contracts import (
    ErrorInfo,
    LlmRequest,
    LlmResponse,
    N8nRunRequest,
    N8nRunResponse,
    ServiceHealthRequest,
    ServiceHealthResponse,
    ToolCallRequest,
    ToolCallResponse,
    now_ts_ms,
)

logger = logging.getLogger("src_n8n")


@dataclass
class BridgeDeps:
    nc: NATS
    pg: asyncpg.Pool
    http: httpx.AsyncClient
    n8n_webhook_base_url: str
    n8n_http_timeout_s: float
    user_id: str


class N8nBridgeService:
    def __init__(
        self,
        *,
        nats_url: str,
        database_url: str,
        n8n_webhook_base_url: str,
        n8n_http_timeout_s: float,
        n8n_run_subject: str,
        n8n_health_subject: str,
        tool_proxy_host: str,
        tool_proxy_port: int,
        user_id: str,
    ) -> None:
        self.nats_url = nats_url
        self.database_url = database_url
        self.n8n_webhook_base_url = n8n_webhook_base_url.rstrip("/")
        self.n8n_http_timeout_s = float(n8n_http_timeout_s)
        self.n8n_run_subject = n8n_run_subject
        self.n8n_health_subject = n8n_health_subject
        self.tool_proxy_host = tool_proxy_host
        self.tool_proxy_port = int(tool_proxy_port)
        self.user_id = user_id

        self._deps: Optional[BridgeDeps] = None
        self._stop = asyncio.Event()

        self._tool_app = FastAPI(title="src_n8n tool proxy")

        @self._tool_app.post("/tool")
        async def tool_handler(payload: dict[str, Any]) -> dict[str, Any]:
            try:
                req = ToolCallRequest.model_validate(payload)
            except Exception as exc:
                trace_id = uuid4()
                if payload.get("trace_id"):
                    try:
                        trace_id = UUID(str(payload["trace_id"]))
                    except Exception:
                        trace_id = uuid4()

                request_id = uuid4()
                if payload.get("request_id"):
                    try:
                        request_id = UUID(str(payload["request_id"]))
                    except Exception:
                        request_id = uuid4()

                session_id = None
                if payload.get("session_id"):
                    try:
                        session_id = UUID(str(payload["session_id"]))
                    except Exception:
                        session_id = None
                resp = ToolCallResponse(
                    trace_id=trace_id,
                    correlation_id=payload.get("correlation_id"),
                    request_id=request_id,
                    session_id=session_id,
                    ts_ms=now_ts_ms(),
                    ok=False,
                    error=ErrorInfo(code="invalid_tool_call", message=str(exc)),
                )
                return json.loads(resp.model_dump_json())

            try:
                resp = await self._dispatch_tool_call(req)
            except Exception as exc:
                logger.exception("Tool call failed")
                resp = ToolCallResponse(
                    trace_id=req.trace_id,
                    correlation_id=req.correlation_id,
                    request_id=req.request_id,
                    session_id=req.session_id,
                    ts_ms=now_ts_ms(),
                    ok=False,
                    error=ErrorInfo(code="tool_call_failed", message=str(exc)),
                )
            return json.loads(resp.model_dump_json())

    async def run(self) -> None:
        nc = NATS()
        await nc.connect(
            servers=[self.nats_url],
            name="src_n8n",
            max_reconnect_attempts=-1,
            reconnect_time_wait=2,
            ping_interval=10,
        )

        pg = await asyncpg.create_pool(self.database_url, min_size=1, max_size=10)
        http = httpx.AsyncClient(timeout=httpx.Timeout(self.n8n_http_timeout_s))

        self._deps = BridgeDeps(
            nc=nc,
            pg=pg,
            http=http,
            n8n_webhook_base_url=self.n8n_webhook_base_url,
            n8n_http_timeout_s=self.n8n_http_timeout_s,
            user_id=self.user_id,
        )

        logger.info("Using n8n webhook base URL: %s", self.n8n_webhook_base_url)

        await self._ensure_static_webhooks_with_retry()

        # Queue groups prevent duplicate processing if multiple bridge instances are running.
        await nc.subscribe(self.n8n_run_subject, queue="src_n8n.run.q", cb=self._handle_run)
        await nc.subscribe(self.n8n_health_subject, queue="src_n8n.health.q", cb=self._handle_health)

        tool_server = uvicorn.Server(
            uvicorn.Config(
                self._tool_app,
                host=self.tool_proxy_host,
                port=self.tool_proxy_port,
                log_level="info",
            )
        )

        loop = asyncio.get_running_loop()
        for sig in (signal.SIGINT, signal.SIGTERM):
            loop.add_signal_handler(sig, lambda s=sig: asyncio.create_task(self.shutdown(s)))

        tool_task = asyncio.create_task(tool_server.serve())
        await self._stop.wait()
        tool_server.should_exit = True
        await tool_task

        await http.aclose()
        await pg.close()
        await nc.drain()
        await nc.close()

    async def shutdown(self, signal_obj=None) -> None:
        logger.info("Shutdown requested: %s", getattr(signal_obj, "name", signal_obj))
        self._stop.set()

    async def _ensure_static_webhooks_with_retry(self) -> None:
        last_error: Exception | None = None
        for attempt in range(1, 31):
            try:
                await self._ensure_static_webhooks()
                return
            except Exception as exc:
                last_error = exc
                logger.warning(
                    "Failed to ensure n8n webhook_entity rows (attempt=%s/30): %s",
                    attempt,
                    str(exc),
                )
                await asyncio.sleep(1)
        raise RuntimeError(f"Failed to ensure static n8n webhooks: {last_error}")

    async def _ensure_static_webhooks(self) -> None:
        assert self._deps is not None
        rows: list[tuple[str, str, str, str]] = []
        for runtime_workflow_id, webhook_path in WORKFLOW_WEBHOOK_PATHS.items():
            workflow_entity_id = WORKFLOW_ENTITY_IDS.get(runtime_workflow_id)
            if not workflow_entity_id:
                continue
            rows.append((webhook_path, "POST", "Webhook", workflow_entity_id))

        if not rows:
            return

        async with self._deps.pg.acquire() as conn:
            existing_ids = {
                r["id"]
                for r in await conn.fetch(
                    'select id from n8n.workflow_entity where id = any($1::text[])',
                    list({row[3] for row in rows}),
                )
            }
            filtered = [row for row in rows if row[3] in existing_ids]
            if not filtered:
                return
            await conn.executemany(
                """
                insert into n8n.webhook_entity("webhookPath", method, node, "workflowId")
                values ($1, $2, $3, $4)
                on conflict ("webhookPath", method) do update
                set node = excluded.node, "workflowId" = excluded."workflowId"
                """,
                filtered,
            )

    async def _handle_health(self, msg: Msg) -> None:
        try:
            raw = json.loads(msg.data.decode("utf-8"))
            req = ServiceHealthRequest.model_validate(raw)

            ok = self._deps is not None
            resp = ServiceHealthResponse(
                trace_id=req.trace_id,
                correlation_id=req.correlation_id,
                request_id=req.request_id,
                session_id=req.session_id,
                ts_ms=now_ts_ms(),
                ok=ok,
                status="healthy" if ok else "unhealthy",
                details={"service": "src_n8n"},
            )
            await msg.respond(resp.model_dump_json().encode("utf-8"))
        except Exception as exc:
            logger.exception("Health request failed")
            resp = ServiceHealthResponse(
                trace_id=uuid4(),
                correlation_id=None,
                request_id=uuid4(),
                session_id=None,
                ts_ms=now_ts_ms(),
                ok=False,
                status="unhealthy",
                details={"service": "src_n8n"},
                error=ErrorInfo(code="health_failed", message=str(exc)),
            )
            await msg.respond(resp.model_dump_json().encode("utf-8"))

    async def _handle_run(self, msg: Msg) -> None:
        if not self._deps:
            return

        try:
            raw = json.loads(msg.data.decode("utf-8"))
            req = N8nRunRequest.model_validate(raw)
        except Exception as exc:
            logger.exception("Invalid n8n.run payload")
            resp = N8nRunResponse(
                trace_id=uuid4(),
                correlation_id=None,
                request_id=uuid4(),
                session_id=None,
                ts_ms=now_ts_ms(),
                status="FAILED",
                result="",
                errors=[ErrorInfo(code="invalid_request", message=str(exc))],
            )
            await msg.respond(resp.model_dump_json().encode("utf-8"))
            return

        if req.session_id is None:
            resp = N8nRunResponse(
                trace_id=req.trace_id,
                correlation_id=req.correlation_id,
                request_id=req.request_id,
                session_id=None,
                ts_ms=now_ts_ms(),
                status="FAILED",
                result="",
                errors=[ErrorInfo(code="missing_session_id", message="session_id is required")],
            )
            await msg.respond(resp.model_dump_json().encode("utf-8"))
            return

        try:
            await self._ensure_session_row(req.session_id)
        except Exception as exc:
            logger.exception("Failed to ensure sessions row")
            resp = N8nRunResponse(
                trace_id=req.trace_id,
                correlation_id=req.correlation_id,
                request_id=req.request_id,
                session_id=req.session_id,
                ts_ms=now_ts_ms(),
                status="FAILED",
                result="",
                errors=[ErrorInfo(code="db_session_failed", message=str(exc))],
                next_runtime=req.runtime,
            )
            await msg.respond(resp.model_dump_json().encode("utf-8"))
            return

        # Idempotency: return stored response if request_id already exists.
        try:
            existing = await self._load_cached_response(req.request_id)
        except Exception as exc:
            logger.warning("Failed to load cached response (request_id=%s): %s", str(req.request_id), str(exc))
            existing = None
        if existing is not None:
            await msg.respond(existing.model_dump_json().encode("utf-8"))
            return

        try:
            await self._insert_request_row(req)
        except Exception as exc:
            logger.warning("Failed to insert runtime_requests row (request_id=%s): %s", str(req.request_id), str(exc))

        try:
            workflow_id = req.runtime.active_workflow_id or WORKFLOW_ROUTER
            path = WORKFLOW_WEBHOOK_PATHS.get(workflow_id)
            if not path:
                raise RuntimeError(f"Unknown workflow_id: {workflow_id}")

            resp = await self._call_n8n_webhook(path=path, req=req)
            try:
                await self._store_response(req.request_id, resp)
            except Exception as exc:
                logger.warning("Failed to store response (request_id=%s): %s", str(req.request_id), str(exc))
            await msg.respond(resp.model_dump_json().encode("utf-8"))
        except Exception as exc:
            logger.exception("n8n execution failed")
            resp = N8nRunResponse(
                trace_id=req.trace_id,
                correlation_id=req.correlation_id,
                request_id=req.request_id,
                session_id=req.session_id,
                ts_ms=now_ts_ms(),
                status="FAILED",
                result="",
                errors=[ErrorInfo(code="workflow_failed", message=str(exc))],
                next_runtime=req.runtime,
            )
            try:
                await self._store_response(req.request_id, resp)
            except Exception as store_exc:
                logger.warning(
                    "Failed to store failed response (request_id=%s): %s",
                    str(req.request_id),
                    str(store_exc),
                )
            await msg.respond(resp.model_dump_json().encode("utf-8"))

    async def _call_n8n_webhook(self, *, path: str, req: N8nRunRequest) -> N8nRunResponse:
        assert self._deps is not None
        url = f"{self._deps.n8n_webhook_base_url}/{path}"
        workflow_entity_id = path.split("/", 1)[0] if isinstance(path, str) and "/" in path else None
        payload = json.loads(req.model_dump_json())
        try:
            r = await self._deps.http.post(url, json=payload)
        except httpx.RequestError as exc:
            raise RuntimeError(
                f"Failed to call n8n webhook (url={url}). "
                "Check N8N_WEBHOOK_BASE_URL and that the n8n webhook server is reachable. "
                "Hints: in Docker use http://n8n_webhook:5678/webhook; locally use http://127.0.0.1:5679/webhook."
            ) from exc
        if r.status_code == 404:
            # n8n import/activation can wipe webhook_entity rows; restore and retry once.
            logger.warning("n8n webhook returned 404; re-ensuring webhook_entity rows and retrying. url=%s", url)
            await self._ensure_static_webhooks_with_retry()
            try:
                r = await self._deps.http.post(url, json=payload)
            except httpx.RequestError as exc:
                raise RuntimeError(
                    f"Failed to call n8n webhook after restoring webhook entities (url={url}). "
                    "Check N8N_WEBHOOK_BASE_URL and that the n8n webhook server is reachable. "
                    "Hints: in Docker use http://n8n_webhook:5678/webhook; locally use http://127.0.0.1:5679/webhook."
                ) from exc
        if r.status_code >= 500:
            dbg = None
            if workflow_entity_id:
                try:
                    dbg = await self._load_latest_execution_error(workflow_entity_id)
                except Exception as exc:
                    logger.warning("Failed to load n8n execution error details: %s", str(exc))
            msg = f"n8n returned {r.status_code} for url={url}."
            if dbg:
                msg = (
                    f"{msg} execution_id={dbg.get('execution_id')} node={dbg.get('node_name')} "
                    f"error={dbg.get('error_name')} http_code={dbg.get('http_code')} message={dbg.get('message')}"
                )
            msg = (
                f"{msg} Hint: n8n must be able to reach the tool proxy URL. "
                "Ensure TOOL_PROXY_URL points to http://src_n8n:9000/tool and that the src_n8n container is running."
            )
            raise RuntimeError(msg)
        r.raise_for_status()
        data = r.json()
        resp = N8nRunResponse.model_validate(data)
        if resp.trace_id != req.trace_id or resp.session_id != req.session_id:
            raise RuntimeError("n8n response trace/session mismatch")
        return resp

    async def _load_latest_execution_error(self, workflow_entity_id: str) -> dict[str, Any] | None:
        """
        Best-effort helper to extract the most recent execution error details from n8n DB.

        This is a dev UX improvement: n8n webhooks often respond with a generic 500, so we read
        the execution record to provide a concrete reason (DNS, tool proxy unreachable, etc).
        """
        assert self._deps is not None
        async with self._deps.pg.acquire() as conn:
            exec_id = await conn.fetchval(
                """
                select id
                from n8n.execution_entity
                where "workflowId" = $1
                  and status = 'error'
                  and "startedAt" >= now() - interval '60 seconds'
                order by id desc
                limit 1
                """,
                workflow_entity_id,
            )
            if not exec_id:
                return None
            data_txt = await conn.fetchval(
                """
                select left(data, 200000)
                from n8n.execution_data
                where "executionId" = $1
                """,
                int(exec_id),
            )
            if not isinstance(data_txt, str) or not data_txt:
                return {"execution_id": int(exec_id)}

        try:
            raw = json.loads(data_txt)
        except Exception:
            return {"execution_id": int(exec_id)}

        best: dict[str, Any] = {"execution_id": int(exec_id)}
        stack: list[Any] = [raw]
        while stack:
            cur = stack.pop()
            if isinstance(cur, dict):
                name = cur.get("name")
                message = cur.get("message")
                node = cur.get("node")
                http_code = cur.get("httpCode")
                if isinstance(name, str) and isinstance(message, str) and "Error" in name:
                    best.update(
                        {
                            "error_name": name,
                            "message": message,
                            "node_name": node if isinstance(node, str) else None,
                            "http_code": http_code if isinstance(http_code, str) else None,
                        }
                    )
                    break
                for v in cur.values():
                    stack.append(v)
            elif isinstance(cur, list):
                stack.extend(cur)

        return best

    async def _dispatch_tool_call(self, req: ToolCallRequest) -> ToolCallResponse:
        assert self._deps is not None
        tool_name = req.tool_name.strip()

        if tool_name.startswith("llm."):
            mode = tool_name.split(".", 1)[1].strip()
            try:
                llm_req = LlmRequest(
                    trace_id=req.trace_id,
                    correlation_id=req.correlation_id,
                    request_id=req.request_id,
                    session_id=req.session_id,
                    ts_ms=req.ts_ms,
                    mode=mode,  # type: ignore[arg-type]
                    input=req.args.get("input") if isinstance(req.args.get("input"), dict) else {},
                    constraints=req.args.get("constraints") if isinstance(req.args.get("constraints"), dict) else {},
                )
            except Exception as exc:
                return ToolCallResponse(
                    trace_id=req.trace_id,
                    correlation_id=req.correlation_id,
                    request_id=req.request_id,
                    session_id=req.session_id,
                    ts_ms=now_ts_ms(),
                    ok=False,
                    artifact_key=f"llm:{tool_name}:{req.request_id}",
                    data=None,
                    error=ErrorInfo(code="invalid_llm_request", message=str(exc)),
                )
            subject = f"{NATS_LLM_SUBJECT_PREFIX}{self.user_id}"
            msg = await self._deps.nc.request(subject, llm_req.model_dump_json().encode("utf-8"), timeout=120)
            llm_resp = LlmResponse.model_validate(json.loads(msg.data.decode("utf-8")))
            return ToolCallResponse(
                trace_id=req.trace_id,
                correlation_id=req.correlation_id,
                request_id=req.request_id,
                session_id=req.session_id,
                ts_ms=now_ts_ms(),
                ok=llm_resp.ok,
                artifact_key=f"llm:{tool_name}:{req.request_id}",
                data=llm_resp.data,
                error=llm_resp.error,
            )

        subject = f"{NATS_TOOLS_PREFIX}{tool_name}"
        msg = await self._deps.nc.request(subject, req.model_dump_json().encode("utf-8"), timeout=120)
        tool_resp = ToolCallResponse.model_validate(json.loads(msg.data.decode("utf-8")))
        return tool_resp

    async def _ensure_session_row(self, session_id: UUID) -> None:
        assert self._deps is not None
        async with self._deps.pg.acquire() as conn:
            await conn.execute(
                """
                insert into sessions (session_id, user_id, status)
                values ($1, $2, 'RUNNING')
                on conflict (session_id) do update
                set updated_at = now()
                """,
                session_id,
                self._deps.user_id,
            )

    async def _load_cached_response(self, request_id: UUID) -> N8nRunResponse | None:
        assert self._deps is not None
        async with self._deps.pg.acquire() as conn:
            row = await conn.fetchrow(
                "select response from runtime_requests where request_id = $1 and response is not null",
                request_id,
            )
            if not row:
                return None
            value = row["response"]
            if isinstance(value, str):
                value = json.loads(value)
            return N8nRunResponse.model_validate(value)

    async def _insert_request_row(self, req: N8nRunRequest) -> None:
        assert self._deps is not None
        async with self._deps.pg.acquire() as conn:
            await conn.execute(
                """
                insert into runtime_requests (request_id, session_id, trace_id, status, response)
                values ($1, $2, $3, 'RUNNING', null)
                on conflict (request_id) do nothing
                """,
                req.request_id,
                req.session_id,
                req.trace_id,
            )

    async def _store_response(self, request_id: UUID, resp: N8nRunResponse) -> None:
        assert self._deps is not None
        async with self._deps.pg.acquire() as conn:
            await conn.execute(
                """
                insert into runtime_requests (request_id, session_id, trace_id, status, response)
                values ($1, $2, $3, $4, $5::jsonb)
                on conflict (request_id) do update
                set status = excluded.status,
                    response = excluded.response
                """,
                request_id,
                resp.session_id,
                resp.trace_id,
                resp.status,
                resp.model_dump_json(),
            )
