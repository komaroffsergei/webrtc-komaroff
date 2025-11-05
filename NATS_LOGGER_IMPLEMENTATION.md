# Реализация унифицированной системы логирования через NATS

## Обзор

Реализована унифицированная система логирования `NatsLogger`, которая позволяет любому сервису отправлять структурированные логи в NATS. Логи автоматически передаются на backend и отображаются в Debug Panel браузера с форматированием.

## Компоненты

### 1. NatsLogger (src_whisper/nats_logger.py)

Универсальный класс для отправки логов в NATS с поддержкой:

- **Базовые логи**: `log_debug()`, `log_info()`, `log_warning()`, `log_error()`
- **Транскрипция**: `log_transcription_start()`, `log_transcription()`
- **События**: `log_event()` для произвольных событий с дополнительными полями
- **Автоматические поля**: timestamp, service name, category, level

### 2. Интеграция в Whisper сервис (src_whisper/main.py)

Обновлен код транскрипции для использования NatsLogger:

- Логирование начала транскрипции с timestamp
- Логирование окончания с полными метриками
- Структурированные данные (audio_duration, transcription_time, RTF, segments, text)

### 3. Обновление Debug Panel (src_back/static/debug_panel.js)

Добавлено:

- Категория `whisper` в фильтры
- Специальное форматирование для логов транскрипции
- Поддержка структурированных данных из NatsLogger
- Отображение текста транскрипции, RTF, временных меток

### 4. Документация

- `src_whisper/NATS_LOGGER_USAGE.md` - полное руководство по использованию
- `src_whisper/example_nats_logger_usage.py` - примеры использования
- `AGENTS.md` - обновлена с информацией о NatsLogger

## Архитектура

```
┌─────────────────┐
│  Whisper Service│
│                 │
│  NatsLogger     │──┐
└─────────────────┘  │
                     │
┌─────────────────┐  │ NATS
│  Other Service  │  │ subject
│                 │  │ "service.logs"
│  NatsLogger     │──┤
└─────────────────┘  │
                     │
┌─────────────────┐  │
│  Backend        │◄─┘
│  handle_track.py│
│                 │
│  _whisper_logs  │
│  _cb()          │
└────────┬────────┘
         │ SSE
         │
┌────────▼────────┐
│  Browser        │
│                 │
│  Debug Panel    │
│  - Filtering    │
│  - Formatting   │
│  - Export       │
└─────────────────┘
```

## Формат сообщения

### Базовый лог

```json
{
    "type": "log",
    "level": "info",
    "category": "whisper",
    "message": "Operation completed",
    "service": "whisper",
    "timestamp": "2024-01-15T10:30:46.353Z"
}
```

### Лог транскрипции (начало)

```json
{
    "type": "log",
    "level": "info",
    "category": "whisper",
    "message": "Transcription started: audio_duration=3.45s bytes=331200",
    "service": "whisper",
    "timestamp": "2024-01-15T10:30:45.123Z",
    "audio_duration": 3.45,
    "audio_bytes": 331200,
    "start": "2024-01-15T10:30:45.123Z"
}
```

### Лог транскрипции (окончание)

```json
{
    "type": "log",
    "level": "info",
    "category": "whisper",
    "message": "Transcription completed: audio_duration=3.45s transcription_time=1.23s segments=2 start=2024-01-15T10:30:45.123Z end=2024-01-15T10:30:46.353Z",
    "service": "whisper",
    "timestamp": "2024-01-15T10:30:46.353Z",
    "audio_duration": 3.45,
    "transcription_time": 1.23,
    "segments": 2,
    "rtf": 0.36,
    "start": "2024-01-15T10:30:45.123Z",
    "end": "2024-01-15T10:30:46.353Z",
    "text": "Hello world from whisper"
}
```

## Отображение в Debug Panel

### Начало транскрипции
```
[10:30:45] [INFO] [whisper] Transcription STARTED | audio: 3.45s | size: 323.4KB
```

### Окончание транскрипции
```
[10:30:46] [INFO] [whisper] Transcription COMPLETED | audio: 3.45s | time: 1.23s | RTF: 0.36x | segments: 2 | 10:30:45 -> 10:30:46 | text: "Hello world from whisper"
```

## Использование

### В новом сервисе

```python
from nats_logger import NatsLogger

# Инициализация
nats_logger = NatsLogger(nc, "service.logs", "my_service")

# Использование
await nats_logger.log_info("Service started", category="system")
await nats_logger.log_error("Error occurred", category="system", error_code=500)
```

### Специализированные методы

```python
# Транскрипция
start_ts = await nats_logger.log_transcription_start(
    audio_duration=3.45,
    audio_bytes=331200
)

await nats_logger.log_transcription(
    text="Result",
    segments=2,
    audio_duration=3.45,
    transcription_time=1.23,
    start_timestamp=start_ts,
    end_timestamp=datetime.utcnow().isoformat() + "Z"
)

# События
await nats_logger.log_event(
    event_type="connection",
    message="Connected",
    category="webrtc",
    level="info",
    peer_id="abc123"
)
```

## Категории и уровни

### Категории (для фильтрации в Debug Panel)
- `system` - системные события
- `webrtc` - WebRTC соединения
- `nats` - события NATS
- `audio` - обработка аудио
- `whisper` - транскрипция
- `general` - прочие события

### Уровни логов
- `debug` - детальная информация
- `info` - информационные сообщения
- `warning` - предупреждения
- `error` - ошибки

## Преимущества

1. **Единый формат** - все сервисы используют одну структуру
2. **Автоматизация** - timestamp, service name добавляются автоматически
3. **Структурированность** - легко парсить и анализировать
4. **Визуализация** - автоматическое отображение в браузере
5. **Фильтрация** - по категориям, уровням, поиск
6. **Расширяемость** - легко добавлять новые типы событий
7. **Переиспользуемость** - один класс для всех сервисов

## Тестирование

```bash
# Проверка синтаксиса
python3 -m py_compile src_whisper/nats_logger.py
python3 -m py_compile src_whisper/main.py
node -c src_back/static/debug_panel.js

# Запуск примеров (требует запущенный NATS)
python3 src_whisper/example_nats_logger_usage.py
```

## Файлы изменений

### Новые файлы
- `src_whisper/nats_logger.py` - основной класс NatsLogger
- `src_whisper/NATS_LOGGER_USAGE.md` - документация
- `src_whisper/example_nats_logger_usage.py` - примеры использования
- `NATS_LOGGER_IMPLEMENTATION.md` - этот файл

### Измененные файлы
- `src_whisper/main.py` - интеграция NatsLogger, логирование транскрипции
- `src_back/static/debug_panel.js` - категория whisper, форматирование логов
- `AGENTS.md` - добавлена секция о NatsLogger

## Дальнейшее развитие

### Возможные улучшения

1. **Метрики** - специализированный метод для метрик производительности
2. **Трейсинг** - поддержка distributed tracing (trace_id, span_id)
3. **Батчинг** - группировка логов перед отправкой для снижения нагрузки
4. **Буферизация** - кеширование логов при недоступности NATS
5. **Конфигурация** - уровни логирования через ENV переменные
6. **Sampling** - отправка только части debug логов в production

### Интеграция с другими сервисами

Для добавления NatsLogger в новый сервис:

1. Скопировать `src_whisper/nats_logger.py` в сервис
2. Инициализировать с NATS клиентом
3. Добавить подписку на backend в `handle_track.py`
4. Использовать методы логирования

Подробнее см. `src_whisper/NATS_LOGGER_USAGE.md`
