"""
Configuration - централизованная конфигурация сервиса
"""

import os
from dataclasses import dataclass
from typing import Optional




@dataclass
class NatsConfig:
    """Конфигурация NATS."""
    url: str
    audio_subject: str
    whisper_subject: str
    logs_subject: str
    
    @classmethod
    def from_env(cls) -> "NatsConfig":
        """Создать конфигурацию из переменных окружения."""
        return cls(
            url=os.getenv("NATS_URL", "nats://localhost:4222"),
            audio_subject=os.getenv(os.getenv("NATS_AUDIO_SUBJECT"), "audio.frames"),
            whisper_subject=os.getenv(os.getenv("NATS_WHISPER_SUBJECT"), "whisper.transcription"),
            logs_subject=os.getenv(os.getenv("NATS_LOGS_SUBJECT"), "whisper.logs")
        )


@dataclass
class WhisperConfig:
    """Конфигурация Whisper."""
    model_path: str
    recordings_dir: str
    save_recordings: bool
    
    @classmethod
    def from_env(cls) -> "WhisperConfig":
        """Создать конфигурацию из переменных окружения."""
        # Если задан WHISPER_MODEL_NAME, строим путь к модели в cache
        model_name = os.getenv("WHISPER_MODEL_NAME")
        if model_name:
            # Используем ./models для локальной разработки, /app/models для Docker
            default_models_dir = "./models" if not os.path.exists("/app") else "/app/models"
            models_dir = os.getenv("MODELS_DIR", default_models_dir)
            model_path = f"{models_dir}/{model_name}"
        else:
            # Иначе используем WHISPER_MODEL или default
            model_path = os.getenv("WHISPER_MODEL", "medium")
        
        return cls(
            model_path=model_path,
            recordings_dir=os.getenv("RECORDINGS_DIR", "recordings"),
            save_recordings=os.getenv("SAVE_RECORDINGS", "true").lower() == "true"
        )


@dataclass
class VADConfig:
    """Конфигурация Silero VAD."""
    sample_rate: int
    min_speech_duration_ms: int
    min_silence_duration_ms: int
    max_speech_duration_s: float
    speech_pad_ms: int
    threshold: float
    buffer_check_interval: float
    
    @classmethod
    def from_env(cls) -> "VADConfig":
        """Создать конфигурацию из переменных окружения."""
        return cls(
            sample_rate=int(os.getenv("VAD_SAMPLE_RATE", "16000")),
            min_speech_duration_ms=int(os.getenv("VAD_MIN_SPEECH_DURATION_MS", "250")),
            min_silence_duration_ms=int(os.getenv("VAD_MIN_SILENCE_DURATION_MS", "300")),
            max_speech_duration_s=float(os.getenv("VAD_MAX_SPEECH_DURATION_S", "30.0")),
            speech_pad_ms=int(os.getenv("VAD_SPEECH_PAD_MS", "30")),
            threshold=float(os.getenv("VAD_THRESHOLD", "0.5")),
            buffer_check_interval=float(os.getenv("VAD_BUFFER_CHECK_INTERVAL", "1.0"))
        )


@dataclass
class ServiceConfig:
    """Общая конфигурация сервиса."""
    nats: NatsConfig
    whisper: WhisperConfig
    vad: VADConfig
    log_level: str
    
    @classmethod
    def from_env(cls) -> "ServiceConfig":
        """Создать конфигурацию из переменных окружения."""
        return cls(
            nats=NatsConfig.from_env(),
            whisper=WhisperConfig.from_env(),
            vad=VADConfig.from_env(),
            log_level=os.getenv("LOG_LEVEL", "INFO")
        )
