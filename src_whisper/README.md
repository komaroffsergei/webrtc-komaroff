# Whisper Transcription Service

Сервис распознавания речи с поддержкой голосовых команд.

## Возможности

- **Транскрипция речи** через faster-whisper (CTranslate2)
- **Сохранение WAV** для отладки в `recordings/`
- **Голосовые команды** с regex паттернами (поддержка >100 команд)
- **Буферизация аудио** из NATS с настраиваемыми интервалами
- **Автоматическая отправка** результатов в SSE

## Установка

```bash
cd src_whisper

# Создать виртуальное окружение
python3 -m venv .venv
source .venv/bin/activate

# Установить зависимости
pip install -r requirements.txt
```

## Структура

```
src_whisper/
├── main.py                    # Главный сервис
├── audio_buffer.py            # Буферизация аудио
├── whisper_processor.py       # Обработка через Whisper
├── recordings/                # WAV файлы для отладки
├── models/
│   └── whisper-medium-ru-fine-ct2/  # Модель CTranslate2
├── voice_commands/
│   ├── command_registry.py    # Реестр команд
│   └── command_matcher.py     # Сопоставление команд
└── commands/
    ├── alert_command.py       # Пример: команда alert
    └── example_commands.py    # Дополнительные команды
```

## Конфигурация

Переменные окружения (или `.env` файл):

```bash
# NATS
NATS_URL=nats://localhost:4222
AUDIO_SUBJ=audio.frames           # Входящий subject
WHISPER_SUBJ=whisper.transcription # Исходящий subject

# Whisper
WHISPER_MODEL=models/whisper-medium-ru-fine-ct2
LOG_LEVEL=INFO

# Буферизация
MIN_DURATION=1.0    # Минимум 1 секунда
MAX_DURATION=30.0   # Максимум 30 секунд
SAVE_RECORDINGS=true # Сохранять WAV для отладки

# VAD (Voice Activity Detection)
ENABLE_VAD=true                  # Включить детекцию голоса
VAD_SILENCE_THRESHOLD=0.02       # Порог тишины (0.0-1.0)
VAD_MIN_SILENCE_DURATION=0.3     # Минимальная пауза между фразами (сек)
VAD_MIN_SPEECH_DURATION=0.5      # Минимальная длительность фразы (сек)
VAD_PADDING_DURATION=0.1         # Отступ до/после речи (сек)

# Директории
RECORDINGS_DIR=recordings
```

### Настройка VAD

**VAD_SILENCE_THRESHOLD** (порог тишины):
- Значения: 0.0-1.0 (по умолчанию: 0.02)
- Меньше = более чувствительный к тихим звукам
- Больше = игнорирует тихие звуки как тишину
- Рекомендуется: 0.01-0.03 для нормальных условий

**VAD_MIN_SILENCE_DURATION** (минимальная пауза):
- Значения: секунды (по умолчанию: 0.3)
- Определяет минимальную паузу между фразами
- Меньше = разделяет речь на больше сегментов
- Больше = объединяет фразы с короткими паузами
- Рекомендуется: 0.2-0.5 секунд

**VAD_MIN_SPEECH_DURATION** (минимальная длительность фразы):
- Значения: секунды (по умолчанию: 0.5)
- Игнорирует очень короткие сегменты речи
- Помогает фильтровать шум и артефакты
- Рекомендуется: 0.3-1.0 секунд

**VAD_PADDING_DURATION** (отступ):
- Значения: секунды (по умолчанию: 0.1)
- Добавляет буфер до и после обнаруженной речи
- Предотвращает обрезание начала/конца слов
- Рекомендуется: 0.05-0.2 секунд

## Запуск

```bash
python main.py
```

## Голосовые команды

### Создание новой команды

1. Создайте файл `commands/my_command.py`:

```python
import logging
from typing import Dict, Any

logger = logging.getLogger("whisper.commands.my_command")

# Паттерны для распознавания
MY_PATTERNS = [
    r"выполни\s+действие\s+(?P<param>.+)",
    r"запусти\s+(?P<param>.+)",
]

async def my_handler(params: Dict[str, Any]) -> Dict[str, Any]:
    """Обработчик команды."""
    param = params.get("param", "").strip()
    
    logger.info(f"My command: {param}")
    
    return {
        "type": "command",
        "method": "my_method",
        "params": {
            "value": param
        }
    }

def register_my_command(registry):
    """Регистрация команды."""
    registry.register(
        name="my_command",
        patterns=MY_PATTERNS,
        handler=my_handler,
        description="Описание команды",
        priority=10
    )
```

2. Добавьте импорт в `main.py`:

```python
from commands.my_command import register_my_command

# В функции main():
register_my_command(command_registry)
```

### Встроенные команды

#### Alert
Показать alert с сообщением:
```
"Выведи сообщение привет мир"
"Покажи сообщение тестовое уведомление"
```

Результат:
```json
{
    "type": "command",
    "method": "alert",
    "params": {
        "msg": "привет мир"
    }
}
```

#### Reload
Перезагрузить страницу:
```
"Перезагрузи страницу"
"Обнови страницу"
```

#### Help
Показать справку:
```
"Помощь"
"Справка"
"Что ты умеешь"
```

#### Status
Показать статус:
```
"Статус"
"Как дела"
```

## Протокол NATS

### Входящие сообщения (audio.frames)

```
[4 bytes: meta_len][meta_json][audio_bytes]
```

Метаданные:
```json
{
    "sample_rate": 48000,
    "channels": 1,
    "format": "s16p",
    "samples": 960
}
```

### Исходящие сообщения (whisper.transcription)

#### Транскрипция
```json
{
    "type": "transcription",
    "text": "распознанный текст",
    "segments": 3
}
```

#### Команда
```json
{
    "type": "command",
    "method": "alert",
    "params": {
        "msg": "текст сообщения"
    }
}
```

## Отладка

### Проверка WAV записей

WAV файлы сохраняются в `recordings/`:
```
recording_20240101_120000_150frames.wav
```

Воспроизведение:
```bash
ffplay recordings/recording_*.wav
```

### Тестирование команд

```python
import asyncio
from voice_commands import CommandRegistry
from commands.alert_command import register_alert_command

async def test():
    registry = CommandRegistry()
    register_alert_command(registry)
    
    # Тест распознавания
    result = registry.match("выведи сообщение тест")
    print(result)  # ('alert', {'message': 'тест'})
    
    # Выполнение команды
    if result:
        cmd, params = result
        output = await registry.execute(cmd, params)
        print(output)

asyncio.run(test())
```

## Масштабирование

Для поддержки >100 команд:

1. **Группировка по категориям:**
```
commands/
├── navigation/     # Навигационные команды
├── controls/       # Управление элементами
├── system/         # Системные команды
└── custom/         # Пользовательские команды
```

2. **Динамическая загрузка:**
```python
from pathlib import Path
import importlib

def load_all_commands(registry):
    commands_dir = Path("commands")
    for file in commands_dir.glob("**/*_command.py"):
        module_name = file.stem
        module = importlib.import_module(f"commands.{module_name}")
        register_func = getattr(module, f"register_{module_name}")
        register_func(registry)
```

3. **Приоритеты:**
- Высокий (10-20): Критичные команды
- Средний (5-9): Обычные команды
- Низкий (1-4): Редкие команды

## Производительность

- **Whisper medium**: ~2-5 секунд на транскрипцию (CPU)
- **Буферизация**: до 30 секунд аудио
- **Память**: ~2GB для модели + буферы

Оптимизация:
- Используйте GPU: `device="cuda"`
- Уменьшите модель: `whisper-small` или `whisper-base`
- Настройте `compute_type`: `int8` (быстрее) или `float16` (точнее)

## Troubleshooting

**Модель не загружается:**
```bash
ls -la models/whisper-medium-ru-fine-ct2/
# Проверьте наличие model.bin, config.json
```

**Нет транскрипции:**
- Проверьте WAV файлы в `recordings/`
- Увеличьте `MIN_DURATION`
- Проверьте уровень звука

**Команды не срабатывают:**
- Проверьте паттерны: `registry.match("ваш текст")`
- Увеличьте `priority` команды
- Проверьте логи: `LOG_LEVEL=DEBUG`
