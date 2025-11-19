import json
import logging
import os
from pathlib import Path
from aiohttp import web

from ..utils.sse import sse_log
from ..utils.nats_client import NatsClient
from ..utils.silero_downloader import ensure_silero_model
from ..utils.silero_onnx_vad import DEFAULT_SILERO_VAD_URL

logger = logging.getLogger("startup")


async def handle_startup(app: web.Application):
    # NATS
    nats_client = NatsClient(app['vars']['NATS_URL'])
    await nats_client.connect()
    app['services'] = {
        'nats_client': nats_client
    }
    async def _log_cb(msg):
        try:
            data = json.loads(msg.data.decode())
            await sse_log(
                app,
                data.get("message", ""),
                level=data.get("type", "info"),
                service=data.get("service", "whisper"),
                log_time=data.get("time"),
                name=data.get("name"),
            )
        except Exception as e:
            logger.warning("Error parsing whisper log: %s", e)

    await app['services']['nats_client'].subscribe(app['vars']['NATS_LOGS_SUBJECT'], _log_cb)

    model_path = _resolve_vad_path()
    resolved_model_path = str(model_path)
    app['vars']['VAD_MODEL_PATH'] = resolved_model_path
    os.environ["VAD_MODEL_PATH"] = resolved_model_path

    if _auto_download_enabled():
        await ensure_silero_model(
            app,
            target_path=model_path,
            url=os.getenv("VAD_MODEL_URL", DEFAULT_SILERO_VAD_URL),
            service=app['vars'].get("STACK_SERVICE_NAME", "src_back"),
        )

    logger.info("Startup complete")


def _resolve_vad_path() -> Path:
    env_path = os.getenv("VAD_MODEL_PATH")
    if env_path:
        return Path(env_path).expanduser()

    dir_candidate = os.getenv("VAD_MODELS_DIR")
    if dir_candidate:
        return Path(dir_candidate).expanduser() / "silero_vad.onnx"

    project_root = Path(__file__).resolve().parents[2]
    return project_root / "models" / "vad" / "silero_vad.onnx"


def _auto_download_enabled() -> bool:
    return os.getenv("VAD_AUTO_DOWNLOAD", "1").lower() not in {"0", "false", "no"}
