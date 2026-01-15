FROM postgres:16-alpine

ENV PGDATA=/var/lib/postgresql/data/pgdata

COPY ./data/init /docker-entrypoint-initdb.d/

# Fail early if the base schema is missing
RUN test -f /docker-entrypoint-initdb.d/010_core_schema.sql

EXPOSE 5432
