import hashlib
import logging
import os
import threading
import urllib

import requests

logger = logging.getLogger(__name__)


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
                    on_status({
                        "type": "info",
                        "name": "model_downloading_status",
                        "message": "exists"}
                    )
                    return
                else:
                    on_status({
                        "type": "info",
                        "name": "model_downloading_status",
                        "message": "downloading"}
                    )
                    os.remove(target_path)
            else:
                on_status({
                    "type": "info",
                    "name": "model_downloading_status",
                    "message": "downloading"}
                )

            try:
                resp = requests.get(model_url, stream=True, timeout=10)
            except requests.exceptions.RequestException as exc:
                logging.error(f"Network error: {exc}")
                on_status({
                    "type": "error",
                    "name": "model_downloading_status",
                    "message": f"network_error: {exc}"
                })
                return

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
                            on_status({
                                "type": "info",
                                "name": "model_downloading_percent",
                                "message": percent
                            })
                            next_percent = percent + 1
                            if next_percent > 100:
                                next_percent = 100

            on_status({
                "type": "info",
                "name": "model_downloading_status",
                "message": "exists"
            })

        except Exception as e:
            logging.error(e)
            on_status({
                "type": "info",
                "name": "model_downloading_status",
                "message": "error"
            })

    threading.Thread(target=worker, daemon=True).start()
