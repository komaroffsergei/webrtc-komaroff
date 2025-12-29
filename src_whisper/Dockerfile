FROM python:3.11-slim

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    git \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip setuptools wheel \
    && pip install --no-cache-dir -r requirements.txt

COPY . .

ENV STACK_SERVICE_NAME=src_whisper \
    USER_ID=user123 \
    NATS_URL=nats://localhost:4222 \
    NATS_EVENTS_SUBJECT=nats.events. \
    NATS_ASR_SUBJECT=nats.asr. \
    ASR_MODELS_DIR=/app/models/asr \
    ASR_MODEL_ID=Systran/faster-whisper-small

RUN mkdir -p "$ASR_MODELS_DIR"

CMD ["python", "main.py"]
