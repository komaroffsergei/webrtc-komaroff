#!/bin/sh
set -eu

ORIG="/usr/local/bin/docker-entrypoint-original.sh"

# Start the official entrypoint in background (it will init db if needed)
"$ORIG" "$@" &
pid="$!"

# Wait for Postgres to be ready
echo "[migrate] waiting for postgres..."
for i in $(seq 1 60); do
  if pg_isready -U "${POSTGRES_USER:-mcp}" -d "${POSTGRES_DB:-mcp}" >/dev/null 2>&1; then
    break
  fi
  sleep 1
done

# Apply migrations every start (best effort)
if pg_isready -U "${POSTGRES_USER:-mcp}" -d "${POSTGRES_DB:-mcp}" >/dev/null 2>&1; then
  echo "[migrate] applying migrations..."
  for f in /migrations/*.sql; do
    if [ -f "$f" ]; then
      echo "[migrate] running $f"
      psql -v ON_ERROR_STOP=1 \
        -U "${POSTGRES_USER:-mcp}" \
        -d "${POSTGRES_DB:-mcp}" \
        -f "$f"
    fi
  done
  echo "[migrate] done"
else
  echo "[migrate] postgres not ready, skipping migrations"
fi

wait "$pid"
