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

COPY . .
COPY --from=shared . /app/src_shared

ENV API_HOST=0.0.0.0 \
    API_PORT=8100

EXPOSE 8100

CMD ["python", "main.py"]
