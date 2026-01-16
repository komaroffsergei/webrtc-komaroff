FROM postgres:16-alpine

ENV PGDATA=/var/lib/postgresql/data/pgdata

# Save original entrypoint
RUN mv /usr/local/bin/docker-entrypoint.sh /usr/local/bin/docker-entrypoint-original.sh

# Init scripts (run only on first database initialization)
COPY ./data/init /docker-entrypoint-initdb.d/
RUN test -f /docker-entrypoint-initdb.d/010_core_schema.sql

# Always-run migrations (run on every container start)
COPY ./data/migrations /migrations/

# Wrapper entrypoint (comes from additional_contexts "postgres")
COPY --from=postgres ./entrypoint-with-migrations.sh /usr/local/bin/docker-entrypoint.sh
RUN chmod +x /usr/local/bin/docker-entrypoint.sh

EXPOSE 5432
