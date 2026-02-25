FROM python:3.11-slim

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app

COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip setuptools wheel \
    && pip install --no-cache-dir -r requirements.txt

COPY . /app/src_langgraph
COPY --from=shared . /app/src_shared

WORKDIR /app/src_langgraph

CMD ["python", "-m", "src_langgraph.main"]
