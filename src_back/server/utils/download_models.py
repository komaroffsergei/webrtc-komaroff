import hashlib
import os
import threading
import urllib
from pathlib import Path

import requests
from aiohttp import web
import logging
from ..utils.sse import sse_log

logger = logging.getLogger("download_models")


def is_model_exists(app: web.Application) -> bool:
    os.makedirs(app['data']['WHISPER_MODEL_DIR'], exist_ok=True)

    filename = os.path.basename(urllib.parse.urlparse(app['data']['WHISPER_MODEL_URL']).path)
    target_path = os.path.join(app['data']['WHISPER_MODEL_DIR'], filename)

    if os.path.exists(target_path):
        return True
    return False


def sha256_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()


def download_model_async(model_url: str, models_dir: str, sha256: str, on_status):
    def worker():
        try:
            os.makedirs(models_dir, exist_ok=True)

            filename = os.path.basename(urllib.parse.urlparse(model_url).path)
            target_path = os.path.join(models_dir, filename)

            # уже есть
            if os.path.exists(target_path):
                if sha256 == sha256_file(target_path):
                    on_status({"type": "model_downloading_status", "value": "exists"})
                    return
                else:
                    on_status({"type": "model_downloading_status", "value": "redownloading"})
                    os.remove(target_path)
            else:
                on_status({"type": "model_downloading_status", "value": "downloading"})

            resp = requests.get(model_url, stream=True)
            resp.raise_for_status()

            total_size = int(resp.headers.get("Content-Length", 0))
            downloaded = 0
            next_percent = 1

            with open(target_path, "wb") as f:
                for chunk in resp.iter_content(chunk_size=8192):
                    if not chunk:
                        continue

                    f.write(chunk)
                    downloaded += len(chunk)

                    if total_size > 0:
                        percent = int(downloaded * 100 / total_size)

                        if percent >= next_percent:
                            on_status({"type": "model_downloading_percent", "value": percent})
                            next_percent = percent + 1
                            if next_percent > 100:
                                next_percent = 100

            on_status({"type": "model_downloading_status", "value": "downloaded"})

        except Exception as e:
            logging.error(e)
            on_status({"type": "model_downloading_status", "value": "error"})

    threading.Thread(target=worker, daemon=True).start()
