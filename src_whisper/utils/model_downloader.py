"""
Model Downloader - автоматическая загрузка моделей Whisper
"""

import logging
import os
from pathlib import Path
from typing import Optional

from huggingface_hub import snapshot_download

logger = logging.getLogger("whisper.model_downloader")


def download_model_if_needed(
    model_name: str,
    cache_dir: str,
    force_download: bool = False
) -> str:
    """
    Скачать модель Whisper если она отсутствует.
    
    Args:
        model_name: название модели (например, "medium" или "large-v3")
        cache_dir: директория для кэша моделей
        force_download: принудительно перезагрузить модель
    
    Returns:
        str: путь к загруженной модели
    """
    cache_path = Path(cache_dir)
    cache_path.mkdir(parents=True, exist_ok=True)
    
    # Конвертируем короткое имя в полное (если нужно)
    repo_id = _get_repo_id(model_name)
    model_dir = cache_path / model_name
    
    # Проверяем наличие модели
    if model_dir.exists() and not force_download:
        config_json = model_dir / "config.json"
        if config_json.exists():
            logger.info(f"Model '{model_name}' already exists at {model_dir}")
            return str(model_dir)
    
    logger.info(f"Downloading model '{model_name}' from {repo_id}...")
    
    try:
        downloaded_path = snapshot_download(
            repo_id=repo_id,
            cache_dir=str(cache_path),
            local_dir=str(model_dir),
            local_dir_use_symlinks=False,
            resume_download=True
        )
        logger.info(f"Model downloaded successfully to {downloaded_path}")
        return str(model_dir)
    
    except Exception as e:
        logger.error(f"Failed to download model: {e}")
        raise


def _get_repo_id(model_name: str) -> str:
    """
    Получить HuggingFace repo ID по имени модели.
    
    Args:
        model_name: короткое имя модели
    
    Returns:
        str: полный repo ID
    """
    # Если уже указан полный путь
    if "/" in model_name:
        return model_name
    
    # Маппинг коротких имен на repo ID
    model_mapping = {
        "tiny": "Systran/faster-whisper-tiny",
        "tiny.en": "Systran/faster-whisper-tiny.en",
        "base": "Systran/faster-whisper-base",
        "base.en": "Systran/faster-whisper-base.en",
        "small": "Systran/faster-whisper-small",
        "small.en": "Systran/faster-whisper-small.en",
        "medium": "Systran/faster-whisper-medium",
        "medium.en": "Systran/faster-whisper-medium.en",
        "large-v1": "Systran/faster-whisper-large-v1",
        "large-v2": "Systran/faster-whisper-large-v2",
        "large-v3": "Systran/faster-whisper-large-v3",
        "large": "Systran/faster-whisper-large-v3",
    }
    
    repo_id = model_mapping.get(model_name)
    if repo_id is None:
        # Если не нашли в маппинге, пробуем использовать как есть
        logger.warning(f"Unknown model name '{model_name}', using as-is")
        return model_name
    
    return repo_id


def ensure_model_available(model_path: str) -> str:
    """
    Убедиться что модель доступна, скачать если нужно.
    
    Args:
        model_path: путь к модели или имя модели
    
    Returns:
        str: путь к доступной модели
    """
    path = Path(model_path)
    
    # Если путь существует и содержит config.json - возвращаем его
    if path.exists() and (path / "config.json").exists():
        return str(path)
    
    # Если это просто имя модели - пытаемся загрузить
    if "/" not in model_path:
        # Определяем cache_dir: ./models для локальной разработки, /app/models для Docker
        default_cache_dir = "./models" if not os.path.exists("/app") else "/app/models"
        cache_dir = os.getenv("WHISPER_MODELS_DIR", default_cache_dir)
        return download_model_if_needed(model_path, cache_dir)
    
    # Возвращаем путь как есть (может быть кастомная модель)
    return str(path)
