from __future__ import annotations

import asyncio
from asyncio import AbstractEventLoop, run_coroutine_threadsafe
from pathlib import Path
from typing import Optional

from faster_whisper import utils as fw_utils
from huggingface_hub import snapshot_download

from nats_logger import NatsLogger


async def ensure_model_path(model_id: str, models_dir, logger: Optional[NatsLogger]) -> str:
    models_dir = Path(models_dir).resolve()
    models_dir.mkdir(parents=True, exist_ok=True)

    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(
        None,
        lambda: _download_sync(model_id, models_dir, logger, loop),
    )


def _download_sync(model_id: str, models_dir: Path, logger: Optional[NatsLogger], loop: AbstractEventLoop) -> str:
    repo_id = _resolve_repo_id(model_id)
    candidate = Path(model_id)
    if candidate.exists():
        return str(candidate.resolve())

    target_dir = models_dir / _slug(repo_id)
    model_bin = target_dir / "model.bin"

    if model_bin.exists():
        _log_status(loop, logger, "exists", name="model_downloading_status")
        _log_percent(loop, logger, 100)
        return str(target_dir)

    target_dir.mkdir(parents=True, exist_ok=True)
    _log_status(loop, logger, "downloading", name="model_downloading_status")
    _log_percent(loop, logger, 0)

    progress_class = _build_progress_class(loop, logger)
    snapshot_download(
        repo_id,
        local_dir=str(target_dir),
        local_dir_use_symlinks=False,
        allow_patterns=[
            "config.json",
            "preprocessor_config.json",
            "model.bin",
            "tokenizer.json",
            "vocabulary.*",
        ],
        tqdm_class=progress_class,
    )

    _log_percent(loop, logger, 100)
    _log_status(loop, logger, "exists", name="model_downloading_status")
    return str(target_dir)


def _build_progress_class(loop: AbstractEventLoop, logger: Optional[NatsLogger]):
    class Progress(fw_utils.disabled_tqdm):
        def __init__(self, *args, **kwargs):
            self._last = -1
            super().__init__(*args, **kwargs)

        def update(self, n=1):
            super().update(n)
            if not self.total:
                return
            percent = int((self.n / self.total) * 100)
            if percent != self._last:
                self._last = percent
                _log_percent(loop, logger, percent)

    return Progress


def _log_status(loop: AbstractEventLoop, logger: Optional[NatsLogger], message: str, *, name: str) -> None:
    if not logger:
        return
    run_coroutine_threadsafe(logger.info(message, name=name), loop)


def _log_percent(loop: AbstractEventLoop, logger: Optional[NatsLogger], percent: int) -> None:
    if not logger:
        return
    run_coroutine_threadsafe(logger.info(str(percent), name="model_downloading_percent"), loop)


def _slug(value: str) -> str:
    return "".join(ch if ch.isalnum() else "_" for ch in value)


def _resolve_repo_id(model_id: str) -> str:
    if "/" in model_id or model_id.endswith(".en"):
        return model_id
    return fw_utils._MODELS.get(model_id, model_id)
