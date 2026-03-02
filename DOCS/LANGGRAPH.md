# src_langgraph

## Responsibility
`src_langgraph` runs workflow scenarios and returns `WorkflowRunResponse` for each user turn.
It routes requests to scenarios, calls LLM/tools, and maintains compact stateful dialog context in runtime state.
It does not expose HTTP endpoints.

## NATS API
Subscriptions:
- `nats.workflow.run`
- `nats.workflow.health`

Outbound req/reply calls:
- `nats.llm.<user_id>`
- `nats.tools.<tool_name>`

## Stateful context model
LangGraph runtime builds and updates compact context per session in `next_runtime.context`:
- `dialog_memory.summary`: compressed text of older turns
- `dialog_memory.recent_turns`: bounded list of latest user/assistant turns
- `artifact_memory`: compact structured artifacts from previous tool responses

On every request:
1. Reads existing memory from `req.runtime.context`.
2. If `edit.turn_id` is present, rewrites memory tail from that user turn.
3. Builds compact `dialog_context` string.
4. Passes `dialog_context` to routing and scenario LLM calls.
5. Appends current user+assistant turns, compacts memory again, returns updated context.

All scenarios are stateful because they receive this shared `dialog_context`.

### Pending exit policy (`where_my_flight`)
- First turn without required params (`flight_number` or `last_name`) returns `PARTIAL + ASK_USER_INPUT`.
- If the next user message still does not contain required params, runtime exits pending state and reroutes this same message through normal scenario selection (excluding `where_my_flight`).
- This prevents infinite `ASK_USER_INPUT` loops and lets user switch topic immediately.

### Reference resolution in `free_speech`
- Runtime resolves references like `он/этот` and `они/эти` against structured entities from `artifact_memory`.
- For plural references, assistant answers against all resolved entities.
- For singular references, runtime first tries to resolve focus from the latest assistant turn; clarification is used only if focus is ambiguous.
- `free_speech` uses both compact dialog context and model general knowledge; when confidence is low, it should state uncertainty explicitly.
- For fact-like queries runtime uses two-pass generation:
  - pass 1: regular `final_response` with full context
  - pass 2 (recovery): retried `final_response` with knowledge-priority instruction and compacted context
  - runtime picks the better response using generic quality heuristics (no domain-specific hardcoding)

## Turn IDs
- Uses `req.turn_id` as user turn identifier.
- Generates `assistant_turn_id` in runtime.
- Injects both IDs into `client_handler.payload`.

This keeps frontend edit/history and database storage aligned.

## Environment
Configured in `src_langgraph/settings.py` and `src_langgraph/env.example`.

- `NATS_URL`
- `NATS_WORKFLOW_RUN_SUBJECT`
- `NATS_WORKFLOW_HEALTH_SUBJECT`
- `NATS_LLM_SUBJECT`
- `NATS_TOOLS_PREFIX`
- `NATS_REQUEST_TIMEOUT_SECONDS`
- `MAX_CONCURRENCY`
- `MEMORY_RECENT_MESSAGES`
- `MEMORY_SUMMARY_MAX_CHARS`
- `MEMORY_CONTEXT_MAX_CHARS`
- `USER_ID`

## Run/stop
Docker:
```bash
cd docker
docker compose --profile langgraph up -d src_langgraph
docker compose --profile langgraph stop src_langgraph
```

Local:
```bash
python -m src_langgraph.main
```

## Common issues
- `missing_session_id`
  - Cause: request reaches runtime without session.
  - Fix: ensure agent always sends `session_id`.
- `no responders available` for tools/llm
  - Cause: downstream service is down or subject mismatch.
  - Fix: verify `src_llm`, `src_api_gateway`, and subject prefixes.
- Context appears lost between turns
  - Cause: runtime state not saved in agent/postgres.
  - Fix: verify `src_agent` DB connectivity and `runtime_state` table updates.

## Code pointers
- Entry: `src_langgraph/main.py`
- Service/NATS handlers: `src_langgraph/service.py`
- Graph engine: `src_langgraph/engine.py`
- Memory helpers: `src_langgraph/memory.py`
- Scenario routing: `src_langgraph/router.py`
- Scenario nodes: `src_langgraph/scenarios/*`
