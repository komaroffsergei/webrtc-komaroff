from __future__ import annotations

import asyncio
import logging
import os
from pathlib import Path

from dotenv import load_dotenv

from src_whisper.service import WhisperService
from src_whisper.settings import (
    ASR_MODEL_ID,
    BUFFER_CHECK_INTERVAL_S,
    MAX_SPEECH_DURATION_S,
    MIN_SILENCE_DURATION_MS,
    MIN_SPEECH_DURATION_MS,
    NATS_ASR_SUBJECT,
    NATS_EVENTS_SUBJECT,
    NATS_URL,
    SPEECH_PAD_MS,
    STACK_SERVICE_NAME,
    USER_ID,
    VAD_MODEL_URL,
    VAD_MODELS,
    VAD_SAMPLE_RATE,
    VAD_THRESHOLD,
    WHISPER_BEAM_SIZE,
    WHISPER_LANGUAGE,
    WHISPER_MAX_CONCURRENCY,
)

current_dir = Path(__file__).parent.resolve()
env_file = current_dir / '.env'
env_local_file = current_dir / '.env.local'
load_dotenv(env_local_file if os.path.exists(env_local_file) else env_file)

ASR_MODELS = current_dir / Path(os.getenv("ASR_MODELS", "models/asr"))
ASR_MODELS.mkdir(parents=True, exist_ok=True)

VAD_MODELS_DIR = Path(VAD_MODELS)
if not VAD_MODELS_DIR.is_absolute():
    VAD_MODELS_DIR = current_dir / VAD_MODELS_DIR
VAD_MODELS_DIR.mkdir(parents=True, exist_ok=True)


def configure_logging() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )


async def _run_service() -> None:
    if not USER_ID:
        raise ValueError("USER_ID is required")
    prefix = (NATS_ASR_SUBJECT or "").strip()
    if not prefix:
        raise ValueError("NATS_ASR_SUBJECT is required")
    if "*" in prefix or ">" in prefix:
        raise ValueError("NATS_ASR_SUBJECT must be a plain prefix (wildcards are not supported)")
    if not prefix.endswith("."):
        prefix += "."

    service = WhisperService(
        service_name=STACK_SERVICE_NAME,
        nats_url=NATS_URL,
        asr_subject=f"{prefix}{USER_ID}",
        logs_subject=f"{NATS_EVENTS_SUBJECT}{USER_ID}",
        models_dir=ASR_MODELS,
        model_id=ASR_MODEL_ID,
        language=WHISPER_LANGUAGE,
        beam_size=WHISPER_BEAM_SIZE,
        max_concurrency=WHISPER_MAX_CONCURRENCY,
        vad_models_dir=VAD_MODELS_DIR,
        vad_model_url=VAD_MODEL_URL,
        vad_sample_rate=VAD_SAMPLE_RATE,
        min_speech_duration_ms=MIN_SPEECH_DURATION_MS,
        min_silence_duration_ms=MIN_SILENCE_DURATION_MS,
        max_speech_duration_s=MAX_SPEECH_DURATION_S,
        speech_pad_ms=SPEECH_PAD_MS,
        vad_threshold=VAD_THRESHOLD,
        buffer_check_interval_s=BUFFER_CHECK_INTERVAL_S,
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
