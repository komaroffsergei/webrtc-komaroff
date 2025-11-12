FROM ruby:3.4.5-slim-bookworm AS base

RUN apt update && apt --fix-missing install -y build-essential pkg-config bash curl libpq-dev openssh-client \
     libsqlite3-dev libssl-dev libgeos-dev libyaml-dev cmake libgomp1 \
     && rm -rf /var/lib/apt/lists/* \
     && test -e /usr/lib/x86_64-linux-gnu/libgomp.so.1

RUN curl -fsSL https://deb.nodesource.com/setup_21.x | bash - && \
    apt-get install -y nodejs && npm i -g yarn

RUN echo 'gem: --no-document' >> ~/.gemrc
RUN gem install ruby-debug-ide bundler --no-document

WORKDIR /app

COPY ${APP_PATH}/ /app

RUN bundle install --jobs $(nproc) --retry=3 && \
    bundle clean --force && rm -rf /usr/local/bundle/cache/*

RUN if [ -f package.json ]; then yarn install --frozen-lockfile || npm install; fi

ENV RACK_ENV=production NODE_ENV=production \
    WHISPER_MODEL_NAME=medium \
    WHISPER_VAD_MODEL_NAME=silero-v5.1.2 \
    WHISPER_MODELS_DIR=/app/models \
    WHISPERCPP_FORCE_CPU=1 \
    WHISPERCPP_DISABLE_GPU=1 \
    WHISPER_NO_GPU=1 \
    GGML_NO_GPU=1 \
    GGML_USE_GPU=0 \
    GGML_USE_CUDA=0 \
    GGML_CUDA=0

RUN mkdir -p ${WHISPER_MODELS_DIR}

RUN rm -rf node_modules

FROM ruby:3.4.5-slim-bookworm AS deploy
RUN apt update && apt install --fix-missing -y bash curl libpq-dev openssh-client \
      sqlite3 libssl-dev libgeos-dev libyaml-0-2 libgomp1 \
     && rm -rf /var/lib/apt/lists/* \
     && test -e /usr/lib/x86_64-linux-gnu/libgomp.so.1

RUN echo 'gem: --no-document' >> ~/.gemrc
COPY --from=base /usr/local/bundle /usr/local/bundle
COPY --from=base /app /app

ENV SERVER_ENV=production \
    RACK_ENV=production \
    NODE_ENV=production \
    DOCKER_CONTAINER=true \
    WHISPER_MODEL_NAME=medium \
    WHISPER_VAD_MODEL_NAME=silero-v5.1.2 \
    WHISPER_MODELS_DIR=/app/models \
    PORT=7000 \
    WHISPERCPP_FORCE_CPU=1 \
    WHISPERCPP_DISABLE_GPU=1 \
    WHISPER_NO_GPU=1 \
    GGML_NO_GPU=1 \
    GGML_USE_GPU=0 \
    GGML_USE_CUDA=0 \
    GGML_CUDA=0

WORKDIR /app

HEALTHCHECK --interval=15s --timeout=2s --retries=3 --start-period=30s CMD curl --fail http://localhost:$PORT/healthcheck || exit 1
CMD bundle exec rackup -o 0.0.0.0 -p $PORT -s falcon
