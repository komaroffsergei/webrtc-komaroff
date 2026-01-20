import os
from dotenv import load_dotenv

# Load environment variables
current_dir = os.path.dirname(os.path.abspath(__file__))
env_file = os.path.join(current_dir, '.env')
load_dotenv(env_file)
USER_ID = os.getenv("USER_ID", "user123")

# NATS Configuration
NATS_URL = os.getenv("NATS_URL", "nats://localhost:4222")
NATS_EVENTS_SUBJECT = os.getenv("NATS_EVENTS_SUBJECT", "nats.events.")
NATS_AGENT_SUBJECT = os.getenv("NATS_AGENT_SUBJECT", "nats.agent.")
NATS_LLM_SUBJECT = os.getenv("NATS_LLM_SUBJECT", "nats.llm.")

# Agent settings
AGENT_MAX_STEPS = int(os.getenv("AGENT_MAX_STEPS", "10"))
STACK_SERVICE_NAME = os.getenv("STACK_SERVICE_NAME", "src_agent")
TIMEOUT_SECONDS = int(os.getenv("TIMEOUT_SECONDS", "600"))
MAX_STEPS = int(os.getenv("MAX_STEPS", "10"))

# Database configuration
POSTGRES_HOST = os.getenv("POSTGRES_HOST", "localhost")
POSTGRES_PORT = os.getenv("POSTGRES_PORT", "5432")
POSTGRES_DB = os.getenv("POSTGRES_DB", "mcp")
POSTGRES_USER = os.getenv("POSTGRES_USER", "mcp")
POSTGRES_PASSWORD = os.getenv("POSTGRES_PASSWORD", "mcp_pass")

DATABASE_URL = os.getenv(
    "DATABASE_URL",
    f"postgresql://{POSTGRES_USER}:{POSTGRES_PASSWORD}@{POSTGRES_HOST}:{POSTGRES_PORT}/{POSTGRES_DB}",
)

AIRPORTS_API_URL = os.getenv("AIRPORTS_API_URL", "http://127.0.0.1:8100/api/airports/search")
RUNWAYS_API_URL = os.getenv("RUNWAYS_API_URL", "http://127.0.0.1:8100/api/airports")
PILOT_API_URL = os.getenv("PILOT_API_URL", "http://127.0.0.1:8100/api/pilot/location")
ROUTES_API_URL = os.getenv("ROUTES_API_URL", "http://127.0.0.1:8100/api/routes/nearest")
WEATHER_API_URL = os.getenv("WEATHER_API_URL", "http://127.0.0.1:8100/api/weather")

SYSTEM_PROMPT = (
    "Ты — MCP агент.\n\n"
    "Правила:\n"
    "- Пиши кратко.\n"
    "- Любое действие через tool_calls.\n"
    "- Маршрутизация сценариев выполняется через select_scenario; не выбирай сценарии по строковым совпадениям.\n"
    "- Не выдумывай аргументы инструментов и значения-заглушки.\n"
    "- Если обязательных параметров не хватает, запрашивай их через ASK_USER_INPUT.\n"
    "- Не вставляй сырые результаты инструментов в content; сохраняй их как artifacts.\n"
    "- Не возвращай JSON в content.\n"
    "- Не повторяй тот же вызов с теми же аргументами после ошибки.\n"
    "- Строго соблюдай типы параметров инструментов.\n\n",
    "- Не выводи цепочку рассуждений.\n\n"
    "- Никогда не печатай <think>/</think>.\n\n"
    "- Отвечай только итогом.\n\n"
    "Критические правила:\n"
    "- Финальный ответ при использовании инструментов должен оформляться через display_result.\n"
    "- Если данных недостаточно, либо запроси недостающие данные, либо заверши с доступными artifacts.\n"
)

ROUTING_SYSTEM_PROMPT = (
    "Ты выбираешь сценарий. Вызови select_scenario, если подходит специализированный сценарий. "
    "Если пользователь спрашивает о статусе рейса или где его рейс, выбирай flight_status. "
    "Если пользователь спрашивает о рейсах между временами, выбирай flights_between_times. "
    "Если пользователь спрашивает о ближайших аэропортах/аэродромах или аэропортах в радиусе, выбирай nearest_airports. "
    "Если ничего не подходит, не вызывай инструмент и верни пустой content."
    # "- ПРАВИЛА:\n\n"
    # "- Не выводи цепочку рассуждений.\n\n"
    # "- Никогда не печатай <think>/</think>.\n\n"
    # "- Отвечай только итогом.\n\n"
)

PARAMS_SYSTEM_PROMPT_TEMPLATE = (
    "Ты извлекаешь параметры запроса для сценария.\n"
    "Сценарий: {scenario_id} — {title}. {description}\n"
    "Если можешь уверенно извлечь параметры, вызови инструмент extract_params и передай поля. "
    "Если не уверен, не вызывай инструмент и верни пустой content."
)

CHITCHAT_SYSTEM_PROMPT = (
    "Ты дружелюбный ассистент. Отвечай кратко на языке пользователя. "
    "Не включай блоки <think> и внутренние рассуждения."
)

CHITCHAT_FALLBACK_MESSAGE = "Спасибо за сообщение."

SCENARIO_CHITCHAT_TITLE = "Общий чат"
SCENARIO_CHITCHAT_DESC = "Общение без специализированных сценариев и инструментов."
SCENARIO_FLIGHT_STATUS_TITLE = "Статус рейса"
SCENARIO_FLIGHT_STATUS_DESC = "Проверяет статус рейса по номеру (например, «где мой рейс»)."
SCENARIO_FLIGHTS_BETWEEN_TIMES_TITLE = "Рейсы по времени"
SCENARIO_FLIGHTS_BETWEEN_TIMES_DESC = "Ищет рейсы в заданном временном окне (например, 12:00-16:00)."
SCENARIO_NEAREST_AIRPORTS_TITLE = "Ближайшие аэропорты"
SCENARIO_NEAREST_AIRPORTS_DESC = (
    "Ищет аэропорты или аэродромы в заданном радиусе от текущей позиции "
    "(например, «аэропорты в радиусе 100 км» или «ближайший аэродром»)."
)

NEAREST_AIRPORTS_SUMMARY_TEMPLATE = "Найдено аэропортов в радиусе {radius_km} км: {count}."
FLIGHTS_BETWEEN_TIMES_UNAVAILABLE_TEMPLATE = (
    "Поиск рейсов по времени пока недоступен. Запрошенное окно: {start}-{end}."
)

TOOL_ASK_USER_INPUT_DESCRIPTION = "Запрашивает у пользователя недостающий ввод."
TOOL_ASK_USER_INPUT_MESSAGE_PARAM = "Текст подсказки, отображаемой пользователю."
TOOL_FLIGHT_STATUS_DESCRIPTION = "Получает статус рейса по номеру."
TOOL_FLIGHT_STATUS_PARAM = "Номер рейса, например SU100."

SELECT_SCENARIO_TOOL_DESCRIPTION_TEMPLATE = (
    "Выбери лучший сценарий для обработки запроса пользователя. "
    "Если ничего не подходит, не вызывай этот инструмент. "
    "Доступные сценарии: {scenarios}"
)
SELECT_SCENARIO_TOOL_PARAM_SCENARIO_ID_DESC = "Идентификатор выбранного сценария."
SELECT_SCENARIO_TOOL_PARAM_REASON_DESC = "Краткая причина выбора."
EXTRACT_PARAMS_TOOL_DESCRIPTION = "Извлеки параметры запроса пользователя для выбранного сценария."


# SYSTEM_PROMPT = (
#     "Ты — MCP-агент, предназначенный для выполнения задач через вызов инструментов.\n\n"
#     "Правила работы:\n"
#     "- ВСЕГДА объясняй в поле `content` свои рассуждения: что ты делаешь и почему.\n"
#     "- ВСЕГДА используй `tool_calls` для вызова инструментов — НИКОГДА не вставляй вызов в `content`.\n"
#     "- НИКОГДА не возвращай JSON или структурированные данные в `content`.\n"
#     "- НИКОГДА не выдумывай значения, параметры или заглушки.\n"
#     "- НИКОГДА не запрашивай недостающие данные у пользователя — работай только с доступной информацией.\n"
#     "- НИКОГДА не повторяй вызов инструмента с теми же аргументами после ошибки.\n"
#     "- НИКОГДА не предполагай следующие шаги без явного результата предыдущего.\n"
#     "- ВСЕГДА строго соблюдай ожидаемые типы параметров инструментов.\n\n"
#     "КРИТИЧЕСКИЕ ТРЕБОВАНИЯ:\n"
#     "- Любой финальный результат ДОЛЖЕН быть передан через `tool_calls` с инструментом `display_result`.\n"
#     "- Если данных недостаточно:\n"
#     "  • либо вызови подходящий инструмент для их получения,\n"
#     "  • либо немедленно вызови `display_result` с имеющимися artifacts.\n"
#     "- Ты НЕ МОЖЕШЬ завершать взаимодействие текстовым ответом — только через `display_result`."
# )

#
# SYSTEM_PROMPT = (
#     "Ты — MCP-АГЕНТ, управляющий выполнением задач ЧЕРЕЗ ИНСТРУМЕНТЫ.\n\n"
#
#     "ГЛАВНОЕ ПРАВИЛО:\n"
#     "- ЕСЛИ ТРЕБУЕТСЯ ДЕЙСТВИЕ — ТЫ ОБЯЗАН ВЫЗВАТЬ ИНСТРУМЕНТ.\n"
#     "- ТЕКСТ БЕЗ ВЫЗОВА ИНСТРУМЕНТА ЗАПРЕЩЁН.\n\n"
#
#     "ФОРМАТ ОТВЕТА:\n"
#     "- При вызове инструмента `content` МОЖЕТ БЫТЬ ПУСТЫМ.\n"
#     "- Вызов инструмента ДОЛЖЕН быть оформлен ТОЛЬКО через `tool_calls`.\n"
#     "- НИКОГДА не вставляй JSON или аргументы инструментов в `content`.\n\n"
#
#     "ПРАВИЛА РАБОТЫ С ИНСТРУМЕНТАМИ:\n"
#     "- Используй ТОЛЬКО инструменты из предоставленного списка.\n"
#     "- Используй ТОЛЬКО те параметры, которые явно указаны в схеме.\n"
#     "- НЕ выдумывай параметры, значения или результаты.\n"
#     "- НЕ повторяй вызов инструмента с теми же аргументами после ошибки.\n"
#     "- НЕ запрашивай данные у пользователя.\n\n"
#
#     "ФИНАЛЬНЫЙ ОТВЕТ:\n"
#     "- Финальный шаг ВСЕГДА выполняется через инструмент `display_result`.\n"
#     "- После вызова `display_result` выполнение ЗАВЕРШАЕТСЯ.\n"
#     "- Текстовый финал запрещён.\n\n"
#
#     "АЛГОРИТМ:\n"
#     "1. Если данных недостаточно — вызови инструмент для их получения.\n"
#     "2. Если данные получены — выполни следующий необходимый инструмент.\n"
#     "3. Когда результат готов — вызови `display_result`.\n\n"
#
#     "НАРУШЕНИЕ ЛЮБОГО ПРАВИЛА ПРИВЕДЁТ К ОТКЛОНЕНИЮ ОТВЕТА."
# )
#
#

# SYSTEM_PROMPT = (
#     "ТЫ — MCP-АГЕНТ. СТРОГО СЛЕДУЙ ЭТИМ ПРАВИЛАМ:\n\n"
#     "1. КАЖДЫЙ ОТВЕТ ДОЛЖЕН СОДЕРЖАТЬ:\n"
#     "   - ТЕКСТОВОЕ РАССУЖДЕНИЕ НА РУССКОМ (ЧТО ДЕЛАЕШЬ И ПОЧЕМУ)\n"
#     "   - ВЫЗОВА ИНСТРУМЕНТА. ВСЕГДА используй `tool_calls` для вызова инструментов.\n"
#     "2. АБСОЛЮТНЫЕ ЗАПРЕТЫ:\n"
#     "   - НИКОГДА не придумывай названия/расстояния/значения\n"
#     "   - НИКОГДА не описывай данные из artifacts в `content`\n"
#     "   - НИКОГДА не оставляй `content` пустым\n"
#     "   - Пример ЗАПРЕЩЁННОГО ответа:\n"
#     "       content: 'Аэропорты: Воронеж 120 км, Курск 150 км'\n"
#     "   - Пример РАЗРЕШЁННОГО ответа:\n"
#     "       content: 'Данные о ближайших аэропортах получены'\n"
#     "       tool_calls: [display_result(artifact_key='selected_airports')]\n\n"
#     "3. АЛГОРИТМ:\n"
#     "   Шаг 1. Получил результат инструмента → НЕМЕДЛЕННО вызови `display_result`\n"
#     "   Шаг 2. В `content` ПОСЛЕ инструментов: только общая фраза без конкретики\n"
#     "   Шаг 3. При ошибке — прекрати работу, не повторяй вызовы\n\n"
#     "НАРУШЕНИЕ ЛЮБОГО ПРАВИЛА = АВТОМАТИЧЕСКИЙ ОТКАЗ СИСТЕМЫ."
# )
