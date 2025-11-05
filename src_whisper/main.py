#!/usr/bin/env python3
"""
Whisper Service - сервис транскрипции речи с использованием Whisper и Silero VAD

Архитектура:
    NATS → Raw Recorder → Phrase Segmenter → File Saver → Whisper Transcriber → Command Processor
    
Компоненты:
    - NatsReceiverNode: прием аудио фреймов из NATS
    - RawRecorderNode: запись сырого аудио для диагностики (опционально)
    - PhraseSegmenterNode: сегментация на фразы с помощью Silero VAD
    - FileSaverNode: сохранение фраз в WAV файлы (опционально)
    - WhisperTranscriberNode: распознавание речи через faster-whisper
    - Command Processor: обработка голосовых команд
"""

import asyncio
import logging
import os
import json
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()

from nodes import (
    NatsReceiverNode,
    PhraseSegmenterNode,
    FileSaverNode,
    WhisperTranscriberNode,
    RawRecorderNode
)
from voice_commands import CommandRegistry, CommandMatcher
from commands.alert_command import register_alert_command
from config import ServiceConfig

# Загрузка конфигурации
config = ServiceConfig.from_env()

# Настройка логирования
logging.basicConfig(
    level=config.log_level,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
log = logging.getLogger("whisper.main")


async def main():
    """Точка входа в сервис транскрипции."""
    log.info("=" * 70)
    log.info("Whisper Service Starting")
    log.info("=" * 70)
    
    # Инициализация NATS клиента
    import nats
    nc = await nats.connect(
        servers=[config.nats.url],
        max_reconnect_attempts=-1,
        reconnect_time_wait=2
    )
    log.info(f"Connected to NATS: {nc.connected_url.netloc}")
    log.info(f"Subjects: audio={config.nats.audio_subject}, whisper={config.nats.whisper_subject}, logs={config.nats.logs_subject}")
    
    # Настраиваем отправку логов в NATS
    from nats_log_handler import NatsLogHandler
    from nats_logger import NatsLogger
    whisper_logger = logging.getLogger("whisper")
    if not any(isinstance(handler, NatsLogHandler) for handler in whisper_logger.handlers):
        nats_handler = NatsLogHandler(nc, config.nats.logs_subject, level=logging.DEBUG)
        nats_handler.setFormatter(logging.Formatter('%(name)s: %(message)s'))
        whisper_logger.addHandler(nats_handler)
        log.info("NATS log handler enabled")
    
    # Инициализируем унифицированный NATS логгер
    nats_logger = NatsLogger(nc, config.nats.logs_subject, service_name="whisper")
    
    # Регистрируем команды
    command_registry = CommandRegistry()
    register_alert_command(command_registry)
    command_matcher = CommandMatcher(command_registry)
    
    log.info(f"Registered {len(command_registry.commands)} voice commands")
    
    # Создание нод обработки
    nats_receiver = NatsReceiverNode(
        nats_url=config.nats.url,
        subject=config.nats.audio_subject
    )
    
    raw_recorder = RawRecorderNode(
        recordings_dir="recordings_raw",
        max_duration_s=10.0,
        enabled=False
    )
    
    phrase_segmenter = PhraseSegmenterNode(
        sample_rate=config.vad.sample_rate,
        min_speech_duration_ms=config.vad.min_speech_duration_ms,
        min_silence_duration_ms=config.vad.min_silence_duration_ms,
        max_speech_duration_s=config.vad.max_speech_duration_s,
        speech_pad_ms=config.vad.speech_pad_ms,
        threshold=config.vad.threshold,
        buffer_check_interval_s=config.vad.buffer_check_interval
    )
    
    file_saver = FileSaverNode(
        recordings_dir=config.whisper.recordings_dir,
        enabled=config.whisper.save_recordings
    )
    
    whisper_transcriber = WhisperTranscriberNode(
        model_path=config.whisper.model_path
    )
    
    # ===== НАСТРОЙКА CALLBACK ЦЕПОЧКИ =====
    
    # Callback для обработки результатов транскрипции
    async def on_transcription(result: dict):
        """Обработать транскрипцию и отправить в NATS."""
        text = result["text"]
        segments = len(result["segments"])
        audio_duration = result.get("audio_duration", 0)
        transcription_time = result.get("transcription_time", 0)
        
        # Логируем транскрипцию через NatsLogger
        start_timestamp = result.get("start_timestamp")
        end_timestamp = datetime.utcnow().isoformat() + "Z"
        
        await nats_logger.log_transcription(
            text=text,
            segments=segments,
            audio_duration=audio_duration,
            transcription_time=transcription_time,
            start_timestamp=start_timestamp,
            end_timestamp=end_timestamp
        )
        
        # Отправляем транскрипцию
        transcription_msg = {
            "type": "transcription",
            "text": text,
            "segments": segments,
            "audio_duration": audio_duration,
            "transcription_time": transcription_time
        }
        await nc.publish(config.nats.whisper_subject, json.dumps(transcription_msg).encode("utf-8"))
        log.info(f"Published transcription: '{text}'")
        
        # Проверяем на команды
        command_result = await command_matcher.process_transcription(text)
        
        if command_result:
            log.info(f"Command detected: {command_result['command']}")
            
            # Отправляем команду
            cmd_result = command_result["result"]
            if "error" not in cmd_result:
                await nc.publish(config.nats.whisper_subject, json.dumps(cmd_result).encode("utf-8"))
                log.info(f"Published command: {command_result['command']}")
    
    # Связываем ноды через callback
    # nats_receiver.set_callback(raw_recorder.process)
    nats_receiver.set_callback(phrase_segmenter.process)
    phrase_segmenter.set_callback(file_saver.process)
    file_saver.set_callback(whisper_transcriber.process)
    whisper_transcriber.set_callback(on_transcription)
    
    log.info("")
    log.info("Pipeline configured:")
    log.info("  NATS Receiver → Raw Recorder → Phrase Segmenter → File Saver → Whisper → Commands")
    log.info("")
    
    # ===== ЗАПУСК НОД =====
    
    try:
        # Запускаем ноды
        await raw_recorder.start()
        await phrase_segmenter.start()
        await file_saver.start()
        await whisper_transcriber.start()
        await nats_receiver.start()  # Запускаем последним
        
        log.info("All nodes started successfully")
        log.info("Listening for audio frames...")
        log.info("")
        
        # Ждем бесконечно
        while True:
            await asyncio.sleep(3600)
            
    except KeyboardInterrupt:
        log.info("Shutting down...")
    finally:
        # Останавливаем ноды в обратном порядке
        await nats_receiver.stop()
        await whisper_transcriber.stop()
        await file_saver.stop()
        await phrase_segmenter.stop()
        await raw_recorder.stop()
        
        # Закрываем NATS для публикации
        try:
            await nc.drain()
            await nc.close()
        except Exception:
            pass
        
        log.info("Shutdown complete")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
