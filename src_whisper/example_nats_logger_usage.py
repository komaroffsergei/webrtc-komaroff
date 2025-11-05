#!/usr/bin/env python3
"""
Пример использования NatsLogger для отправки логов в NATS.
Этот пример показывает, как использовать NatsLogger из любого сервиса.
"""

import asyncio
import nats
from datetime import datetime
from nats_logger import NatsLogger


async def example_basic_logging():
    """Пример базового логирования"""
    
    # Подключение к NATS
    nc = await nats.connect("nats://localhost:4222")
    
    # Создание логгера
    logger = NatsLogger(
        nc=nc,
        subject="example.logs",
        service_name="example_service"
    )
    
    # Базовые логи
    await logger.log_debug("Debug message", category="system")
    await logger.log_info("Service started", category="system")
    await logger.log_warning("High memory usage", category="system", memory_mb=512)
    await logger.log_error("Connection failed", category="nats", error_code=500)
    
    await nc.close()
    print("Basic logging example completed")


async def example_transcription_logging():
    """Пример логирования транскрипции"""
    
    nc = await nats.connect("nats://localhost:4222")
    logger = NatsLogger(nc, "whisper.logs", "whisper")
    
    # Симуляция транскрипции
    audio_duration = 3.45
    audio_bytes = 331200
    
    # Логируем начало
    start_timestamp = await logger.log_transcription_start(
        audio_duration=audio_duration,
        audio_bytes=audio_bytes
    )
    
    # Симуляция обработки
    await asyncio.sleep(1.2)
    
    # Логируем окончание
    await logger.log_transcription(
        text="Hello world from whisper",
        segments=2,
        audio_duration=audio_duration,
        transcription_time=1.23,
        start_timestamp=start_timestamp,
        end_timestamp=datetime.utcnow().isoformat() + "Z"
    )
    
    await nc.close()
    print("Transcription logging example completed")


async def example_event_logging():
    """Пример логирования событий с дополнительными полями"""
    
    nc = await nats.connect("nats://localhost:4222")
    logger = NatsLogger(nc, "service.logs", "audio_processor")
    
    # WebRTC событие
    await logger.log_event(
        event_type="connection",
        message="WebRTC peer connected",
        category="webrtc",
        level="info",
        peer_id="abc123",
        codec="opus",
        sample_rate=48000
    )
    
    # Аудио метрика
    await logger.log_event(
        event_type="metric",
        message="Audio chunk processed",
        category="audio",
        level="debug",
        chunk_size=4096,
        duration_ms=85,
        latency_ms=12
    )
    
    # Ошибка с контекстом
    await logger.log_event(
        event_type="error",
        message="Failed to decode audio frame",
        category="audio",
        level="error",
        frame_number=1234,
        codec="opus",
        error_details="Invalid packet size"
    )
    
    await nc.close()
    print("Event logging example completed")


async def example_structured_logging():
    """Пример логирования со структурированными данными"""
    
    nc = await nats.connect("nats://localhost:4222")
    logger = NatsLogger(nc, "service.logs", "data_processor")
    
    # Лог с множественными параметрами
    await logger.log_info(
        "Data processing completed",
        category="system",
        input_size=1024000,
        output_size=512000,
        compression_ratio=2.0,
        duration_ms=450,
        cache_hits=125,
        cache_misses=5
    )
    
    # Лог производительности
    await logger.log_info(
        "Performance metrics",
        category="system",
        cpu_usage=45.2,
        memory_mb=256,
        disk_io_mbps=15.3,
        network_mbps=8.7,
        active_connections=12
    )
    
    await nc.close()
    print("Structured logging example completed")


async def example_error_handling():
    """Пример логирования ошибок с обработкой исключений"""
    
    nc = await nats.connect("nats://localhost:4222")
    logger = NatsLogger(nc, "service.logs", "error_handler")
    
    try:
        # Симуляция ошибки
        result = 10 / 0
    except ZeroDivisionError as e:
        await logger.log_error(
            f"Math error: {str(e)}",
            category="system",
            exception_type=type(e).__name__,
            operation="division",
            operands=[10, 0]
        )
    
    try:
        # Симуляция другой ошибки
        raise ValueError("Invalid configuration parameter")
    except ValueError as e:
        await logger.log_error(
            f"Configuration error: {str(e)}",
            category="system",
            exception_type=type(e).__name__,
            config_key="audio_sample_rate",
            config_value="invalid"
        )
    
    await nc.close()
    print("Error handling example completed")


async def main():
    """Запуск всех примеров"""
    
    print("\n=== NatsLogger Examples ===\n")
    
    try:
        print("1. Basic logging...")
        await example_basic_logging()
        await asyncio.sleep(0.5)
        
        print("\n2. Transcription logging...")
        await example_transcription_logging()
        await asyncio.sleep(0.5)
        
        print("\n3. Event logging...")
        await example_event_logging()
        await asyncio.sleep(0.5)
        
        print("\n4. Structured logging...")
        await example_structured_logging()
        await asyncio.sleep(0.5)
        
        print("\n5. Error handling...")
        await example_error_handling()
        
        print("\n=== All examples completed ===\n")
        
    except Exception as e:
        print(f"Example failed: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    asyncio.run(main())
