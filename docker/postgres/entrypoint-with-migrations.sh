#!/bin/sh
set -eu

ORIG="/usr/local/bin/docker-entrypoint-original.sh"

echo "[migrate] wrapper entrypoint started"
echo "[migrate] POSTGRES_DB=${POSTGRES_DB:-mcp} POSTGRES_USER=${POSTGRES_USER:-mcp}"
echo "[migrate] migrations dir:"
ls -la /migrations || true

# Start the official entrypoint in background (it will init db if needed)
"$ORIG" "$@" &
pid="$!"

# Wait for Postgres to be ready
echo "[migrate] waiting for postgres..."
for i in $(seq 1 90); do
  if pg_isready -U "${POSTGRES_USER:-mcp}" -d "${POSTGRES_DB:-mcp}" >/dev/null 2>&1; then
    echo "[migrate] pg_isready ok"
    break
  fi
  sleep 1
done

# Apply migrations every start (best effort + retries)
apply_once() {
  for f in /migrations/*.sql; do
    if [ -f "$f" ]; then
      echo "[migrate] running $f"
      psql -v ON_ERROR_STOP=1 \
        -U "${POSTGRES_USER:-mcp}" \
        -d "${POSTGRES_DB:-mcp}" \
        -f "$f"
    fi
  done
}

# Retry psql because sometimes "ready" isn't really ready
echo "[migrate] applying migrations..."
ok=0
for i in $(seq 1 30); do
  if apply_once >/tmp/migrate.log 2>&1; then
    ok=1
    cat /tmp/migrate.log
    echo "[migrate] migrations applied successfully"
    break
  fi
  echo "[migrate] attempt $i failed, retrying..."
  cat /tmp/migrate.log || true
  sleep 1
done

if [ "$ok" -ne 1 ]; then
  echo "[migrate] migrations failed after retries"
  cat /tmp/migrate.log || true
fi

wait "$pid"
