from __future__ import annotations

import os
from pathlib import Path
from urllib.parse import urlparse

import aiohttp
from aiohttp.web_app import Application

from src_core.settings import STACK_SERVICE_NAME, VAD_MODEL_PATH
from .event_bus import event_log

CHUNK_SIZE = 1 << 16  # 64 KB


async def ensure_silero_model(app: Application, *, url: str,
                              service: str = STACK_SERVICE_NAME) -> str:
    filename = os.path.basename(urlparse(url).path)
    full_path = f"{VAD_MODEL_PATH}/{filename}"
    resolved = Path(full_path).expanduser().resolve()
    if os.path.exists(full_path):
        await _log_status("exists", app)
        await _log_percent("100", app)
        return str(full_path)

    resolved.parent.mkdir(parents=True, exist_ok=True)
    await _log_status("downloading", app)
    await _log_percent("0", app)

    await _download_file(app, url, resolved)

    await _log_status("exists", app)
    await _log_percent("100", app)
    return str(resolved)


async def _download_file(app: Application, url: str, target: Path) -> None:
    tmp = target.with_suffix(target.suffix + ".tmp")

    async with aiohttp.ClientSession() as session:
        async with session.get(url) as response:
            response.raise_for_status()
            total = int(response.headers.get("Content-Length") or 0)
            downloaded = 0
            last_percent = 0

            with open(tmp, "wb") as dst:
                async for chunk in response.content.iter_chunked(CHUNK_SIZE):
                    dst.write(chunk)
                    downloaded += len(chunk)

                    if total:
                        percent = min(100, int(downloaded * 100 / total))
                        while last_percent < percent:
                            last_percent += 1
                            await event_log(str(last_percent), name="model_downloading_status", service=STACK_SERVICE_NAME , app=app)

    if not total:
        await event_log("100", name="model_downloading_percent", service=STACK_SERVICE_NAME , app=app)

    tmp.replace(target)


async def _log_status(value: str, app) -> None:
    await event_log(value, name="model_downloading_status", service=STACK_SERVICE_NAME , app=app)


async def _log_percent(value: str, app) -> None:
    await event_log(value, name="model_downloading_percent", service=STACK_SERVICE_NAME , app=app)
