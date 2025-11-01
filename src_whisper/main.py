#!/usr/bin/env python3
import asyncio
import json
import logging
import os
from typing import Tuple, Optional
from pathlib import Path

import nats

from audio_buffer import AudioBuffer
from whisper_processor import WhisperProcessor
from voice_commands import CommandRegistry, CommandMatcher
from commands.alert_command import register_alert_command
from commands.example_commands import register_example_commands

logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO"),
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
log = logging.getLogger("whisper")

NATS_URL = os.getenv("NATS_URL", "nats://localhost:4222")
IN_SUBJ = os.getenv("AUDIO_SUBJ") or os.getenv("NATS_SUBJECT") or "audio.frames"
IN_SUBJ = IN_SUBJ if not str(IN_SUBJ).endswith(".") else f"{IN_SUBJ}frames"
OUT_SUBJ = os.getenv("WHISPER_SUBJ") or "whisper.transcription"

MODEL_PATH = os.getenv("WHISPER_MODEL", "models/whisper-medium-ru-fine-ct2")
RECORDINGS_DIR = os.getenv("RECORDINGS_DIR", "recordings")

# Параметры буферизации
MIN_DURATION = float(os.getenv("MIN_DURATION", "1.0"))  # минимум 1 секунда
MAX_DURATION = float(os.getenv("MAX_DURATION", "30.0"))  # максимум 30 секунд
SAVE_RECORDINGS = os.getenv("SAVE_RECORDINGS", "true").lower() == "true"


def decode_payload(data: bytes) -> Tuple[Optional[dict], Optional[bytes]]:
    if len(data) < 4:
        return None, None
    meta_len = int.from_bytes(data[:4], "big")
    end = 4 + meta_len
    if end > len(data):
        return None, None
    try:
        meta = json.loads(data[4:end].decode("utf-8"))
    except Exception:
        meta = {}
    audio = data[end:]
    return meta, audio


def encode_payload(meta: dict, text: str = "") -> bytes:
    """Кодируем результат транскрипции"""
    meta_copy = meta.copy()
    meta_copy["transcription"] = text
    mb = json.dumps(meta_copy, ensure_ascii=False).encode("utf-8")
    return len(mb).to_bytes(4, "big") + mb


async def main():
    # Инициализация компонентов
    log.info("Initializing Whisper service...")
    
    audio_buffer = AudioBuffer(recordings_dir=RECORDINGS_DIR)
    whisper_processor = WhisperProcessor(model_path=MODEL_PATH)
    
    # Инициализация системы команд
    command_registry = CommandRegistry()
    register_alert_command(command_registry)
    register_example_commands(command_registry)
    
    command_matcher = CommandMatcher(command_registry)
    
    log.info(f"Registered {len(command_registry.commands)} voice commands")
    
    # Подключение к NATS
    urls = [u.strip() for u in str(NATS_URL).split(",") if u.strip()]
    nc = await nats.connect(
        servers=urls or [NATS_URL],
        max_reconnect_attempts=-1,
        reconnect_time_wait=2,
        ping_interval=10,
    )
    log.info(f"Connected to NATS: {nc.connected_url.netloc}")
    log.info(f"Listening: {IN_SUBJ}, Publishing: {OUT_SUBJ}")

    async def process_buffer():
        """Обработать накопленный аудио буфер"""
        try:
            # Сохраняем WAV для отладки
            if SAVE_RECORDINGS:
                wav_path = audio_buffer.save_to_wav()
                log.info(f"Saved recording: {wav_path}")
            
            # Получаем аудио данные
            audio_data = audio_buffer.get_audio_data()
            
            if not audio_data:
                log.warning("Empty audio buffer")
                audio_buffer.clear()
                return
            
            # Транскрибируем
            log.info(f"Transcribing {len(audio_data)} bytes...")
            segments = whisper_processor.transcribe_audio(
                audio_data,
                sample_rate=audio_buffer.sample_rate,
                channels=audio_buffer.channels,
                sample_width=audio_buffer.sample_width
            )
            
            if not segments:
                log.info("No speech detected")
                audio_buffer.clear()
                return
            
            # Объединяем все сегменты
            full_text = " ".join(seg["text"] for seg in segments)
            log.info(f"Transcription: '{full_text}'")
            
            # Отправляем транскрипцию в чат
            transcription_msg = {
                "type": "transcription",
                "text": full_text,
                "segments": len(segments)
            }
            await nc.publish(OUT_SUBJ, json.dumps(transcription_msg).encode("utf-8"))
            
            # Проверяем на команды
            command_result = await command_matcher.process_transcription(full_text)
            
            if command_result:
                log.info(f"Command detected: {command_result['command']}")
                
                # Отправляем результат команды
                cmd_result = command_result["result"]
                if "error" not in cmd_result:
                    await nc.publish(OUT_SUBJ, json.dumps(cmd_result).encode("utf-8"))
            else:
                log.debug("No command matched")
            
            # Очищаем буфер
            audio_buffer.clear()
            
        except Exception as e:
            log.error(f"Error processing buffer: {e}", exc_info=True)
            audio_buffer.clear()

    async def handler(msg: nats.aio.client.Msg):
        """Обработчик входящих аудио фреймов"""
        meta, audio = decode_payload(msg.data)
        if meta is None or audio is None:
            log.warning("Invalid payload, skipping")
            return
        
        # Добавляем фрейм в буфер
        audio_buffer.add_frame(audio, meta)
        
        # Проверяем, нужно ли обработать буфер
        if audio_buffer.should_process(MIN_DURATION, MAX_DURATION):
            duration = audio_buffer.get_duration()
            log.info(f"Buffer ready for processing: {duration:.2f}s, {audio_buffer.frame_count} frames")
            
            # Обрабатываем в фоне
            asyncio.create_task(process_buffer())

    await nc.subscribe(IN_SUBJ, cb=handler)
    log.info("Subscription established, ready to process audio")

    try:
        while True:
            await asyncio.sleep(3600)
    finally:
        log.info("Shutting down...")
        try:
            await nc.drain()
        except Exception:
            pass
        try:
            await nc.close()
        except Exception:
            pass


if __name__ == "__main__":
    asyncio.run(main())
