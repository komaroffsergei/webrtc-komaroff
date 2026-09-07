# Voice AI: один Python runtime и собственный WebRTC relay

Адрес https://voice.komaroff-dev.ru/. Демо подготовлено 7 сентября 2026.
Дата подготовки не является датой начала разработки исходной системы.

## Что работает реально

Браузер создаёт RTCPeerConnection с audio + DataChannel. HTTPS используется только
для config/SDP/status; сообщения сценария идут через настоящий DataChannel.
Собственный coturn на этой VPS принудительно используется как relay. SDP фильтруется
до публичного адреса VPS; TURN может обращаться только к этой же VPS, без произвольного
проксирования. Краткоживущие TURN credentials действуют 120 секунд. Медиа защищены DTLS/SRTP.

`portfolio.runtime.DemoRuntime` вызывает исходный `src_langgraph.engine.WorkflowEngine`.
Используются исходные dispatch, echo, free_speech, contracts и bounded conversation memory.
RuntimeIO заменён MockIO; отдельные NATS/LLM/ASR/TTS/Ruby процессы в демо не запускаются.
Это консолидация публичного сценария, а не исходная распределённая топология проекта.

ASR отдаёт фиксированную фразу только после приёма аудиокадров; это не транскрипция речи.
LLM router/response детерминированы. TTS заменён коротким синусоидальным тоном и текстом.
По команде «таймаут» мок задерживается, asyncio.wait_for отменяет граф через две секунды.
Сценарий echo проходит настоящий граф без LLM-вызова.

## Изоляция и ограничения

Два одновременных соединения, одно на подписанную cookie, до 90 секунд и 10 сообщений.
Текст до 280 символов, один audio stream и один DataChannel. Произвольные uploads,
внешние tools, API и запись аудио отключены. Сервер считает кадры и сразу отбрасывает их.
Контекст хранится только в памяти процесса, удаляется при завершении/таймауте/рестарте.
Сброс очищает контекст, сохраняя лимит сообщений и время текущей сессии.
Микрофон активируется только соответствующей кнопкой. Есть полноценный текстовый режим
без разрешения на микрофон; транспорт остаётся WebRTC.

## Code-map

| Функция | Экран/API | Модуль | Данные / проверка |
|---|---|---|---|
| Подключение | кнопка → config/offer | portfolio/server.py, исходный validate_sdp | SDP + короткая TURN auth; live ICE QA |
| Аудио | getUserMedia → RTCPeerConnection | receive_audio / MockTone | только счётчики, без записи; media byte/frame QA |
| Текст | DataChannel portfolio | handle_message → DemoRuntime | память одной сессии; runtime tests |
| Оркестрация | события LangGraph | src_langgraph.engine + scenarios | исходные trace/runtime contracts |
| Timeout/retry | «Таймаут LLM» | MockIO + wait_for | отмена графа; timeout then echo test |
| Завершение | DELETE session / 90 s | close + expiry | освобождение PC/track/tasks/memory |

Перед изменением проследить сигналинг, ICE, медиа, DataChannel, граф и ответ. После правки
обновить карту/схемы и проверить два соединения, таймаут, повтор и очистку. Рабочую и
демонстрационную архитектуру показывать раздельно.

## Сборка / эксплуатация

Dockerfile.portfolio: Python3.12 digest + полный requirements.lock. Сборка вне VPS.
Runtime 384 MiB / 0.8 CPU, coturn 96 MiB / 0.3 CPU, logs 3×5 MB.
Host networking нужен для ICE публичного интерфейса; HTTP привязан только к 127.0.0.1:18406.
Открыт TURN3478 UDP/TCP, relay ports 49160–49179 используются локальными peers этой VPS.
TURN quota 2 на пользователя / 8 всего, bandwidth 128000 B/s на сессию и 512000 B/s всего.
Healthcheck приложения проверяет процесс; фактическое прохождение медиа проверяется отдельно.
LangSmith tracing отключён. Секреты только в серверном .env, не в Git или образе.

Источники технических контрактов: https://aiortc.readthedocs.io/en/latest/api.html,
https://github.com/coturn/coturn/blob/master/README.turnserver.
