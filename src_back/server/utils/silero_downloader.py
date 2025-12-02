from __future__ import annotations

from pathlib import Path

import aiohttp

from shared.sse import sse_log, SSEContext
from ..utils.silero_onnx_vad import DEFAULT_SILERO_VAD_URL

CHUNK_SIZE = 1 << 16  # 64 KB


async def ensure_silero_model(ctx: SSEContext, *, target_path: str | Path, url: str = DEFAULT_SILERO_VAD_URL,
                              service: str = "src_back") -> str:
    path = Path(target_path).expanduser().resolve()
    if path.exists():
        await _log_status(ctx, service, "exists")
        await _log_percent(ctx, service, "100")
        return str(path)

    path.parent.mkdir(parents=True, exist_ok=True)
    await _log_status(ctx, service, "downloading")
    await _log_percent(ctx, service, "0")

    await _download_file(ctx, service, url, path)

    await _log_status(ctx, service, "exists")
    await _log_percent(ctx, service, "100")
    return str(path)


async def _download_file(ctx: SSEContext, service: str, url: str, target: Path) -> None:
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


async def _log_status(ctx: SSEContext, service: str, status: str) -> None:
    await sse_log(ctx, status, service=service, name="model_downloading_status")


async def _log_percent(ctx: SSEContext, service: str, value: str) -> None:
    await sse_log(ctx, value, service=service, name="model_downloading_percent")
