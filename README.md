# WebRTC Whisper (Komaroff)

Этот репозиторий содержит Python- и Ruby-версии сервиса транскрипции. Ниже описано, как переключать Ruby-вариант (`src_whisper_ruby/src`) между CPU и GPU, а также как собрать текущие образы через Docker.

## Переключение WhisperCPP на CPU

1. **Выставьте переменные окружения перед запуском сервиса.**
   ```bash
   export WHISPERCPP_FORCE_CPU=1        # внутренний флаг whispercpp
   export GGML_NO_GPU=1                 # запасной флаг для ggml/whisper.cpp
   export GGML_CUDA=0 GGML_USE_CUDA=0   # отключаем следы от прошлых запусков
   ```
2. **Запускайте сервис из каталога `src_whisper_ruby/src`.**
   ```bash
   cd src_whisper_ruby/src
   bundle exec rackup config.ru  # или любой другой entrypoint
   ```
3. **Проверьте логи.** После старта должны появиться строки вида:
   ```
   whisper_init_with_params_no_state: use gpu    = 0
   whisper_init_with_params_no_state: flash attn = 0
   ```
   Если видите `use gpu = 1`, значит в окружении остались GPU-флаги — вернитесь к шагу 1.

## Переключение WhisperCPP на GPU

> **Важно:** по умолчанию в репозитории собран CPU-билд (`GGML_CUDA=OFF`). Для реального использования GPU сначала нужно пересобрать нативное расширение с поддержкой CUDA/другого бекэнда.

1. **Пересоберите `whispercpp` с нужным бекэндом.**
   ```bash
   cd src_whisper_ruby/src/vendor/bundle/ruby/3.4.0/gems/whispercpp-1.3.4/ext
   bundle exec ruby extconf.rb --enable-ggml-cuda          # или --enable-ggml-vulkan / --enable-ggml-opencl
   make -j"$(nproc)"
   cp whisper.so ../lib/whisper.so
   cp whisper.so ../../extensions/x86_64-linux/3.4.0/whispercpp-1.3.4/whisper.so
   ```
   Убедитесь, что на хосте стоят CUDA Toolkit, драйверы и т.д.
2. **Включите GPU во время запуска сервиса.**
   ```bash
   export WHISPERCPP_FORCE_CPU=0
   export GGML_NO_GPU=0
   export WHISPERCPP_USE_GPU=1         # новый флаг whispercpp
   export GGML_USE_CUDA=1 GGML_CUDA=1  # требуются бэкенду ggml
   cd src_whisper_ruby/src
   bundle exec rackup config.ru
   ```
3. **Проверьте логи.** Должен появиться блок:
   ```
   whisper_init_with_params_no_state: use gpu    = 1
   whisper_backend_init_gpu: found <backend-name>
   ```
   Если всё ещё `use gpu = 0`, значит CUDA-билд не подхватился или переменные окружения не применились.

## Сборки в Docker (локальное окружение)

1. **Требования:** установлен Docker с buildx, доступ к Docker socket (`/var/run/docker.sock`), а также `bash`.
2. **Запустите локальный билд всего проекта.**
   ```bash
   cd docker
   ./local_build.sh
   ```
   Скрипт собирает вспомогательный образ `docker/Dockerfile.build`, пробрасывает `CI_*` переменные (по умолчанию в скрипте `CI_REGISTRY_HOST=localhost`) и внутри контейнера запускает `build-labels` + `docker buildx bake` на основе `docker-compose.yml`.
3. **Переопределите окружение при необходимости.**
   ```bash
   export CI_REGISTRY_HOST=registry.example.com
   export CI_SKIP_PUSH=1          # если нужен только локальный образ
   ./docker/local_build.sh
   ```
4. **Проверка:** после завершения в локальном Docker должны появиться образы
   ```
   ${CI_REGISTRY_HOST}/webrtc-server-komaroff-back/${CI_COMMIT_BRANCH}
   ${CI_REGISTRY_HOST}/webrtc-server-komaroff-whisper/${CI_COMMIT_BRANCH}
   ```
   Для быстрого прогона сервисов можно использовать `docker/docker-compose.yml`, предварительно подставив нужные env (`REGISTRY_HOST`, `CI_COMMIT_BRANCH`, `NATS_URL`, и т.д.) и выполнив `docker compose up --build`.

Эти шаги описывают текущее состояние окружения. Если добавите новые бекэнды или измените структуру `docker/`, обновите инструкцию, чтобы не потерять нюансы.
