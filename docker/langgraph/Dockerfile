FROM python:3.11-slim

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app

COPY requirements.txt .
ARG INSTALL_DEBUGPY=0
RUN pip install --no-cache-dir --upgrade pip setuptools wheel \
    && pip install --no-cache-dir -r requirements.txt
RUN if [ "$INSTALL_DEBUGPY" = "1" ]; then pip install --no-cache-dir debugpy==1.8.13 pydevd-pycharm~=252.26830.0; fi

COPY . /app/src_langgraph
COPY --from=shared . /app/src_shared

WORKDIR /app/src_langgraph

CMD ["python", "-m", "src_langgraph.main"]
