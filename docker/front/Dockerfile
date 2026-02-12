FROM node:22.8.0-alpine3.19 AS build

ARG CI_PIPELINE_ID

WORKDIR /app
COPY package.json package-lock.json /app/
RUN npm ci
COPY . /app/

ENV COM_GITLAB_CI_PIPELINE_IID=$CI_PIPELINE_ID

RUN npm run build

FROM nginx:1.20-alpine as deploy

ENV FRONT_NATS_WS_UPSTREAM=nats

RUN rm -rf /usr/share/nginx/html/*
RUN rm -f /etc/nginx/conf.d/*.conf /etc/nginx/templates/*.conf.template /etc/nginx/sites-enabled/*.conf

COPY --from=build /app/dist /usr/share/nginx/html

COPY --from=nginx /default.conf /etc/nginx/templates/default.conf.template
COPY --from=nginx /nginx.conf /etc/nginx/nginx.conf
COPY --from=nginx /50-settings.sh /docker-entrypoint.d/50-settings.sh
RUN chmod +x /docker-entrypoint.d/50-settings.sh

CMD ["nginx", "-g", "daemon off;"]
