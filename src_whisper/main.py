from __future__ import annotations

import asyncio
import logging
import os
from pathlib import Path

from dotenv import load_dotenv

from src_whisper.service import WhisperService
from src_whisper.settings import STACK_SERVICE_NAME, NATS_URL, NATS_ASR_SUBJECT, USER_ID, NATS_EVENTS_SUBJECT, \
    ASR_MODEL_ID

current_dir = Path(__file__).parent.resolve()
env_file = current_dir / '.env'
env_local_file = current_dir / '.env.local'
load_dotenv(env_local_file if os.path.exists(env_local_file) else env_file)

ASR_MODELS = current_dir / Path(os.getenv("ASR_MODELS", "models/asr"))
ASR_MODELS.mkdir(parents=True, exist_ok=True)


def configure_logging() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )


async def _run_service() -> None:
    service = WhisperService(
        service_name=STACK_SERVICE_NAME,
        nats_url=NATS_URL,
        asr_subject=f"{NATS_ASR_SUBJECT}{USER_ID}",
        logs_subject=f"{NATS_EVENTS_SUBJECT}{USER_ID}",
        models_dir=ASR_MODELS,
        model_id=ASR_MODEL_ID,
        compute_type="float32",
    )
    await service.run()


def main() -> None:
    configure_logging()
    try:
        asyncio.run(_run_service())
    except KeyboardInterrupt:
        pass
    except Exception as exc:
        logging.getLogger("main").exception("Service terminated with error: %s", exc)
        raise SystemExit(1) from exc


if __name__ == "__main__":
    main()
