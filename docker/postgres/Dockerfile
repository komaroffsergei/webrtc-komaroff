FROM postgres:16-alpine

# init scripts
COPY ./data/init /docker-entrypoint-initdb.d/
RUN test -f /docker-entrypoint-initdb.d/010_core_schema.sql

# migrations
COPY ./data/migrations /migrations/

# сохранить оригинальный entrypoint
RUN mv /usr/local/bin/docker-entrypoint.sh /usr/local/bin/docker-entrypoint-original.sh

# wrapper entrypoint из additional_contexts "postgres"
COPY --from=postgres ./entrypoint-with-migrations.sh /usr/local/bin/docker-entrypoint.sh
RUN chmod +x /usr/local/bin/docker-entrypoint.sh

EXPOSE 5432
