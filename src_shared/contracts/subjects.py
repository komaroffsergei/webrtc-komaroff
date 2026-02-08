from __future__ import annotations


class Subjects:
    """
    Canonical NATS subjects used by this repo.

    User-scoped subjects are prefixes; append `user_id` (no extra dot).
    """

    AGENT_PREFIX = "nats.agent."
    EVENTS_PREFIX = "nats.events."
    LLM_PREFIX = "nats.llm."

    N8N_RUN = "nats.n8n.run"
    N8N_HEALTH = "nats.n8n.health"

    TOOLS_PREFIX = "nats.tools."

