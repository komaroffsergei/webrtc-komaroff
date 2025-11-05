# Best Practices - Whisper Service

## Структура проекта

### Модульная организация

```
src_whisper/
├── config.py              # Конфигурация сервиса
├── main.py                # Точка входа
├── nats_logger.py         # Логирование в NATS
├── nats_log_handler.py    # Python logging handler
├── utils/                 # Общие утилиты
├── nodes/                 # Узлы обработки
├── commands/              # Голосовые команды
└── voice_commands/        # Система команд
```

### Принципы

1. **Один модуль - одна ответственность**
   - Каждый файл отвечает за конкретную функциональность
   - Не смешивать логику разных уровней

2. **Переиспользование кода**
   - Общие функции в `utils/`
   - Базовые классы для наследования
   - Избегать дублирования

3. **Конфигурация**
   - Все настройки в `config.py`
   - Типизированные dataclass
   - Переменные окружения для деплоя

## Добавление новых компонентов

### Новая нода обработки

1. Создать файл в `nodes/`
2. Наследоваться от `BaseNode`
3. Реализовать `start()`, `stop()`, `process()`
4. Добавить в `nodes/__init__.py`

```python
from .base_node import BaseNode

class MyCustomNode(BaseNode):
    def __init__(self, param1: str, name: str = "my_custom"):
        super().__init__(name)
        self.param1 = param1
    
    async def start(self) -> None:
        self.logger.info("Starting custom node")
    
    async def stop(self) -> None:
        self.logger.info("Stopping custom node")
    
    async def process(self, data: dict) -> None:
        # Обработка данных
        result = self._transform(data)
        await self.emit(result)
```

### Новая голосовая команда

1. Создать файл в `commands/`
2. Определить паттерны распознавания
3. Создать async handler
4. Зарегистрировать в `main.py`

```python
PATTERNS = [
    r"моя команда\\s+(?P<arg>.+)",
]

async def my_command_handler(params: dict) -> dict:
    arg = params.get("arg", "")
    return {
        "type": "command",
        "method": "my_command",
        "params": {"arg": arg}
    }

def register_my_command(registry):
    registry.register(
        name="my_command",
        patterns=PATTERNS,
        handler=my_command_handler,
        priority=5
    )
```

### Новая утилита

1. Добавить функцию в `utils/audio_utils.py` или создать новый файл
2. Типизировать параметры и return
3. Добавить docstring
4. Экспортировать в `utils/__init__.py`

```python
def my_audio_function(audio: np.ndarray, param: int) -> np.ndarray:
    """
    Описание функции.
    
    Args:
        audio: входное аудио
        param: параметр обработки
    
    Returns:
        обработанное аудио
    """
    # Реализация
    return processed_audio
```

## Логирование

### Использование стандартного logging

```python
import logging

logger = logging.getLogger("whisper.mymodule")

logger.debug("Детальная информация")
logger.info("Общая информация")
logger.warning("Предупреждение")
logger.error("Ошибка")
```

### Использование NatsLogger

```python
from nats_logger import NatsLogger

nats_logger = NatsLogger(nc, "whisper.logs", service_name="myservice")

await nats_logger.log_info("Operation completed", category="system")
await nats_logger.log_error("Failed", category="audio", error_code=500)
```

## Конфигурация

### Добавление новых настроек

1. Добавить в `.env.example`
2. Обновить соответствующий dataclass в `config.py`
3. Добавить значение по умолчанию

```python
@dataclass
class MyConfig:
    my_param: str
    
    @classmethod
    def from_env(cls) -> "MyConfig":
        return cls(
            my_param=os.getenv("MY_PARAM", "default_value")
        )
```

## Тестирование

### Unit tests

```python
import pytest
from utils.audio_utils import resample_audio

def test_resample_audio():
    audio = np.zeros(48000, dtype=np.float32)
    resampled = resample_audio(audio, 48000, 16000)
    assert len(resampled) == 16000
```

### Integration tests

```python
import pytest
from nodes import PhraseSegmenterNode

@pytest.mark.asyncio
async def test_phrase_segmenter():
    node = PhraseSegmenterNode()
    await node.start()
    
    # Тест обработки
    result = await node.process(test_data)
    assert result is not None
    
    await node.stop()
```

## Обработка ошибок

### В нодах

```python
async def process(self, data: dict) -> None:
    try:
        # Обработка
        result = self._process_data(data)
        await self.emit(result)
    except Exception as e:
        self.logger.error(f"Processing error: {e}", exc_info=True)
        # Не падаем, продолжаем работу
```

### В main.py

```python
try:
    await node.start()
except Exception as e:
    log.error(f"Failed to start node: {e}")
    raise  # Критическая ошибка, останавливаем сервис
```

## Performance

### Асинхронность

- Используйте `asyncio.create_task()` для фоновых задач
- Блокирующие операции выполняйте в `executor`
- Не блокируйте event loop

```python
# Плохо
result = blocking_function()

# Хорошо
result = await asyncio.get_event_loop().run_in_executor(
    None,
    blocking_function
)
```

### Буферизация

- Используйте буферы для накопления данных
- Не обрабатывайте каждый фрейм отдельно
- Группируйте операции

### Ресурсы

- Освобождайте ресурсы в `stop()`
- Закрывайте соединения при завершении
- Очищайте большие буферы

## Deployment

### Docker

```dockerfile
FROM python:3.11-slim

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

CMD ["python", "main.py"]
```

### Environment Variables

Обязательные:
- `NATS_URL` - URL NATS сервера
- `WHISPER_MODEL` - путь к модели

Опциональные (есть defaults):
- `VAD_THRESHOLD` - порог VAD
- `SAVE_RECORDINGS` - сохранять ли записи
- `LOG_LEVEL` - уровень логирования

## Мониторинг

### Метрики

- Время транскрипции (RTF - Real Time Factor)
- Количество обработанных фраз
- Ошибки и warnings
- Использование памяти

### Логи

- Все события отправляются в NATS
- Доступны в Debug Panel
- Можно экспортировать для анализа

## Code Style

- **PEP 8** для Python кода
- **Type hints** для всех функций
- **Docstrings** для модулей, классов, функций
- **Комментарии** только где нужны
- **Константы** в верхнем регистре
- **Приватные методы** с префиксом `_`

## Git Workflow

1. Создать feature branch
2. Сделать изменения
3. Добавить тесты
4. Проверить линтером
5. Создать PR
6. Code review
7. Merge в main
