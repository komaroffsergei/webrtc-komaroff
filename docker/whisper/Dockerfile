FROM python:3.11-slim

# Legacy local Dockerfile. Current production `voice-chat/stt_whisper_to_nats` image is built
# from the separate `py_faster_whisper` repo, not from this file.

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app

RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    libgomp1 \
    git \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip setuptools wheel \
    && pip install --no-cache-dir -r requirements.txt

COPY . /app/src_whisper

WORKDIR /app/src_whisper

RUN mkdir -p "/models/asr" "/models/vad"

CMD ["python", "-m", "src_whisper.main"]

