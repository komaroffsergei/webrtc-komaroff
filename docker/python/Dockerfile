FROM python:3.11-slim AS base

WORKDIR /app

RUN apt-get update && apt-get install -y \
    ffmpeg libsm6 libxext6 libgl1 libglib2.0-0 libavformat-dev libavcodec-dev  \
    libavdevice-dev libavfilter-dev  libswresample-dev libswscale-dev pkg-config \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .

RUN pip install --no-cache-dir --upgrade pip setuptools wheel
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Create directory for whisper models (mounted as a volume at runtime)
RUN mkdir -p /app/models

# Runtime env
ENV SERVER_ENV=production \
    PORT=8000 \
    WHISPER_MODELS_DIR=/app/models \
    WHISPER_MODEL_NAME=medium

CMD ["python", "main.py"]

FROM base AS whisper
