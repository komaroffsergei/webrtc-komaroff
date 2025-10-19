FROM python:3.11-slim

WORKDIR /app

RUN apt-get update && apt-get install -y \
    ffmpeg libsm6 libxext6 libgl1 libglib2.0-0 libavformat-dev libavcodec-dev  \
    libavdevice-dev libavfilter-dev  libswresample-dev libswscale-dev pkg-config\
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .

RUN pip install --no-cache-dir -r requirements.txt
RUN pip install --upgrade pip setuptools wheel
COPY . .

ENV SERVER_ENV=production \
    PORT=8000

# RUN chmod +x ./run.sh

CMD ["python", "main.py"]
