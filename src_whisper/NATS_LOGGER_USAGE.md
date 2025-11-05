# NatsLogger - Унифицированная система логирования в NATS

## Описание

`NatsLogger` - универсальный класс для отправки структурированных логов в NATS из любого сервиса. Логи автоматически передаются на backend и отображаются в Debug Panel браузера с форматированием.

## Быстрый старт

### Инициализация

```python
from nats_logger import NatsLogger

# Создать логгер
nats_logger = NatsLogger(
    nc=nats_client,              # NATS клиент
    subject="service.logs",      # NATS subject для логов
    service_name="my_service"    # Имя вашего сервиса
)
```

### Базовое использование

```python
# Отправить обычные логи
await nats_logger.log_debug("Debug information", category="system")
await nats_logger.log_info("Operation completed", category="audio")
await nats_logger.log_warning("Low memory", category="system")
await nats_logger.log_error("Connection failed", category="nats")
```

### Логи с дополнительными полями

```python
# Добавить произвольные поля через kwargs
await nats_logger.log_info(
    "Audio processed",
    category="audio",
    duration=1.23,
    samples=48000,
    format="pcm16"
)
```

### Специализированные методы

#### Логирование транскрипции

```python
# Начало транскрипции
start_timestamp = await nats_logger.log_transcription_start(
    audio_duration=3.45,
    audio_bytes=331200
)

# Окончание транскрипции
await nats_logger.log_transcription(
    text="Hello world",
    segments=2,
    audio_duration=3.45,
    transcription_time=1.23,
    start_timestamp=start_timestamp,
    end_timestamp=datetime.utcnow().isoformat() + "Z"
)
```

#### Логирование событий

```python
await nats_logger.log_event(
    event_type="connection",
    message="WebRTC connected",
    category="webrtc",
    level="info",
    peer_id="abc123",
    codec="opus"
)
```

## Категории логов

Поддерживаемые категории (отображаются как фильтры в Debug Panel):

- `system` - системные события
- `webrtc` - WebRTC соединения и аудио потоки
- `nats` - события NATS (подписки, публикации)
- `audio` - обработка аудио
- `whisper` - транскрипция и распознавание
- `general` - прочие события

## Уровни логов

- `debug` - детальная отладочная информация
- `info` - информационные сообщения
- `warning` - предупреждения
- `error` - ошибки

## Структура сообщения

Все логи отправляются в NATS в следующем формате:

```json
{
    "type": "log",
    "level": "info",
    "category": "whisper",
    "message": "Transcription completed",
    "service": "whisper",
    "timestamp": "2024-01-15T10:30:46.353Z",
    
    // Дополнительные поля (опционально)
    "audio_duration": 3.45,
    "transcription_time": 1.23,
    "segments": 2,
    "text": "Hello world"
}
```

## Интеграция в новый сервис

### 1. Скопировать файл

```bash
cp src_whisper/nats_logger.py your_service/nats_logger.py
```

### 2. Инициализировать в коде

```python
import asyncio
import nats
from nats_logger import NatsLogger

async def main():
    # Подключиться к NATS
    nc = await nats.connect("nats://localhost:4222")
    
    # Создать логгер
    logger = NatsLogger(
        nc=nc,
        subject="your_service.logs",
        service_name="your_service"
    )
    
    # Использовать
    await logger.log_info("Service started", category="system")
    
    # Ваша логика
    ...
    
    await logger.log_info("Service stopped", category="system")
    await nc.close()

if __name__ == "__main__":
    asyncio.run(main())
```

### 3. Настроить backend для подписки на логи

В `src_back/server/handlers/handle_track.py` добавить подписку на ваш subject:

```python
async def _your_service_logs_cb(msg):
    data = json.loads(msg.data.decode())
    await sse_log(
        request.app,
        message=data.get('message', ''),
        level=data.get('level', 'info'),
        category=data.get('category', 'general'),
        extra=data
    )

await nc.subscribe("your_service.logs", cb=_your_service_logs_cb)
```

## Преимущества

1. **Унифицированный формат** - все сервисы используют одну структуру
2. **Автоматические timestamp и uid** - не нужно добавлять вручную
3. **Структурированные данные** - легко парсить и фильтровать
4. **Визуализация в браузере** - автоматическое отображение в Debug Panel
5. **Фильтрация** - по типу, уровню, категории
6. **Экспорт** - возможность сохранить логи в JSON

## Примеры использования

### Мониторинг аудио обработки

```python
await nats_logger.log_info(
    "Audio chunk received",
    category="audio",
    chunk_size=4096,
    sample_rate=48000,
    channels=1
)
```

### Отслеживание ошибок

```python
try:
    result = await process_data()
except Exception as e:
    await nats_logger.log_error(
        f"Processing failed: {str(e)}",
        category="system",
        exception_type=type(e).__name__,
        traceback=traceback.format_exc()
    )
```

### Метрики производительности

```python
start = time.time()
result = await heavy_operation()
duration = time.time() - start

await nats_logger.log_info(
    f"Operation completed in {duration:.2f}s",
    category="system",
    operation="heavy_operation",
    duration=duration,
    result_size=len(result)
)
```

## Debug Panel

Все логи автоматически отображаются в Debug Panel браузера:

- **Фильтры** - выберите интересующие категории и уровни
- **Поиск** - найдите нужные сообщения
- **Экспорт** - сохраните логи для анализа
- **Очистка** - очистите панель от старых логов

### Специальное форматирование

Для логов транскрипции Debug Panel автоматически форматирует вывод:

```
[10:30:45] [INFO] [whisper] Transcription STARTED | audio: 3.45s | size: 323.4KB
[10:30:46] [INFO] [whisper] Transcription COMPLETED | audio: 3.45s | time: 1.23s | RTF: 0.36x | segments: 2 | 10:30:45 -> 10:30:46 | text: "Hello world from whisper..."
```

## Troubleshooting

### Логи не отображаются в браузере

1. Проверьте, что NATS клиент подключен: `nc.is_connected`
2. Убедитесь, что backend подписан на ваш subject
3. Проверьте фильтры в Debug Panel - возможно категория отключена

### Ошибка "NATS not connected"

```python
# Проверить подключение перед использованием
if nc and nc.is_connected:
    await nats_logger.log_info("Message")
else:
    print("NATS disconnected, skipping log")
```

### Логи не попадают в NATS

- Убедитесь, что используется `await` перед вызовами логгера
- Проверьте, что event loop запущен (не используйте в синхронном коде)
