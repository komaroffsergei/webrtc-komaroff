# Whisper Service - Модульная Архитектура

## Обзор

Рефакторинг с разделением на независимые модули (ноды), которые общаются через callback.

## Структурная схема

```
┌─────────────────┐
│  NATS Receiver  │  Получение аудио фреймов из NATS
└────────┬────────┘
         │ callback: {"audio": bytes, "meta": dict}
         ▼
┌─────────────────┐
│ Phrase Segmenter│  Нарезка на фразы по тишине
└────────┬────────┘
         │ callback: PhraseSegment (на каждую фразу)
         ▼
┌─────────────────┐
│   File Saver    │  Сохранение в WAV (асинхронно)
└────────┬────────┘
         │ callback: PhraseSegment (прокидывает дальше)
         ▼
┌─────────────────┐
│Whisper Transcrib│  Распознавание речи
└────────┬────────┘
         │ callback: {"text": str, "segments": list, "phrase": PhraseSegment}
         ▼
┌─────────────────┐
│Command Processor│  Анализ команд и отправка в NATS
└─────────────────┘
```

## Модули (Ноды)

### 1. BaseNode (nodes/base_node.py)

Базовый класс для всех нод.

**Методы:**
- `set_callback(callback)` - установить callback для передачи данных
- `emit(data)` - отправить данные в callback
- `start()` - запустить ноду (абстрактный)
- `stop()` - остановить ноду (абстрактный)
- `process(data)` - обработать входные данные (опционально)

**Принцип:**
- Каждая нода делает одну задачу
- Результат передается через async callback
- Независимость от других нод

### 2. NatsReceiverNode (nodes/nats_receiver_node.py)

**Задача:** Получение аудио фреймов из NATS

**Вход:** NATS messages (audio.frames)

**Выход:** `{"audio": bytes, "meta": dict}`

**Параметры:**
- `nats_url` - URL NATS сервера
- `subject` - subject для подписки

**Особенности:**
- Подключается к NATS при start()
- Декодирует payload (4 bytes length + JSON meta + audio)
- Автоматический reconnect

### 3. PhraseSegmenterNode (nodes/phrase_segmenter_node.py)

**Задача:** Нарезка аудио на фразы по тишине

**Вход:** `{"audio": bytes, "meta": dict}`

**Выход:** `PhraseSegment` (на каждую фразу через callback)

**Параметры:**
- `silence_threshold` - порог тишины (0.02)
- `min_silence_duration` - минимальная пауза для конца фразы (0.3с)
- `min_phrase_duration` - минимальная длительность фразы (0.5с)
- `padding_duration` - отступ до/после фразы (0.1с)
- `check_interval` - частота проверки окончания (0.5с)
- `max_buffer_duration` - максимальный буфер (60с)

**Алгоритм:**
1. Накапливает аудио фреймы в буфере
2. Каждые 0.5с проверяет энергию в конце буфера
3. Если тишина >= 0.3с → фраза закончена
4. Детектирует сегменты речи в буфере
5. Отправляет каждый сегмент через callback
6. Очищает буфер

**Особенности:**
- Фоновая задача для проверки окончания
- VAD детекция сегментов речи
- Защита от переполнения буфера

### 4. FileSaverNode (nodes/file_saver_node.py)

**Задача:** Сохранение фраз в WAV файлы

**Вход:** `PhraseSegment`

**Выход:** `PhraseSegment` (прокидывает дальше)

**Параметры:**
- `recordings_dir` - директория для записей
- `enabled` - включить/выключить сохранение

**Особенности:**
- Асинхронное сохранение через executor
- Автоматическая нумерация файлов
- Формат: `phrase_YYYYMMDD_HHMMSS_0001.wav`
- Не блокирует pipeline при сохранении
- Можно отключить через `enabled=False`

### 5. WhisperTranscriberNode (nodes/whisper_transcriber_node.py)

**Задача:** Распознавание речи через faster-whisper

**Вход:** `PhraseSegment`

**Выход:** `{"text": str, "segments": list, "phrase": PhraseSegment}`

**Параметры:**
- `model_path` - путь к CTranslate2 модели
- `device` - 'cpu' или 'cuda'
- `compute_type` - 'int8', 'float16', 'float32'
- `language` - язык распознавания ('ru')

**Особенности:**
- Загрузка модели в executor (не блокирует)
- Автоматический resample 48kHz → 16kHz
- VAD фильтр встроен в Whisper
- Транскрипция в executor (не блокирует event loop)

## Типы данных

### PhraseSegment

```python
@dataclass
class PhraseSegment:
    audio: np.ndarray       # float32, normalized [-1, 1]
    sample_rate: int        # частота дискретизации
    start_time: float       # время начала (сек)
    end_time: float         # время конца (сек)
    duration: float         # длительность (сек)
```

## Главный файл (main_refactored.py)

### Инициализация

```python
# Создание нод
nats_receiver = NatsReceiverNode(...)
phrase_segmenter = PhraseSegmenterNode(...)
file_saver = FileSaverNode(...)
whisper_transcriber = WhisperTranscriberNode(...)

# Настройка callback цепочки
nats_receiver.set_callback(phrase_segmenter.process)
phrase_segmenter.set_callback(file_saver.process)
file_saver.set_callback(whisper_transcriber.process)
whisper_transcriber.set_callback(on_transcription)

# Запуск
await phrase_segmenter.start()
await file_saver.start()
await whisper_transcriber.start()
await nats_receiver.start()
```

### Обработка результатов

```python
async def on_transcription(result: dict):
    text = result["text"]
    
    # Отправка транскрипции в NATS
    await nc.publish(WHISPER_SUBJECT, ...)
    
    # Проверка команд
    command_result = await command_matcher.process_transcription(text)
    if command_result:
        await nc.publish(WHISPER_SUBJECT, ...)
```

## Преимущества модульной архитектуры

### 1. Независимость модулей
- Каждая нода в отдельном файле
- Четкие интерфейсы (вход/выход)
- Легко тестировать отдельно

### 2. Гибкость
- Можно отключить любую ноду (например, File Saver)
- Можно заменить реализацию (например, другую VAD)
- Можно добавить новые ноды в pipeline

### 3. Масштабируемость
- Ноды можно распараллелить
- Легко добавить очереди между нодами
- Можно вынести ноды в отдельные процессы

### 4. Отладка
- Легко логировать каждую ноду отдельно
- Видно что происходит на каждом этапе
- Можно перехватить данные между нодами

### 5. Повторное использование
- Ноды можно использовать в других проектах
- Стандартный интерфейс BaseNode
- Callback паттерн универсален

## Пример расширения

### Добавление новой ноды (например, фильтр шума)

```python
from nodes.base_node import BaseNode

class NoiseFilterNode(BaseNode):
    def __init__(self, filter_level: float = 0.5):
        super().__init__("noise_filter")
        self.filter_level = filter_level
    
    async def start(self):
        pass
    
    async def stop(self):
        pass
    
    async def process(self, phrase: PhraseSegment):
        # Фильтрация шума
        filtered_audio = self._filter_noise(phrase.audio)
        
        # Создаем новый сегмент
        filtered_phrase = PhraseSegment(
            audio=filtered_audio,
            sample_rate=phrase.sample_rate,
            start_time=phrase.start_time,
            end_time=phrase.end_time,
            duration=phrase.duration
        )
        
        # Передаем дальше
        await self.emit(filtered_phrase)

# Использование
noise_filter = NoiseFilterNode()
phrase_segmenter.set_callback(noise_filter.process)
noise_filter.set_callback(file_saver.process)
```

## Конфигурация

Все параметры через .env:

```bash
# NATS
NATS_URL=nats://localhost:4222
AUDIO_SUBJ=audio.frames
WHISPER_SUBJ=whisper.transcription

# Whisper
WHISPER_MODEL=models/whisper-medium-ru-fine-ct2

# Recording
SAVE_RECORDINGS=true
RECORDINGS_DIR=recordings

# VAD
VAD_SILENCE_THRESHOLD=0.02
VAD_MIN_SILENCE_DURATION=0.3
VAD_MIN_SPEECH_DURATION=0.5
VAD_PADDING_DURATION=0.1
VAD_CHECK_INTERVAL=0.5
MAX_BUFFER_DURATION=60.0
```

## Запуск

```bash
cd src_whisper
python main_refactored.py
```

## Логи

Каждая нода логирует свою работу:

```
[INFO] whisper.nodes.nats_receiver: Connected to NATS
[INFO] whisper.nodes.phrase_segmenter: Phrase ended (silence 0.35s): 2.3s
[INFO] whisper.nodes.file_saver: Saved: phrase_20240101_120530_0001.wav (2.3s)
[INFO] whisper.nodes.whisper_transcriber: Transcribing phrase (2.3s)
[INFO] whisper.nodes.whisper_transcriber: Transcription: 'привет как дела'
[INFO] whisper.main: Published transcription: 'привет как дела'
```

## Тестирование

Каждую ноду можно тестировать отдельно:

```python
import asyncio
from nodes import PhraseSegmenterNode

async def test_segmenter():
    segmenter = PhraseSegmenterNode()
    
    # Mock callback
    results = []
    async def on_phrase(phrase):
        results.append(phrase)
    
    segmenter.set_callback(on_phrase)
    await segmenter.start()
    
    # Подаем тестовые данные
    for frame in test_frames:
        await segmenter.process(frame)
    
    await asyncio.sleep(1)
    await segmenter.stop()
    
    print(f"Detected {len(results)} phrases")

asyncio.run(test_segmenter())
```
