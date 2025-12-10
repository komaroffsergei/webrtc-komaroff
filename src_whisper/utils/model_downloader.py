from __future__ import annotations

import asyncio
from asyncio import AbstractEventLoop, run_coroutine_threadsafe
from fnmatch import fnmatch
from pathlib import Path
from typing import Iterable, Optional

import threading
import time

from faster_whisper import utils as fw_utils
from huggingface_hub import HfApi, hf_hub_download

from src_whisper.utils.nats_logger import NatsLogger

ALLOW_PATTERNS = (
    "config.json",
    "preprocessor_config.json",
    "model.bin",
    "tokenizer.json",
    "tokenizer_config.json",
    "vocabulary.*",
)


async def ensure_model_path(model_id: str, models_dir, logger: Optional[NatsLogger]) -> str:
    models_dir = Path(models_dir).resolve()
    models_dir.mkdir(parents=True, exist_ok=True)

    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(
        None,
        lambda: _download_sync(model_id, models_dir, logger, loop),
    )


def _download_sync(model_id: str, models_dir: Path,
                   logger: Optional[NatsLogger], loop: AbstractEventLoop) -> str:

    candidate = Path(model_id)
    if candidate.exists():
        return str(candidate.resolve())

    repo_id = _resolve_repo_id(model_id)
    target_dir = models_dir / _slug(repo_id)
    model_bin = target_dir / "model.bin"

    if model_bin.exists():
        _log_status(loop, logger, "exists")
        _log_percent(loop, logger, 100)
        return str(target_dir)

    target_dir.mkdir(parents=True, exist_ok=True)
    _log_status(loop, logger, "downloading")
    _log_percent(loop, logger, 0)

    files = list(_list_repo_files(repo_id))
    stop_flag = False

    def ticking():
        while not stop_flag:
            _log_status(loop, logger, "downloading")
            time.sleep(1)

    tick_thread = threading.Thread(target=ticking, daemon=True)
    tick_thread.start()

    for entry in files:
        rel = entry.rfilename
        local_path = target_dir / rel
        local_path.parent.mkdir(parents=True, exist_ok=True)

        # Качаем файл целиком
        hf_hub_download(
            repo_id,
            rel,
            local_dir=str(target_dir),
            local_dir_use_symlinks=False,
        )


    stop_flag = True
    tick_thread.join(timeout=0.2)
    _log_percent(loop, logger, 100)
    _log_status(loop, logger, "exists")

    return str(target_dir)


def _list_repo_files(repo_id: str) -> Iterable:
    api = HfApi()
    info = api.repo_info(repo_id, files_metadata=True)
    if not info.siblings:
        return []

    for sibling in info.siblings:
        path = sibling.rfilename
        if sibling.size is None:
            continue
        if any(fnmatch(path, pattern) for pattern in ALLOW_PATTERNS):
            yield sibling


def _log_status(loop: AbstractEventLoop, logger: Optional[NatsLogger], message: str) -> None:
    if not logger:
        return
    run_coroutine_threadsafe(logger.info(message, name="model_downloading_status"), loop)


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
