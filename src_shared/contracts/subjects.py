from __future__ import annotations


class Subjects:
    """
    Canonical NATS subjects used by this repo.

    User-scoped subjects are prefixes; append `user_id` (no extra dot).
    """

    AGENT_PREFIX = "nats.agent."
    AGENT_HISTORY_PREFIX = "nats.agent.history."
    EVENTS_PREFIX = "nats.events."
    LLM_PREFIX = "nats.llm."

    WORKFLOW_RUN = "nats.workflow.run.python"
    WORKFLOW_HEALTH = "nats.workflow.health.python"

    TOOLS_PREFIX = "nats.tools."
