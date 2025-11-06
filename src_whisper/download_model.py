#!/usr/bin/env python3
"""
Скрипт для предварительной загрузки модели Whisper.
Используется при сборке Docker образа.
"""

import argparse
import logging
import os
import sys

from utils.model_downloader import download_model_if_needed

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)

logger = logging.getLogger("whisper.download_model")


def main():
    parser = argparse.ArgumentParser(description="Download Whisper model")
    parser.add_argument(
        "--model",
        type=str,
        default=os.getenv("WHISPER_MODEL_NAME", "medium"),
        help="Model name to download (e.g., tiny, base, small, medium, large-v3)"
    )
    parser.add_argument(
        "--cache-dir",
        type=str,
        default=os.getenv("WHISPER_MODELS_DIR", "/app/models"),
        help="Directory to store downloaded models"
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Force re-download even if model exists"
    )
    
    args = parser.parse_args()
    
    logger.info(f"Downloading model: {args.model}")
    logger.info(f"Cache directory: {args.cache_dir}")
    
    try:
        model_path = download_model_if_needed(
            model_name=args.model,
            cache_dir=args.cache_dir,
            force_download=args.force
        )
        logger.info(f"Model ready at: {model_path}")
        return 0
    except Exception as e:
        logger.error(f"Failed to download model: {e}", exc_info=True)
        return 1


if __name__ == "__main__":
    sys.exit(main())
