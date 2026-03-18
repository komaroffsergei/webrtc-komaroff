FROM ruby:3.4.5-slim-bookworm AS base

ARG APP_PATH=src_langgraph_rb

RUN apt update && apt --fix-missing install -y build-essential pkg-config bash curl libpq-dev openssh-client \
     libsqlite3-dev libssl-dev libgeos-dev libyaml-dev libgomp1 \
     && rm -rf /var/lib/apt/lists/* \
     && test -e /usr/lib/x86_64-linux-gnu/libgomp.so.1

RUN echo 'gem: --no-document' >> ~/.gemrc
RUN gem install ruby-debug-ide bundler --no-document

WORKDIR /app

COPY ${APP_PATH}/ /app

RUN bundle install --jobs $(nproc) --retry=3 && \
    bundle clean --force && rm -rf /usr/local/bundle/cache/*

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
    DOCKER_CONTAINER=true

WORKDIR /app

CMD ["bundle", "exec", "ruby", "./bin/service"]
