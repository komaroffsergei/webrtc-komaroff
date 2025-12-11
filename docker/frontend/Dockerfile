FROM node:22.8.0-alpine3.19 AS build

WORKDIR /app
COPY package.json package-lock.json /app/
RUN npm ci
COPY . /app/

ARG CI_PIPELINE_ID
ENV COM_GITLAB_CI_PIPELINE_IID $CI_PIPELINE_ID
RUN npm run build

FROM docker-io.monitorsoft.ru/nginx:1.20-alpine as deploy
RUN rm -rf /usr/share/nginx/html/*
COPY --from=build /app/dist /usr/share/nginx/html
COPY --from=docker /nginx/default.conf /etc/nginx/templates/default.conf.template
COPY --from=docker /nginx/nginx.conf /etc/nginx/nginx.conf
COPY --from=docker /nginx/50-settings.sh /docker-entrypoint.d/

CMD ["nginx", "-g", "daemon off;"]
