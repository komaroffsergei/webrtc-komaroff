FROM ruby:3.4.5-slim-bookworm AS base

ARG APP_PATH=src_langgraph_rb_node
ARG BUNDLER_VERSION=2.6.7

RUN apt update && apt --fix-missing install -y build-essential pkg-config bash curl git libpq-dev openssh-client \
     libsqlite3-dev libssl-dev libgeos-dev libyaml-dev libgomp1 \
     && rm -rf /var/lib/apt/lists/* \
     && test -e /usr/lib/x86_64-linux-gnu/libgomp.so.1

RUN echo 'gem: --no-document' >> ~/.gemrc
RUN gem install bundler -v ${BUNDLER_VERSION} --no-document && \
    gem install ruby-debug-ide --no-document

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

CMD ["bundle", "exec", "ruby", "./lib/src_langgraph_rb_node/runtime/service.rb"]
