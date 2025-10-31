# SSE Refactoring Summary

## Новые функции (Backend)

### src_back/server/handlers/sse.py

```python
# Специализированные функции отправки
async def sse_command(app, method: str, params=None, uid: str = None)
async def sse_message(app, text: str, descr: str = "send", uid: str = None, **extra)
async def sse_log(app, message: str, level: str = "info", category: str = "general", **extra)
async def sse_warning(app, descr: str, uid: str = None)
```

Все функции автоматически добавляют `timestamp` и `uid`.

## Структура сообщений

### Команды
```json
{"type": "command", "method": "alert", "params": {...}, "uid": "...", "timestamp": "..."}
```

### Сообщения
```json
{"type": "message", "descr": "send", "text": "...", "uid": "...", "timestamp": "..."}
```

### Логи
```json
{"type": "log", "level": "info", "category": "webrtc", "message": "...", "uid": "...", "timestamp": "..."}
```

Уровни: `debug`, `info`, `warning`, `error`
Категории: `system`, `webrtc`, `nats`, `audio`, `general`

### Предупреждения
```json
{"type": "warning", "descr": "mic_too_loud", "uid": "...", "timestamp": "..."}
```

## Интеграция логирования

### handle_offer.py
```python
await sse_log(app, "WebRTC: Connection established", level="info", category="webrtc")
```

### handle_track.py
```python
await sse_log(app, "Audio track processing started", level="info", category="audio")
await sse_log(app, f"NATS: Subscribed to {subject}", level="info", category="nats")
```

### audio_monitor.py
```python
await sse_warning(app, "mic_too_loud")
```

## Отладочная панель (Frontend)

### src_back/static/debug_panel.js

Автоматически логирует все SSE события с фильтрами:
- По типу: command, log, message, warning
- По уровню: debug, info, warning, error
- По категории: system, webrtc, nats, audio, general

### API
```javascript
window.DebugPanel.togglePanel()   // Свернуть/развернуть
window.DebugPanel.clearLogs()     // Очистить
window.DebugPanel.exportLogs()    // Экспорт в JSON
window.DebugPanel.getStats()      // Статистика
```

## Обратная совместимость

Старые функции работают через новые:
```python
send_command(app, 'alert', {})     → sse_command(app, 'alert', {})
send_text_message(app, 'text')     → sse_message(app, 'text', 'send')
```

## Использование

### Отправка команды
```python
from server.handlers.sse import sse_command
await sse_command(app, 'reload', {})
```

### Отправка лога
```python
from server.handlers.sse import sse_log
await sse_log(app, 'Connection established', level='info', category='webrtc')
```

### Отправка сообщения
```python
from server.handlers.sse import sse_message
await sse_message(app, 'Hello from server', descr='send')
```

### Отправка предупреждения
```python
from server.handlers.sse import sse_warning
await sse_warning(app, 'mic_too_loud')
```
