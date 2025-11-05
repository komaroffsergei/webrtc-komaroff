#!/usr/bin/env python3
import asyncio
import json
import logging
import os
from datetime import datetime
from typing import Tuple, Optional
from pathlib import Path

import nats
from dotenv import load_dotenv

from audio_buffer import AudioBuffer
from nats_log_handler import NatsLogHandler
from nats_logger import NatsLogger
from whisper_processor import WhisperProcessor
from vad_processor import VADProcessor
from voice_commands import CommandRegistry, CommandMatcher
from commands.alert_command import register_alert_command
from commands.example_commands import register_example_commands

# Загружаем .env файл если есть
load_dotenv()

logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO"),
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
log = logging.getLogger("whisper")


def _resolve_subject(env_value: Optional[str], default: str) -> str:
    subject = (env_value or "").strip()
    if not subject:
        subject = default
    return subject[:-1] if subject.endswith(".") else subject


NATS_URL = os.getenv("NATS_URL", "nats://localhost:4222")
NATS_AUDIO_SUBJECT = _resolve_subject(os.getenv("NATS_AUDIO_SUBJECT"), "audio.frames")
NATS_WHISPER_SUBJECT = _resolve_subject(os.getenv("NATS_WHISPER_SUBJECT"), "whisper.transcription")
NATS_LOGS_SUBJECT = _resolve_subject(os.getenv("NATS_LOGS_SUBJECT"), "whisper.logs")

MODEL_PATH = os.getenv("WHISPER_MODEL", "models/whisper-medium-ru-fine-ct2")
RECORDINGS_DIR = os.getenv("RECORDINGS_DIR", "recordings")

# Параметры буферизации
MAX_BUFFER_DURATION = float(os.getenv("MAX_BUFFER_DURATION", "60.0"))  # Максимальный буфер перед принудительной обработки
SAVE_RECORDINGS = os.getenv("SAVE_RECORDINGS", "true").lower() == "true"

# VAD параметры
ENABLE_VAD = os.getenv("ENABLE_VAD", "true").lower() == "true"
VAD_SILENCE_THRESHOLD = float(os.getenv("VAD_SILENCE_THRESHOLD", "0.02"))
VAD_MIN_SILENCE_DURATION = float(os.getenv("VAD_MIN_SILENCE_DURATION", "0.3"))  # Пауза для определения конца фразы
VAD_MIN_SPEECH_DURATION = float(os.getenv("VAD_MIN_SPEECH_DURATION", "0.5"))
VAD_PADDING_DURATION = float(os.getenv("VAD_PADDING_DURATION", "0.1"))
VAD_CHECK_INTERVAL = float(os.getenv("VAD_CHECK_INTERVAL", "0.5"))  # Как часто проверять окончание фразы


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
    
    # Инициализация VAD
    vad_processor = None
    if ENABLE_VAD:
        vad_processor = VADProcessor(
            silence_threshold=VAD_SILENCE_THRESHOLD,
            min_silence_duration=VAD_MIN_SILENCE_DURATION,
            min_speech_duration=VAD_MIN_SPEECH_DURATION,
            padding_duration=VAD_PADDING_DURATION,
            sample_rate=48000
        )
        log.info(f"VAD enabled: silence_threshold={VAD_SILENCE_THRESHOLD}, "
                f"min_silence={VAD_MIN_SILENCE_DURATION}s, "
                f"min_speech={VAD_MIN_SPEECH_DURATION}s")
    else:
        log.info("VAD disabled")
    
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
    log.info(f"Listening: {NATS_AUDIO_SUBJECT}, Publishing: {NATS_WHISPER_SUBJECT}")

    # Настраиваем отправку логов в NATS
    whisper_logger = logging.getLogger("whisper")
    if not any(isinstance(handler, NatsLogHandler) for handler in whisper_logger.handlers):
        nats_handler = NatsLogHandler(nc, NATS_LOGS_SUBJECT, level=logging.DEBUG)
        nats_handler.setFormatter(logging.Formatter('%(name)s: %(message)s'))
        whisper_logger.addHandler(nats_handler)
        log.info(f"NATS log handler enabled: subject={NATS_LOGS_SUBJECT}")
    
    # Инициализируем унифицированный NATS логгер
    nats_logger = NatsLogger(nc, NATS_LOGS_SUBJECT, service_name="whisper")

    async def process_buffer():
        """Обработать накопленный аудио буфер"""
        try:
            # Получаем аудио данные
            audio_data = audio_buffer.get_audio_data()
            
            if not audio_data:
                log.warning("Empty audio buffer")
                audio_buffer.clear()
                return
            
            # Конвертируем в numpy array для VAD
            import numpy as np
            if audio_buffer.sample_width == 2:
                audio_array = np.frombuffer(audio_data, dtype=np.int16)
                audio_float = audio_array.astype(np.float32) / 32768.0
            else:
                audio_array = np.frombuffer(audio_data, dtype=np.int32)
                audio_float = audio_array.astype(np.float32) / 2147483648.0
            
            # Применяем VAD если включен
            speech_segments_float = []
            if vad_processor and ENABLE_VAD:
                # Проверяем наличие речи
                if not vad_processor.has_speech(audio_float):
                    log.info("No speech detected in buffer (VAD)")
                    audio_buffer.clear()
                    return
                
                # Разделяем на сегменты с речью
                speech_segments_float = vad_processor.split_audio_by_speech(audio_float)
                
                if not speech_segments_float:
                    log.info("No speech segments after VAD filtering")
                    audio_buffer.clear()
                    return
                
                speech_ratio = vad_processor.get_speech_ratio(audio_float)
                log.info(f"VAD: {len(speech_segments_float)} segments, {speech_ratio*100:.1f}% speech")
                
                # Сохраняем каждый сегмент отдельно
                if SAVE_RECORDINGS:
                    from datetime import datetime
                    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                    
                    for idx, segment_float in enumerate(speech_segments_float):
                        # Конвертируем сегмент в bytes
                        if audio_buffer.sample_width == 2:
                            segment_int = (segment_float * 32768.0).astype(np.int16)
                        else:
                            segment_int = (segment_float * 2147483648.0).astype(np.int32)
                        segment_bytes = segment_int.tobytes()
                        
                        # Создаем временный буфер для сохранения
                        segment_buffer = AudioBuffer(recordings_dir=RECORDINGS_DIR)
                        segment_buffer.sample_rate = audio_buffer.sample_rate
                        segment_buffer.channels = audio_buffer.channels
                        segment_buffer.sample_width = audio_buffer.sample_width
                        segment_buffer.frames.append(segment_bytes)
                        segment_buffer.frame_count = 1
                        
                        # Сохраняем с уникальным именем
                        filename = f"segment_{timestamp}_part{idx+1:02d}"
                        wav_path = segment_buffer.save_to_wav(filename)
                        
                        duration = len(segment_float) / audio_buffer.sample_rate
                        log.info(f"Saved speech segment {idx+1}/{len(speech_segments_float)}: {wav_path} ({duration:.2f}s)")
                
                # Объединяем сегменты для транскрипции
                audio_float = np.concatenate(speech_segments_float)
                
                # Конвертируем обратно в bytes
                if audio_buffer.sample_width == 2:
                    audio_int = (audio_float * 32768.0).astype(np.int16)
                else:
                    audio_int = (audio_float * 2147483648.0).astype(np.int32)
                audio_data = audio_int.tobytes()
            else:
                # VAD отключен, сохраняем все как есть
                if SAVE_RECORDINGS:
                    wav_path = audio_buffer.save_to_wav()
                    log.info(f"Saved full recording: {wav_path}")
            
            # Транскрибируем
            bytes_per_sample = max(audio_buffer.sample_width * max(audio_buffer.channels, 1), 1)
            audio_duration = len(audio_data) / (bytes_per_sample * max(audio_buffer.sample_rate, 1))
            
            # Логируем начало транскрипции через NatsLogger
            transcription_start_iso = await nats_logger.log_transcription_start(
                audio_duration=audio_duration,
                audio_bytes=len(audio_data)
            )
            
            start_time = asyncio.get_event_loop().time()
            segments = whisper_processor.transcribe_audio(
                audio_data,
                sample_rate=audio_buffer.sample_rate,
                channels=audio_buffer.channels,
                sample_width=audio_buffer.sample_width
            )
            transcription_time = asyncio.get_event_loop().time() - start_time
            segment_count = len(segments) if segments else 0
            
            # Получаем текст транскрипции
            text = " ".join([seg["text"].strip() for seg in segments if seg.get("text")])
            
            # Логируем окончание транскрипции через NatsLogger
            await nats_logger.log_transcription(
                text=text,
                segments=segment_count,
                audio_duration=audio_duration,
                transcription_time=transcription_time,
                start_timestamp=transcription_start_iso,
                end_timestamp=datetime.utcnow().isoformat() + "Z"
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
                "segments": len(segments),
                "audio_duration": audio_duration,
                "transcription_time": transcription_time
            }
            await nc.publish(NATS_WHISPER_SUBJECT, json.dumps(transcription_msg).encode("utf-8"))
            
            # Проверяем на команды
            command_result = await command_matcher.process_transcription(full_text)
            
            if command_result:
                log.info(f"Command detected: {command_result['command']}")
                
                # Отправляем результат команды
                cmd_result = command_result["result"]
                if "error" not in cmd_result:
                    await nc.publish(NATS_WHISPER_SUBJECT, json.dumps(cmd_result).encode("utf-8"))
            else:
                log.debug("No command matched")
            
            # Очищаем буфер
            audio_buffer.clear()
            
        except Exception as e:
            log.error(f"Error processing buffer: {e}", exc_info=True)
            audio_buffer.clear()

    # Состояние для отслеживания тишины
    last_check_time = asyncio.get_event_loop().time()
    silence_start_time = None
    
    async def check_phrase_end():
        """Периодическая проверка окончания фразы"""
        nonlocal last_check_time, silence_start_time
        
        try:
            while True:
                await asyncio.sleep(VAD_CHECK_INTERVAL)
                
                # Пропускаем если буфер пустой
                if audio_buffer.frame_count == 0:
                    silence_start_time = None
                    continue
                
                duration = audio_buffer.get_duration()
                
                # Принудительная обработка если буфер слишком большой
                if duration >= MAX_BUFFER_DURATION:
                    log.warning(f"Buffer overflow: {duration:.2f}s, forcing processing")
                    asyncio.create_task(process_buffer())
                    silence_start_time = None
                    continue
                
                # Проверяем окончание фразы через VAD
                if vad_processor and ENABLE_VAD and duration >= 1.0:
                    # Получаем последние N секунд для проверки
                    check_duration = min(2.0, duration)
                    audio_data = audio_buffer.get_audio_data()
                    
                    # Конвертируем в float для VAD
                    import numpy as np
                    if audio_buffer.sample_width == 2:
                        audio_array = np.frombuffer(audio_data, dtype=np.int16)
                        audio_float = audio_array.astype(np.float32) / 32768.0
                    else:
                        audio_array = np.frombuffer(audio_data, dtype=np.int32)
                        audio_float = audio_array.astype(np.float32) / 2147483648.0
                    
                    # Берем последние check_duration секунд
                    check_samples = int(check_duration * audio_buffer.sample_rate)
                    tail_audio = audio_float[-check_samples:] if len(audio_float) > check_samples else audio_float
                    
                    # Проверяем энергию в конце буфера
                    window_size = int(0.02 * audio_buffer.sample_rate)  # 20ms
                    if len(tail_audio) >= window_size:
                        # Вычисляем RMS последнего окна
                        last_window = tail_audio[-window_size:]
                        rms = np.sqrt(np.mean(last_window ** 2))
                        
                        is_silent = rms < VAD_SILENCE_THRESHOLD
                        
                        if is_silent:
                            if silence_start_time is None:
                                # Начало тишины
                                silence_start_time = asyncio.get_event_loop().time()
                            else:
                                # Проверяем длительность тишины
                                silence_duration = asyncio.get_event_loop().time() - silence_start_time
                                
                                if silence_duration >= VAD_MIN_SILENCE_DURATION:
                                    # Фраза закончена - обрабатываем
                                    log.info(f"Phrase ended (silence {silence_duration:.2f}s): {duration:.2f}s, {audio_buffer.frame_count} frames")
                                    asyncio.create_task(process_buffer())
                                    silence_start_time = None
                        else:
                            # Есть активность - сбрасываем счетчик тишины
                            silence_start_time = None
                            
        except asyncio.CancelledError:
            pass
        except Exception as e:
            log.error(f"Error in phrase end check: {e}", exc_info=True)
    
    # Запускаем фоновую задачу проверки окончания фраз
    check_task = asyncio.create_task(check_phrase_end())
    
    async def handler(msg: nats.aio.client.Msg):
        """Обработчик входящих аудио фреймов"""
        meta, audio = decode_payload(msg.data)
        if meta is None or audio is None:
            log.warning("Invalid payload, skipping")
            return
        
        # Добавляем фрейм в буфер
        audio_buffer.add_frame(audio, meta)

    await nc.subscribe(NATS_AUDIO_SUBJECT, cb=handler)
    log.info("Subscription established, ready to process audio")

    try:
        while True:
            await asyncio.sleep(3600)
    finally:
        log.info("Shutting down...")
        
        # Останавливаем задачу проверки фраз
        check_task.cancel()
        try:
            await check_task
        except asyncio.CancelledError:
            pass
        
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
