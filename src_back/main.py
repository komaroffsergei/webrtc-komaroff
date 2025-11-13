from aiohttp import web

from server.app import create_app
from src_back.server.handlers.handle_startup import handle_startup, handle_startup_sse

# DEFAULT_SILERO_VAD_URL = (
#     "https://github.com/snakers4/silero-vad/raw/refs/heads/master/src/"
#     "silero_vad/data/silero_vad.onnx"
# )
# WHISPER_RUBY_VAD_URL = "https://huggingface.co/ggerganov/whisper.cpp/resolve/main/ggml-silero-v5.1.2.bin"

WHISPER_MODEL_URL = "https://huggingface.co/ggerganov/whisper.cpp/resolve/main/ggml-medium.bin"


if __name__ == "__main__":
    app = create_app()
    app.on_startup.append(handle_startup)
    app.handle_startup_sse = handle_startup_sse
    import os
    port = int(os.getenv("PORT", "8000"))
    web.run_app(app, host="0.0.0.0", port=port)
