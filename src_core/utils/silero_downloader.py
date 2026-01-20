from __future__ import annotations

import os
from pathlib import Path
from urllib.parse import urlparse

import aiohttp
from aiohttp.web_app import Application

from src_core.settings import STACK_SERVICE_NAME, VAD_MODEL_PATH
from .event_bus import event_log

CHUNK_SIZE = 1 << 16  # 64 KB


async def ensure_silero_model(app: Application, *, url: str) -> str:
    filename = os.path.basename(urlparse(url).path)
    full_path = f"{VAD_MODEL_PATH}/{filename}"
    resolved = Path(full_path).expanduser().resolve()
    if os.path.exists(full_path):
        await _publish_status(app, status="ready")
        return str(full_path)

    resolved.parent.mkdir(parents=True, exist_ok=True)
    await _publish_status(app, status="downloading", percent=0)

    await _download_file(app, url, resolved)

    await _publish_status(app, status="ready")
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
                            await _publish_status(app, status="downloading", percent=last_percent)

    tmp.replace(target)


async def _publish_status(app: Application, *, status: str, percent: int | None = None) -> None:
    data: dict[str, object] = {"status": status}
    if percent is not None:
        data["percent"] = percent
    await event_log(
        "command",
        "status_vad",
        data,
        app=app,
        service=STACK_SERVICE_NAME,
    )
