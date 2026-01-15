FROM python:3.11-slim AS base

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app

RUN apt-get update && apt-get install -y --no-install-recommends \
    libavformat-dev libavcodec-dev \
    libavdevice-dev libavfilter-dev libswresample-dev libswscale-dev \
    pkg-config libgomp1 \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .

RUN pip install --no-cache-dir --upgrade pip setuptools wheel
RUN pip install --no-cache-dir -r requirements.txt

COPY . /app/src_core

RUN cat <<'EOF' >/entrypoint.sh
#!/bin/sh
set -e
exec "$@"
EOF

RUN chmod +x /entrypoint.sh
RUN mkdir -p /app/models/asr /app/src_core/models/vad


ENV SERVER_ENV=production \
    PORT=8000 \
    ASR_MODELS_DIR=/app/models/asr \
    ASR_MODEL_ID=Systran/faster-whisper-small \
    VAD_MODEL_PATH=/app/src_core/models/vad/

WORKDIR /app/src_core

ENTRYPOINT ["/entrypoint.sh"]
CMD ["python", "-m", "src_core.main"]