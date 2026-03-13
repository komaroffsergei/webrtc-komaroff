FROM python:3.11-slim AS base

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app

RUN apt-get update && apt-get install -y --no-install-recommends \
    libavformat-dev libavcodec-dev \
    libavdevice-dev libavfilter-dev libswresample-dev libswscale-dev \
    pkg-config libgomp1 git \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .

ARG INSTALL_DEBUGPY=0

RUN pip install --no-cache-dir --upgrade pip setuptools wheel
RUN pip install -U --force-reinstall -r requirements.txt
RUN if [ "$INSTALL_DEBUGPY" = "1" ]; then pip install --no-cache-dir debugpy==1.8.13 pydevd-pycharm~=252.26830.0; fi

COPY . /app/src_core
COPY --from=shared . /app/src_shared

RUN cat <<'EOF' >/entrypoint.sh
#!/bin/sh
set -e
exec "$@"
EOF

RUN chmod +x /entrypoint.sh

ENV SERVER_ENV=production \
    PORT=8000

WORKDIR /app/src_core

ENTRYPOINT ["/entrypoint.sh"]
CMD ["python", "-m", "src_core.main"]
