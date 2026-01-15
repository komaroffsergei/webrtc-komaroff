from __future__ import annotations

from fnmatch import fnmatch
from pathlib import Path
from typing import Iterable

from huggingface_hub import HfApi, hf_hub_download

GGUF_PATTERNS = ("*.gguf",)


from pathlib import Path
from huggingface_hub import hf_hub_download


def ensure_model_path(
    model_id: str,
    models_dir: str,
    model_file: str | None = None,
) -> str:
    # 1. Если передали путь к файлу — просто вернуть
    p = Path(model_id)
    if p.exists():
        return str(p.resolve())

    # 2. Всегда работаем относительно текущей директории
    models_dir = Path(models_dir)
    target_dir = models_dir / _slug(model_id)
    target_dir.mkdir(parents=True, exist_ok=True)

    # 3. Выбираем файл
    filename = model_file or _select_model_file(model_id)
    cached = target_dir / filename
    if cached.exists():
        return str(cached.resolve())

    # 4. Качаем
    downloaded = hf_hub_download(
        repo_id=model_id,
        filename=filename,
        local_dir=str(target_dir),
        local_dir_use_symlinks=False,
    )

    return str(Path(downloaded).resolve())



def _select_model_file(repo_id: str) -> str:
    candidates = list(_list_repo_files(repo_id))
    if not candidates:
        raise ValueError(f"No GGUF files found for repo {repo_id}")

    candidates.sort(key=lambda item: (item.size or 0, item.rfilename))
    return candidates[0].rfilename


def _list_repo_files(repo_id: str) -> Iterable:
    api = HfApi()
    info = api.repo_info(repo_id, files_metadata=True)
    if not info.siblings:
        return []

    for sibling in info.siblings:
        path = sibling.rfilename
        if sibling.size is None:
            continue
        if any(fnmatch(path, pattern) for pattern in GGUF_PATTERNS):
            yield sibling


def _slug(value: str) -> str:
    return "".join(ch if ch.isalnum() else "_" for ch in value)
