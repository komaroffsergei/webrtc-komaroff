FROM python:3.11-slim AS base

WORKDIR /app

RUN apt-get update && apt-get install -y \
    ffmpeg libsm6 libxext6 libgl1 libglib2.0-0 libavformat-dev libavcodec-dev  \
    libavdevice-dev libavfilter-dev  libswresample-dev libswscale-dev pkg-config curl \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .

RUN pip install --no-cache-dir --upgrade pip setuptools wheel
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

ENV SILERO_VAD_BUNDLE_DIR=/opt/silero_vad_bundle \
    SILERO_VAD_DIR=/opt/silero_vad \
    SILERO_VAD_MODEL_PATH=/opt/silero_vad/silero_vad.onnx \
    SILERO_VAD_MODEL_URL=https://github.com/snakers4/silero-vad/raw/refs/heads/master/src/silero_vad/data/silero_vad.onnx

RUN mkdir -p ${SILERO_VAD_BUNDLE_DIR} ${SILERO_VAD_DIR} \
    && curl -L ${SILERO_VAD_MODEL_URL} -o ${SILERO_VAD_BUNDLE_DIR}/silero_vad.onnx

RUN cat <<'EOF' >/entrypoint.sh
#!/bin/sh
set -e

bundle_dir="${SILERO_VAD_BUNDLE_DIR:-}"
bundle_model="${bundle_dir}/silero_vad.onnx"
runtime_model="${SILERO_VAD_MODEL_PATH:-}"

if [ -z "$runtime_model" ] && [ -n "${SILERO_VAD_DIR:-}" ]; then
    runtime_model="${SILERO_VAD_DIR%/}/silero_vad.onnx"
fi

runtime_dir=$(dirname "$runtime_model")

if [ -f "$bundle_model" ] && [ ! -f "$runtime_model" ]; then
    mkdir -p "$runtime_dir"
    cp "$bundle_model" "$runtime_model"
fi

exec "$@"
EOF

RUN chmod +x /entrypoint.sh

# Создать директорию для моделей
RUN mkdir -p /app/models

# Установить переменные окружения для загрузки модели
ENV SERVER_ENV=production \
    PORT=8000 \
    MODELS_DIR=/app/models \
    WHISPER_MODEL_NAME=medium

ENTRYPOINT ["/entrypoint.sh"]
CMD ["python", "main.py"]

FROM base AS whisper

# Скачать модель Whisper при сборке образа
RUN python3 download_model.py --model ${WHISPER_MODEL_NAME} --cache-dir ${MODELS_DIR}
