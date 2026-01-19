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
    "You are an MCP agent.\n\n"
    "Rules:\n"
    "- Keep responses concise.\n"
    "- Use tool_calls for any action that requires tools.\n"
    "- Never invent tool arguments or placeholder values.\n"
    "- If required parameters are missing, ask the user for them via ASK_USER_INPUT.\n"
    "- Do not include raw tool outputs in content; store them as artifacts.\n"
    "- Do not return JSON in content.\n"
    "- Do not repeat the same tool call with identical arguments after an error.\n"
    "- Follow tool parameter types strictly.\n\n"
    "Critical rules:\n"
    "- A final answer must be produced via display_result when tools are used.\n"
    "- If data is insufficient, either request missing data or finalize with available artifacts.\n"
)


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
