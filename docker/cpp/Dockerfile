FROM ubuntu:24.04 AS build

ENV DEBIAN_FRONTEND=noninteractive

RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential \
        ca-certificates \
        cmake \
        curl \
        git \
        pkg-config \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /src

COPY . .

ARG PROJECT_SUBDIR=src_whisper_c
RUN set -eux; \
    BUILD_ROOT=/src; \
    if [ -d "/src/${PROJECT_SUBDIR}" ]; then BUILD_ROOT="/src/${PROJECT_SUBDIR}"; fi; \
    cd "${BUILD_ROOT}"; \
    rm -rf build; \
    cmake -S . -B build -DCMAKE_BUILD_TYPE=Release; \
    cmake --build build --config Release; \
    cmake --install build --prefix /opt/whisper

FROM ubuntu:24.04 AS runtime

ENV DEBIAN_FRONTEND=noninteractive

RUN apt-get update && apt-get install -y --no-install-recommends \
        ca-certificates \
        curl \
        ffmpeg \
        libgomp1 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY --from=build /opt/whisper /opt/whisper
COPY --from=build /src /app

RUN ln -s /opt/whisper/bin/whisper-server /usr/local/bin/whisper-cpp \
    && mkdir -p /app/models/asr

ENV LD_LIBRARY_PATH=/opt/whisper/lib:$LD_LIBRARY_PATH \
    STACK_SERVICE_NAME=src_whisper_c \
    NATS_URL=nats://audio_nats:4222 \
    NATS_FRAMES_SUBJECT=nats.frames \
    NATS_LOGS_SUBJECT=nats.logs \
    ASR_MODELS_DIR=/app/models/asr \
    ASR_MODEL_URL=https://huggingface.co/ggerganov/whisper.cpp/resolve/main/ggml-small.bin \
    ASR_MODEL_SHA1=55356645c2b361a969dfd0ef2c5a50d530afd8d5 \
    ASR_LANGUAGE=ru \
    ASR_THREADS=4 \
    ASR_MAX_CONCURRENCY=1 \
    WHISPERCPP_FORCE_CPU=1 \
    WHISPER_NO_GPU=1 \
    GGML_USE_GPU=0

ENTRYPOINT ["/usr/local/bin/whisper-cpp"]
