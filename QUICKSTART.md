# Quick Start Guide

## Что реализовано

### 1. Мониторинг уровня звука
- Автоматическая детекция проблем с микрофоном
- Предупреждения в UI при слишком громком/тихом сигнале или шуме
- Интеграция в аудио-граф обработки

### 2. Обмен сообщениями
- `POST /message` - отправка сообщений от клиента
- `GET /events` (SSE) - получение сообщений от сервера
- Двусторонняя коммуникация с автогенерацией UID

### 3. Система команд
- Центральный обработчик команд на клиенте
- Регистрация кастомных команд
- Встроенные команды: alert, console, reload, redirect

## Запуск проекта

```bash
# Перейти в директорию backend
cd src_back

# Установить зависимости (если еще не установлены)
pip install -r requirements.txt

# Запустить сервер
python main.py
```

## Проверка функционала

### 1. Открыть приложение
```
http://localhost:8000/static/assistant.html
```

### 2. Тест обмена сообщениями

**В UI:**
1. Нажать кнопку микрофона (чат развернется)
2. Ввести текст в поле ввода
3. Нажать Enter
4. Сообщение появится в чате
5. Сервер отправит эхо-ответ

**Через curl:**
```bash
curl -X POST http://localhost:8000/message \
  -H "Content-Type: application/json" \
  -d '{"text": "Тестовое сообщение"}'
```

### 3. Тест предупреждений

**Автоматически:** При подключении микрофона система начнет мониторинг

**Вручную из Python:**
```python
from server.handlers.sse import sse_broadcast

await sse_broadcast(app, {
    "type": "warning",
    "descr": "mic_too_loud"
})
```

### 4. Тест команд

**Отправить команду с сервера:**
```python
from server.utils.command_sender import send_command

await send_command(app, 'alert', {'msg': 'Тестовое уведомление'})
```

**Зарегистрировать команду на клиенте:**
```javascript
// В консоли браузера
window.CommandHandler.register('test', (params, uid) => {
    console.log('Test command executed!', params);
});
```

## Мониторинг SSE событий

**В консоли браузера:**
```javascript
// Проверить состояние SSE
console.log('SSE connected:', window.eventSource?.readyState === 1);

// Логировать все события
const originalHandler = window.CommandHandler.handleServerMessage;
window.CommandHandler.handleServerMessage = function(msg) {
    console.log('[SSE Event]', msg);
    originalHandler.call(this, msg);
};
```

## Структура SSE сообщений

### Предупреждение о звуке
```json
{
    "type": "warning",
    "descr": "mic_too_loud"
}
```

### Текстовое сообщение
```json
{
    "type": "message",
    "descr": "send",
    "uid": "uuid-here",
    "text": "Текст сообщения"
}
```

### Команда
```json
{
    "type": "command",
    "method": "alert",
    "params": {"msg": "Alert text"},
    "uid": "uuid-here"
}
```

## Настройка аудио-мониторинга

В `src_back/server/handlers/handle_track.py`:

```python
audio_monitor = AudioMonitor(
    app,
    check_interval=2.0,        # Интервал проверки (сек)
    loud_threshold=0.9,        # Порог громкости (0-1)
    quiet_threshold=0.02,      # Порог тишины (0-1)
    noise_threshold=0.15,      # Порог шума
    min_frames_for_check=10    # Минимум фреймов для анализа
)
```

## Добавление кастомной команды

### На клиенте (JavaScript):
```javascript
window.CommandHandler.register('custom_action', (params, uid) => {
    // Ваша логика
    console.log('Custom action:', params);
});
```

### На сервере (Python):
```python
from server.utils.command_sender import send_command

async def my_handler(request):
    await send_command(request.app, 'custom_action', {
        'data': 'value'
    })
    return web.Response(text='OK')
```

## Отладка

### Логи сервера
```bash
# Включить debug-логи
export LOG_LEVEL=DEBUG
python main.py
```

### Логи клиента
```javascript
// В консоли браузера
localStorage.setItem('debug', 'true');
location.reload();
```

### Проверка SSE подключения
```bash
# Подключиться к SSE через curl
curl -N http://localhost:8000/events
```

## Известные ограничения

1. **Cooldown предупреждений:** Одинаковые предупреждения отправляются не чаще раз в 10 секунд
2. **SSE reconnect:** При разрыве соединения автоматическое переподключение через 3 секунды
3. **Буфер фреймов:** Хранятся последние 100 аудио-фреймов для анализа

## Следующие шаги

1. Изучите `AGENTS.md` для понимания архитектуры
2. Прочитайте `src_back/static/COMMANDS_README.md` для детальной документации API
3. См. `IMPLEMENTATION_SUMMARY.md` для технических деталей

## Полезные ссылки

- Основное приложение: `http://localhost:8000/static/assistant.html`
- SSE endpoint: `http://localhost:8000/events`
- Message endpoint: `POST http://localhost:8000/message`
- WebRTC endpoint: `POST http://localhost:8000/offer`

## Troubleshooting

**Проблема:** Предупреждения не появляются
- Проверьте, что микрофон подключен
- Проверьте пороги в AudioMonitor
- Проверьте SSE соединение

**Проблема:** Команды не выполняются
- Проверьте, что команда зарегистрирована через `CommandHandler.register`
- Проверьте консоль браузера на ошибки
- Проверьте, что SSE соединение активно

**Проблема:** Сообщения не отправляются
- Проверьте network tab в DevTools
- Убедитесь, что сервер запущен
- Проверьте формат JSON запроса
