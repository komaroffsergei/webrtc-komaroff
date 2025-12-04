from __future__ import annotations

import os
from pathlib import Path
from urllib.parse import urlparse

import aiohttp
from aiohttp.web_app import Application

from src_core.main import VAD_MODEL_URL, VAD_MODEL_PATH, STACK_SERVICE_NAME
from src_core.server.handlers.handle_sse import sse_log

CHUNK_SIZE = 1 << 16  # 64 KB


async def ensure_silero_model(app: Application, *, url: str,
                              service: str = STACK_SERVICE_NAME) -> str:
    filename = os.path.basename(urlparse(VAD_MODEL_URL).path)
    full_path = f"{VAD_MODEL_PATH}/{filename}"
    resolved = Path(full_path).expanduser().resolve()
    if os.path.exists(full_path):
        await _log_status(app, service, "exists")
        await _log_percent(app, service, "100")
        return str(full_path)

    resolved.parent.mkdir(parents=True, exist_ok=True)
    await _log_status(app, service, "downloading")
    await _log_percent(app, service, "0")

    await _download_file(app, service, url, resolved)

    await _log_status(app, service, "exists")
    await _log_percent(app, service, "100")
    return str(resolved)


async def _download_file(ctx: Application, service: str, url: str, target: Path) -> None:
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
                            await _log_percent(ctx, service, str(last_percent))

    if not total:
        await _log_percent(ctx, service, "100")

    tmp.replace(target)


async def _log_status(app: Application, service: str, status: str) -> None:
    await sse_log(app, status, service=service, name="model_downloading_status")


async def _log_percent(app: Application, service: str, value: str) -> None:
    await sse_log(app, value, service=service, name="model_downloading_percent")
