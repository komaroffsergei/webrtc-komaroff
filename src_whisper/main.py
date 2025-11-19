from __future__ import annotations

import asyncio
import logging
import os
from pathlib import Path

from dotenv import load_dotenv

from service import WhisperService
current_dir = Path(__file__).parent.resolve()
env_file = current_dir / '.env'
env_local_file = current_dir / '.env.local'
load_dotenv(env_local_file if os.path.exists(env_local_file) else env_file)

STACK_SERVICE_NAME = os.getenv("STACK_SERVICE_NAME", "src_whisper_python")
NATS_URL = os.getenv("NATS_URL", "nats://127.0.0.1:4222")
NATS_FRAMES_SUBJECT = os.getenv("NATS_FRAMES_SUBJECT", "nats.frames")
NATS_LOGS_SUBJECT = os.getenv("NATS_LOGS_SUBJECT", "nats.logs")
ASR_MODELS_DIR = current_dir / Path(os.getenv("ASR_MODELS_DIR", "models/asr"))
ASR_MODEL_ID = os.getenv("ASR_MODEL_ID", "Systran/faster-whisper-small")

ASR_MODELS_DIR.mkdir(parents=True, exist_ok=True)


def configure_logging() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )


async def _run_service() -> None:
    service = WhisperService(
        service_name=STACK_SERVICE_NAME,
        nats_url=NATS_URL,
        frames_subject=NATS_FRAMES_SUBJECT,
        logs_subject=NATS_LOGS_SUBJECT,
        models_dir=ASR_MODELS_DIR,
        model_id=ASR_MODEL_ID,
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
