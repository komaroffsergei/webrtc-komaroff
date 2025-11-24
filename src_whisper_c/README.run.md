# Whisper C++ Service (NATS mode)

Этот README дополняет базовое описание из `README.md` и описывает эксплуатацию обновленного сервиса, который принимает фразы по NATS, логирует события в NATS и автоматически скачивает модель Whisper при запуске.

## Зависимости

Для локальной сборки потребуются:

- Ubuntu 22.04+/Debian 12+: `build-essential`, `cmake`, `pkg-config`, `curl`, `git`
- ffmpeg (опционально, но устанавливаем по умолчанию в docker-образе)
- CUDA/Vulkan/OpenCL драйверы — только если планируется GPU-режим

Проверка зависимостей:

```bash
sudo apt-get update \
 && sudo apt-get install -y build-essential cmake pkg-config curl git ffmpeg
```

## Сборка

```bash
  cd src_whisper_c
  rm -rf build
  cmake -S . -B build
  cmake --build build --config Release -j"$(nproc)"

```

Бинарь `dist/bin/whisper-server` использует окружение для настройки поведения и не требует дополнительных аргументов.

## Ключевые переменные окружения

| Переменная | Назначение | Значение по умолчанию |
|------------|-----------|-----------------------|
| `STACK_SERVICE_NAME` | Имя сервиса в логах | `src_whisper_c` |
| `NATS_URL` | URL брокера NATS (можно через запятую несколько) | `nats://127.0.0.1:4222` |
| `NATS_FRAMES_SUBJECT` | subject для входящих фраз | `nats.frames` |
| `NATS_LOGS_SUBJECT` | subject для логов | `nats.logs` |
| `ASR_MODELS_DIR` | каталог с ggml-моделями | `models/asr` |
| `ASR_MODEL_PATH` | путь к уже скачанной модели (если задан, URL не используется) | — |
| `ASR_MODEL_URL` / `ASR_MODEL_SHA1` | ссылка и sha1 модели (скачивается при старте) | small.ggml из `README.md` |
| `ASR_LANGUAGE` | язык распознавания / `auto` | `ru` |
| `ASR_THREADS` | количество потоков для ggml | `hw_concurrency` |
| `ASR_BEAM_SIZE` | размер beam-search (`1` = greedy) | `1` |
| `ASR_MAX_CONCURRENCY` | количество параллельных транскрипций | `1` |
| `ASR_MIN_PHRASE_MS` | минимальная длина входной фразы, добивает нулями | `100` |
| `ASR_USE_GPU` | Явное включение GPU (см. ниже) | `false` (включайте вручную) |
| `WHISPERCPP_FORCE_CPU`, `WHISPERCPP_DISABLE_GPU`, `WHISPER_NO_GPU`, `GGML_NO_GPU` | Любой из этих флагов переводит сервис в CPU режим | — |
| `GGML_USE_GPU`, `GGML_CUDA`, `GGML_CUDA_FORCE_DMMV` | Принудительное включение GPU, если собранная библиотека поддерживает CUDA/Vulkan | — |

## Запуск локально

1. Настройте `.env.local` (при необходимости) или экспортируйте переменные:
   ```bash
   export NATS_URL="nats://127.0.0.1:4222"
   export ASR_MODELS_DIR="$PWD/models/asr"
   export ASR_MODEL_URL="https://huggingface.co/ggerganov/whisper.cpp/resolve/main/ggml-small.bin"
   export ASR_MODEL_SHA1="55356645c2b361a969dfd0ef2c5a50d530afd8d5"
   ```
2. Запустите NATS (`docker run nats:2.11.6-scratch` или `docker compose up audio_nats`).
3. Запустите сервис:
   ```bash
   ./dist/bin/whisper-server
   ```
4. Проверяйте логи через `nats sub nats.logs` или в SSE на backend-е.

## Docker

- Dockerfile: `docker/cpp/Dockerfile`
- Локальный запуск: `cd docker && docker compose up webrtc-server-whisper-cpp`
- Билд одиночного образа:
  ```bash
  docker build -f docker/cpp/Dockerfile -t whisper-cpp ./src_whisper_c
  docker run --rm \
    -e NATS_URL=nats://host.docker.internal:4222 \
    -v $(pwd)/models:/app/models/asr \
    whisper-cpp
  ```
- В прод-стеки (`stack/webrtc.drs`) добавлен сервис `:whisper_cpp` с отдельным volume `ASR_MODELS_DIR_CPP`, поэтому конфликта с python/ruby контейнерами нет.

## GPU / CPU режимы

### CPU

- Значения по умолчанию в Docker (`WHISPERCPP_FORCE_CPU=1`, `GGML_USE_GPU=0`, как в ruby-сервисе) делают бинарь полностью CPU-шным.
- Для явного перевода в CPU задайте любой из флагов `WHISPERCPP_FORCE_CPU=1`, `WHISPER_NO_GPU=1`, `GGML_NO_GPU=1`.

### GPU

- Необходимо собрать `ggml`/`whisper.cpp` с поддержкой CUDA/Vulkan (используйте официальные инструкции `whisper.cpp` при подготовке образа).
- Включите GPU, передав `ASR_USE_GPU=1 GGML_USE_GPU=1` (и при необходимости `GGML_CUDA=1 GGML_CUDA_FORCE_DMMV=1`).
- Для multi-GPU дополнительно можно указать `WHISPER_CUDA_DEVICE=0` (проксируется в ggml).
- Наблюдайте загрузку в `nvidia-smi`.

## Рекомендуемые профили

| Профиль | Модель | Потоки / параллелизм | Beam | Примечания |
|---------|--------|----------------------|------|-----------|
| **Макс. качество (дольше)** | `ggml-large-v3` | `ASR_THREADS=12`, `ASR_MAX_CONCURRENCY=1`, GPU желательно | `5` | Лучше включить GPU, `ASR_MIN_PHRASE_MS=200` для устойчивости |
| **Сбалансированно** | `ggml-small` | `ASR_THREADS=8`, `ASR_MAX_CONCURRENCY=2` | `3` | Хороший компромисс для CPU серверов |
| **Макс. скорость** | `ggml-base` | `ASR_THREADS=4`, `ASR_MAX_CONCURRENCY=4` | `1` | Самый быстрый отклик, меньше точность |

При повышении `ASR_MAX_CONCURRENCY` убедитесь, что хватает CPU/GPU ресурсов. Логи в `nats.logs` содержат время обработки (`transcribe_time`) — контролируйте SLA.

## Проверка

После запуска:

1. Убедитесь, что в NATS появилась запись `"Model loaded"` (`name=model_status`).
2. Отправьте тестовую фразу через `src_back` или `nats req nats.frames ...` (используйте формат `4 байта длины + json + PCM int16`).
3. Ответ с текстом и `transcribe_time` должен прийти по reply-сабджекту, ошибки пишутся с `error` и `details`.
