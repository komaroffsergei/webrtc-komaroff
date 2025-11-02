#!/usr/bin/env python3
"""
Whisper Service - Модульная архитектура
Структура: NATS → Phrase Segmenter → File Saver → Whisper → Command Processor
"""

import asyncio
import logging
import os
import json
from dotenv import load_dotenv

# Загружаем конфигурацию
load_dotenv()

# Импорт нод
from nodes import (
    NatsReceiverNode,
    PhraseSegmenterNode,
    FileSaverNode,
    WhisperTranscriberNode,
    RawRecorderNode
)

# Импорт системы команд
from voice_commands import CommandRegistry, CommandMatcher
from commands.alert_command import register_alert_command
from commands.example_commands import register_example_commands

# Настройка логирования
logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO"),
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
log = logging.getLogger("whisper.main")

# Конфигурация
NATS_URL = os.getenv("NATS_URL", "nats://localhost:4222")
AUDIO_SUBJECT = os.getenv("AUDIO_SUBJ", "audio.frames")
WHISPER_SUBJECT = os.getenv("WHISPER_SUBJ", "whisper.transcription")

MODEL_PATH = os.getenv("WHISPER_MODEL", "models/whisper-medium-ru-fine-ct2")
RECORDINGS_DIR = os.getenv("RECORDINGS_DIR", "recordings")
SAVE_RECORDINGS = os.getenv("SAVE_RECORDINGS", "true").lower() == "true"

# Silero VAD параметры
VAD_SAMPLE_RATE = int(os.getenv("VAD_SAMPLE_RATE", "16000"))
VAD_MIN_SPEECH_DURATION_MS = int(os.getenv("VAD_MIN_SPEECH_DURATION_MS", "250"))
VAD_MIN_SILENCE_DURATION_MS = int(os.getenv("VAD_MIN_SILENCE_DURATION_MS", "300"))
VAD_MAX_SPEECH_DURATION_S = float(os.getenv("VAD_MAX_SPEECH_DURATION_S", "30.0"))
VAD_SPEECH_PAD_MS = int(os.getenv("VAD_SPEECH_PAD_MS", "30"))
VAD_THRESHOLD = float(os.getenv("VAD_THRESHOLD", "0.5"))
VAD_BUFFER_CHECK_INTERVAL = float(os.getenv("VAD_BUFFER_CHECK_INTERVAL", "1.0"))


async def main():
    """Главная функция."""
    log.info("=" * 70)
    log.info("Whisper Service - Modular Architecture")
    log.info("=" * 70)
    
    # Инициализация NATS клиента для отправки результатов
    import nats
    nc = await nats.connect(
        servers=[NATS_URL],
        max_reconnect_attempts=-1,
        reconnect_time_wait=2
    )
    log.info(f"Connected to NATS for publishing: {nc.connected_url.netloc}")
    
    # Инициализация системы команд
    command_registry = CommandRegistry()
    register_alert_command(command_registry)
    register_example_commands(command_registry)
    command_matcher = CommandMatcher(command_registry)
    
    log.info(f"Registered {len(command_registry.commands)} voice commands")
    
    # ===== СОЗДАНИЕ НОД =====
    
    # 1. NATS Receiver - получение аудио из NATS
    nats_receiver = NatsReceiverNode(
        nats_url=NATS_URL,
        subject=AUDIO_SUBJECT
    )
    
    # 1.5. Raw Recorder - запись сырого аудио для диагностики
    raw_recorder = RawRecorderNode(
        recordings_dir="recordings_raw",
        max_duration_s=10.0,
        enabled=True
    )
    
    # 2. Phrase Segmenter - нарезка на фразы по тишине
    phrase_segmenter = PhraseSegmenterNode()
    
    # 3. File Saver - сохранение фраз в файлы
    file_saver = FileSaverNode(
        recordings_dir=RECORDINGS_DIR,
        enabled=SAVE_RECORDINGS
    )
    
    # 4. Whisper Transcriber - распознавание речи
    whisper_transcriber = WhisperTranscriberNode(
        model_path=MODEL_PATH
    )
    
    # ===== НАСТРОЙКА CALLBACK ЦЕПОЧКИ =====
    
    # Callback для обработки результатов транскрипции
    async def on_transcription(result: dict):
        """Обработать транскрипцию и отправить в NATS."""
        text = result["text"]
        
        # Отправляем транскрипцию
        transcription_msg = {
            "type": "transcription",
            "text": text,
            "segments": len(result["segments"])
        }
        await nc.publish(WHISPER_SUBJECT, json.dumps(transcription_msg).encode("utf-8"))
        log.info(f"Published transcription: '{text}'")
        
        # Проверяем на команды
        command_result = await command_matcher.process_transcription(text)
        
        if command_result:
            log.info(f"Command detected: {command_result['command']}")
            
            # Отправляем команду
            cmd_result = command_result["result"]
            if "error" not in cmd_result:
                await nc.publish(WHISPER_SUBJECT, json.dumps(cmd_result).encode("utf-8"))
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
