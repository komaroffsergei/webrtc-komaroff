FROM ruby:3.4.4-slim-bookworm AS base

RUN apt update && apt --fix-missing install -y build-essential pkg-config libpq-dev curl cmake libssl-dev libyaml-dev\
     && rm -rf /var/lib/apt/lists/*

RUN echo 'gem: --no-document' >> ~/.gemrc

WORKDIR /app

ENV BUNDLE_BUILD__WHISPERCPP="--disable-ggml-cuda --disable-ggml-openblas"

COPY Gemfile* /app/

RUN bundle install --jobs $(nproc) --retry=3 && \
    bundle clean --force && rm -rf /usr/local/bundle/cache/*

COPY . /app

ENV RACK_ENV=production NODE_ENV=production
RUN rake -T | grep 'rake build' && rake build || echo 'no build task'

ENV WHISPER_MODEL_NAME=medium \
    WHISPER_VAD_MODEL_NAME=silero-v5.1.2 \
    WHISPER_MODELS_DIR=/app/models

RUN mkdir -p ${WHISPER_MODELS_DIR}
RUN bundle exec ruby scripts/download_model.rb \
      --model ${WHISPER_MODEL_NAME} \
      --vad-model ${WHISPER_VAD_MODEL_NAME} \
      --models-dir ${WHISPER_MODELS_DIR}

# used in .gitlab-ci.yml Tests.
FROM base AS tests
# COPY . . required test fixtures
CMD bundle exec rspec

FROM ruby:3.4.4-slim-bookworm AS deploy
RUN apt update && apt install --fix-missing -y bash curl libssl-dev bash curl wget libpq-dev libyaml-0-2\
     && rm -rf /var/lib/apt/lists/*

COPY --from=base /usr/local/bundle /usr/local/bundle
COPY --from=base /app/models /app/models

# Force start & wait test Stage
# COPY --from=tests /app/src/spec/results /app/src/spec/results

COPY . /app

ENV RUBY_YJIT_ENABLE=1 \
    SERVER_ENV=production \
    RACK_ENV=production \
    PORT=7000 \
    WHISPER_MODEL_NAME=medium \
    WHISPER_VAD_MODEL_NAME=silero-v5.1.2 \
    WHISPER_MODELS_DIR=/app/models

WORKDIR /app

# --start_period=5s (Unknown flag: start_period)
HEALTHCHECK --interval=15s --timeout=2s --retries=3 CMD curl --fail http://127.0.0.1:$PORT/healthcheck || exit 1
CMD bundle exec rackup -o 0.0.0.0 -p $PORT -s falcon
# docker-compose build --progress plain
