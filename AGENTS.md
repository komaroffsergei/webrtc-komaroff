# Agent Development Guide

## Архитектура системы

### Backend (Python/aiohttp)
- `src_back/server/app.py` - главное приложение и роуты
- `src_back/server/handlers/` - обработчики HTTP запросов
- `src_back/server/processors/` - граф обработки аудио (нода-архитектура)
- `src_back/server/utils/` - утилиты (конфигурация, валидация, мониторинг)

### Frontend (Vanilla JS)
- `src_back/static/command_handler.js` - центральный обработчик команд
- `src_back/static/chat_ui.js` - UI для чата
- `src_back/static/warning_ui.js` - UI для предупреждений
- `src_back/static/assistant.js` - главный скрипт приложения

## Система SSE (Server-Sent Events)

### Специализированные функции отправки

```python
from server.handlers.sse import sse_command, sse_message, sse_log, sse_warning

# Отправить команду
await sse_command(app, 'alert', {'msg': 'Hello from server'})

# Отправить текстовое сообщение
await sse_message(app, 'Текст сообщения', descr='send')

# Отправить лог для отладочной панели
await sse_log(app, 'WebRTC connection established', level='info', category='webrtc')

# Отправить предупреждение
await sse_warning(app, 'mic_too_loud')
```

### Обратная совместимость

```python
from server.utils.command_sender import send_command, send_text_message

# Эти функции работают через новые sse_* функции
await send_command(app, 'alert', {'msg': 'Hello'})
await send_text_message(app, 'Сообщение')
```

## Система команд

### Регистрация команд на клиенте

```javascript
// В любом JS файле после загрузки command_handler.js
window.CommandHandler.register('my_command', (params, uid) => {
    console.log('Executing my_command with params:', params);
    // Ваша логика
});
```

### Протокол SSE сообщений

Все сообщения автоматически получают `timestamp` и `uid` если они не указаны.

#### Команды
```json
{
    "type": "command",
    "method": "alert",
    "params": {"msg": "Alert text"},
    "uid": "uuid",
    "timestamp": "2024-01-01T12:00:00Z"
}
```

#### Сообщения
```json
{
    "type": "message",
    "descr": "send",
    "uid": "uuid",
    "text": "Текст сообщения",
    "timestamp": "2024-01-01T12:00:00Z"
}
```

#### Предупреждения
```json
{
    "type": "warning",
    "descr": "mic_too_loud",
    "uid": "uuid",
    "timestamp": "2024-01-01T12:00:00Z"
}
```

#### Логи (для отладочной панели)
```json
{
    "type": "log",
    "level": "info",
    "category": "webrtc",
    "message": "Connection established",
    "uid": "uuid",
    "timestamp": "2024-01-01T12:00:00Z"
}
```

**Уровни логов:** `debug`, `info`, `warning`, `error`

**Категории логов:** `system`, `webrtc`, `nats`, `audio`, `general`

## Отладочная панель

### Использование на клиенте

```javascript
// Панель автоматически инициализируется при загрузке страницы
// Все SSE события автоматически логируются

// Программный доступ
window.DebugPanel.togglePanel();      // Свернуть/развернуть
window.DebugPanel.clearLogs();        // Очистить логи
window.DebugPanel.exportLogs();       // Экспортировать в JSON
window.DebugPanel.getStats();         // Получить статистику
```

### Фильтры

- **По типу:** command, log, message, warning
- **По уровню:** debug, info, warning, error
- **По категории:** system, webrtc, nats, audio, general

### Экспорт логов

Кнопка "Экспорт" сохраняет все логи в JSON файл для последующего анализа.

## Мониторинг аудио

### Типы предупреждений
- `mic_too_loud` - микрофон слишком громкий (клиппинг)
- `mic_too_quiet` - микрофон слишком тихий
- `mic_too_noise` - высокий уровень шума

### Настройка параметров

```python
from server.utils.audio_monitor import AudioMonitor

monitor = AudioMonitor(
    app,
    check_interval=2.0,        # интервал проверки в секундах
    loud_threshold=0.9,        # порог громкости (0.0-1.0)
    quiet_threshold=0.02,      # порог тишины (0.0-1.0)
    noise_threshold=0.15,      # порог шума по RMS
    min_frames_for_check=10    # минимум фреймов для анализа
)
```

## Добавление новых команд

### 1. Регистрация на клиенте

В `command_handler.js` или в отдельном модуле:

```javascript
window.CommandHandler.register('my_new_command', (params, uid) => {
    // Обработка команды
    const { arg1, arg2 } = params;
    console.log(`Command ${uid}: ${arg1}, ${arg2}`);
});
```

### 2. Отправка с сервера

```python
# В любом обработчике или процессоре
from server.utils.command_sender import send_command

await send_command(request.app, 'my_new_command', {
    'arg1': 'value1',
    'arg2': 'value2'
})
```

## Best Practices

1. **Использовать специализированные SSE функции** - `sse_command`, `sse_message`, `sse_log`, `sse_warning` вместо прямого `sse_broadcast`
2. **Категоризировать логи** - используйте правильные категории для удобной фильтрации
3. **Не использовать eval** - для безопасности избегайте команды `eval_js` в продакшене
4. **Валидация параметров** - всегда проверяйте входные данные на клиенте и сервере
5. **Обработка ошибок** - используйте try/catch в обработчиках команд
6. **Логирование критичных событий** - WebRTC подключения, NATS сообщения, ошибки
7. **Типизация** - используйте type hints в Python и JSDoc в JavaScript
8. **Cooldown для предупреждений** - не спамить одинаковыми предупреждениями
9. **Уровни логирования** - debug для детальной информации, info для обычных событий, warning/error для проблем

## Структура для масштабирования

При добавлении большого количества команд (>100):

1. Разделите команды по категориям в отдельные файлы:
   - `commands/audio_commands.js`
   - `commands/ui_commands.js`
   - `commands/system_commands.js`

2. Используйте префиксы для группировки:
   - `audio.start`, `audio.stop`, `audio.mute`
   - `ui.show_modal`, `ui.hide_modal`
   - `system.reload`, `system.log`

3. Создайте централизованный реестр команд с документацией
