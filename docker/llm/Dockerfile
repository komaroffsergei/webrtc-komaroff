FROM python:3.11-slim

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app
ARG INSTALL_DEBUGPY=0

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    cmake \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip setuptools wheel \
    && pip install --no-cache-dir -r requirements.txt
RUN if [ "$INSTALL_DEBUGPY" = "1" ]; then pip install --no-cache-dir debugpy==1.8.13 pydevd-pycharm~=252.26830.0; fi

COPY . /app/src_llm
COPY --from=shared . /app/src_shared

WORKDIR /app/src_llm

RUN mkdir -p "/app/models/llm"

CMD ["python", "-m", "src_llm.main"]
