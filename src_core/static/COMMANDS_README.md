# Command System Documentation

## Обзор

Система команд обеспечивает двустороннюю коммуникацию между сервером и клиентом через SSE (Server-Sent Events).

## Клиентская часть

### Отправка сообщений на сервер

```javascript
// Отправить текстовое сообщение
await window.CommandHandler.sendMessage('Привет, сервер!');
```

### Регистрация обработчиков команд

```javascript
// Простая команда
window.CommandHandler.register('greet', (params, uid) => {
    alert(`Hello, ${params.name}!`);
});

// Команда с асинхронной логикой
window.CommandHandler.register('fetch_data', async (params, uid) => {
    const response = await fetch(params.url);
    const data = await response.json();
    console.log('Data received:', data);
});

// Команда с обработкой ошибок
window.CommandHandler.register('risky_operation', (params, uid) => {
    try {
        // Ваша логика
        if (!params.required_field) {
            throw new Error('Missing required field');
        }
        console.log('Operation successful');
    } catch (error) {
        console.error('Operation failed:', error);
    }
});
```

### Встроенные команды

#### alert
Показать alert диалог:
```json
{"type": "command", "method": "alert", "params": {"msg": "Alert text"}}
```

#### console
Вывод в консоль браузера:
```json
{"type": "command", "method": "console", "params": "Debug info"}
```

#### reload
Перезагрузить страницу:
```json
{"type": "command", "method": "reload"}
```

#### redirect
Редирект на другой URL:
```json
{"type": "command", "method": "redirect", "params": {"url": "/other-page"}}
```

## Серверная часть

### Отправка команд клиенту

```python
from server.utils.command_sender import send_command, send_text_message

# В любом обработчике или процессоре
async def my_handler(request):
    # Отправить команду
    await send_command(request.app, 'alert', {'msg': 'Hello from server'})
    
    # Отправить текстовое сообщение в чат
    await send_text_message(request.app, 'Обработка завершена')
    
    return web.Response(text='OK')
```

### Отправка предупреждений

```python
from server.utils.sse import sse_broadcast

# Предупреждение об уровне звука
await sse_broadcast({
    "type": "warning",
    "descr": "mic_too_loud"
})
```

## Примеры интеграции

### Пример 1: Команда для изменения UI

Клиент:
```javascript
window.CommandHandler.register('set_theme', (params, uid) => {
    document.body.className = params.theme;
    console.log(`Theme changed to ${params.theme}`);
});
```

Сервер:
```python
await send_command(app, 'set_theme', {'theme': 'dark-mode'})
```

### Пример 2: Запрос данных от клиента

Клиент:
```javascript
window.CommandHandler.register('get_client_info', async (params, uid) => {
    const info = {
        userAgent: navigator.userAgent,
        screen: {
            width: window.screen.width,
            height: window.screen.height
        }
    };
    
    // Отправляем ответ обратно на сервер
    await fetch('/client-info', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({uid, info})
    });
});
```

Сервер:
```python
# Запрос информации
await send_command(app, 'get_client_info', {})

# Обработчик ответа
async def handle_client_info(request):
    data = await request.json()
    uid = data['uid']
    info = data['info']
    
    logger.info(f"Client info received: {info}")
    return web.Response(text='OK')
```

### Пример 3: Прогресс-бар для длительной операции

Клиент:
```javascript
window.CommandHandler.register('update_progress', (params, uid) => {
    const progressBar = document.getElementById('progress');
    progressBar.style.width = `${params.percent}%`;
    progressBar.textContent = `${params.percent}%`;
});
```

Сервер:
```python
async def long_operation(app):
    total_steps = 100
    
    for step in range(total_steps):
        # Выполняем работу
        await asyncio.sleep(0.1)
        
        # Обновляем прогресс
        percent = int((step + 1) / total_steps * 100)
        await send_command(app, 'update_progress', {'percent': percent})
    
    await send_text_message(app, 'Операция завершена!')
```

## Мониторинг аудио

### Типы предупреждений

- **mic_too_loud**: Амплитуда сигнала превышает 0.9 (риск клиппинга)
- **mic_too_quiet**: Амплитуда сигнала ниже 0.02 (слишком тихо)
- **mic_too_noise**: Высокий RMS при низкой амплитуде (фоновый шум)

### UI для предупреждений

Предупреждения отображаются автоматически через `WarningUI`:

```javascript
// Показать кастомное предупреждение
window.WarningUI.showWarning('Пользовательское предупреждение');

// Скрыть текущее предупреждение
window.WarningUI.hideWarning();
```

## Отладка

### Логирование команд

Все выполненные команды логируются в консоль браузера с префиксом `[CommandHandler]`.

### Проверка SSE соединения

```javascript
// В консоли браузера
console.log('SSE connected:', window.eventSource?.readyState === 1);
```

### Отладка на сервере

```python
import logging

logger = logging.getLogger("commands")
logger.setLevel(logging.DEBUG)

# Логировать все SSE сообщения
await sse_broadcast(message)
logger.debug(f"SSE broadcast: {message}")
```
