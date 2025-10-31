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

## Система команд

### Регистрация команд на клиенте

```javascript
// В любом JS файле после загрузки command_handler.js
window.CommandHandler.register('my_command', (params, uid) => {
    console.log('Executing my_command with params:', params);
    // Ваша логика
});
```

### Отправка команд с сервера

```python
from server.utils.command_sender import send_command, send_text_message

# Отправить команду
await send_command(app, 'alert', {'msg': 'Hello from server'})

# Отправить текстовое сообщение
await send_text_message(app, 'Сообщение от сервера')
```

### Протокол SSE сообщений

#### Команды
```json
{
    "type": "command",
    "method": "alert",
    "params": {"msg": "Alert text"},
    "uid": "uuid"
}
```

#### Сообщения
```json
{
    "type": "message",
    "descr": "send",
    "uid": "uuid",
    "text": "Текст сообщения"
}
```

#### Предупреждения
```json
{
    "type": "warning",
    "descr": "mic_too_loud",
    "uid": "uuid"
}
```

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

1. **Не использовать eval** - для безопасности избегайте команды `eval_js` в продакшене
2. **Валидация параметров** - всегда проверяйте входные данные на клиенте и сервере
3. **Обработка ошибок** - используйте try/catch в обработчиках команд
4. **Логирование** - логируйте выполнение команд для отладки
5. **Типизация** - используйте type hints в Python и JSDoc в JavaScript
6. **Cooldown для предупреждений** - не спамить одинаковыми предупреждениями

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
