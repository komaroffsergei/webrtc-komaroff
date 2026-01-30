from __future__ import annotations

import asyncio
import logging
import os
from pathlib import Path

from dotenv import load_dotenv

from src_whisper.service import WhisperService

current_dir = Path(__file__).parent.resolve()
env_file = current_dir / '.env'
env_local_file = current_dir / '.env.local'
load_dotenv(env_local_file if os.path.exists(env_local_file) else env_file)

from src_whisper import settings as s  # noqa: E402  # reason: .env must be loaded first


ASR_MODELS_DIR = Path(s.ASR_MODELS)
if not ASR_MODELS_DIR.is_absolute():
    ASR_MODELS_DIR = current_dir / ASR_MODELS_DIR
ASR_MODELS_DIR.mkdir(parents=True, exist_ok=True)

VAD_MODELS_DIR = Path(s.VAD_MODELS)
if not VAD_MODELS_DIR.is_absolute():
    VAD_MODELS_DIR = current_dir / VAD_MODELS_DIR
VAD_MODELS_DIR.mkdir(parents=True, exist_ok=True)


def configure_logging() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )


async def _run_service() -> None:
    if not s.USER_ID:
        raise ValueError("USER_ID is required")
    prefix = (s.NATS_ASR_SUBJECT or "").strip()
    if not prefix:
        raise ValueError("NATS_ASR_SUBJECT is required")
    if "*" in prefix or ">" in prefix:
        raise ValueError("NATS_ASR_SUBJECT must be a plain prefix (wildcards are not supported)")
    if not prefix.endswith("."):
        prefix += "."

    service = WhisperService(
        service_name=s.STACK_SERVICE_NAME,
        nats_url=s.NATS_URL,
        asr_subject=f"{prefix}{s.USER_ID}",
        logs_subject=f"{s.NATS_EVENTS_SUBJECT}{s.USER_ID}",
        models_dir=ASR_MODELS_DIR,
        model_id=s.ASR_MODEL_ID,
        language=s.WHISPER_LANGUAGE,
        beam_size=s.WHISPER_BEAM_SIZE,
        max_concurrency=s.WHISPER_MAX_CONCURRENCY,
        vad_models_dir=VAD_MODELS_DIR,
        vad_model_url=s.VAD_MODEL_URL,
        vad_sample_rate=s.VAD_SAMPLE_RATE,
        min_speech_duration_ms=s.MIN_SPEECH_DURATION_MS,
        min_silence_duration_ms=s.MIN_SILENCE_DURATION_MS,
        max_speech_duration_s=s.MAX_SPEECH_DURATION_S,
        speech_pad_ms=s.SPEECH_PAD_MS,
        vad_threshold=s.VAD_THRESHOLD,
        buffer_check_interval_s=s.BUFFER_CHECK_INTERVAL_S,
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
