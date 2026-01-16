FROM postgres:16-alpine

ENV PGDATA=/var/lib/postgresql/data/pgdata

# Keep init scripts (only first time volume is created)
COPY ./data/init /docker-entrypoint-initdb.d/
RUN test -f /docker-entrypoint-initdb.d/010_core_schema.sql

# Copy "always-run" migrations
COPY ./data/migrations /migrations/

# Wrap entrypoint to run migrations on every container start
RUN mv /usr/local/bin/docker-entrypoint.sh /usr/local/bin/docker-entrypoint-original.sh
COPY --from=postgres ./entrypoint-with-migrations.sh /usr/local/bin/docker-entrypoint.sh
RUN chmod +x /usr/local/bin/docker-entrypoint.sh

EXPOSE 5432




