#!/bin/sh
set -eu

echo "[migrate] wrapper entrypoint started"
echo "[migrate] POSTGRES_DB=${POSTGRES_DB:-} POSTGRES_USER=${POSTGRES_USER:-}"
echo "[migrate] migrations dir:"
ls -la /migrations || true

# стартуем оригинальный entrypoint (он поднимет postgres)
# важно: он должен оставаться PID1 в конце, поэтому пока запускаем в фоне
/usr/local/bin/docker-entrypoint-original.sh "$@" &
pid="$!"

echo "[migrate] waiting for postgres..."
for i in $(seq 1 60); do
  if pg_isready -h 127.0.0.1 -p 5432 -U "${POSTGRES_USER}" -d "${POSTGRES_DB}" >/dev/null 2>&1; then
    echo "[migrate] postgres is ready"
    break
  fi
  sleep 1
done

echo "[migrate] applying migrations..."
# best-effort: не валим контейнер, если миграция уже применена (idempotent)
for f in /migrations/*.sql; do
  echo "[migrate] running $f"
  psql -h 127.0.0.1 -p 5432 -U "${POSTGRES_USER}" -d "${POSTGRES_DB}" -v ON_ERROR_STOP=1 -f "$f"
done

# переводим postgres в foreground: отдаём управление оригинальному процессу
wait "$pid"
