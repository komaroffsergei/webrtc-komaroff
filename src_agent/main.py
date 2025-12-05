import asyncio

from src_agent.settings import (
    STACK_SERVICE_NAME,
    NATS_URL,
    AGENT_FRAMES_SUBJECT,
    AGENT_LOGS_SUBJECT,
)
from src_agent.service import AgentService


async def main():
    AgentService(
        service_name=STACK_SERVICE_NAME,
        nats_url=NATS_URL,
        frames_subject=AGENT_FRAMES_SUBJECT,
        logs_subject=AGENT_LOGS_SUBJECT,
    )
    while True:
        await asyncio.sleep(3600)


if __name__ == "__main__":
    asyncio.run(main())
