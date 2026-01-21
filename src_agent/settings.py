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
    "Ты выбираешь ОДИН сценарий для обработки запроса пользователя.\n\n"
    "Учитывай КОНТЕКСТ ДИАЛОГА (все сообщения), а не только последнее.\n\n"
    "Вызывай select_scenario только если запрос явно относится к специализированному сценарию.\n"
    "Разрешён только один инструмент: select_scenario. Любые другие tool calls запрещены.\n\n"
    "Формат tool-call (строго):\n"
    "<tool_call>{\"name\":\"select_scenario\",\"arguments\":{\"scenario_id\":\"...\",\"reason\":\"...\"}}</tool_call>\n\n"
    "КРИТИЧЕСКИЕ ПРАВИЛА:\n\n"
    "1) flight_status выбирай ТОЛЬКО если запрос явно про авиацию.\n"
    "   Признаки авиации (хотя бы один):\n"
    "   - слова: рейс, полёт/полет, самолет/самолёт, авиакомпания, вылет, прилёт/прилет, посадка, гейт, терминал, boarding, flight, статус рейса\n"
    "   - или пользователь указал номер рейса (комбинация букв+цифр или просто типичный flight-id)\n"
    "   - или пользователь сообщает фамилию В КОНТЕКСТЕ поиска рейса/статуса рейса\n"
    "   Запрещено выбирать flight_status только по фразам «где мой …», «найди мой …» без признаков авиации.\n\n"
    "2) nearest_airports выбирай, если пользователь просит:\n"
    "   - ближайший/самый удалённый аэропорт (по расстоянию от меня)\n"
    "   - аэропорт рядом со мной\n"
    "   - построить маршрут до аэропорта в контексте выбора по расстоянию\n\n"
    "3) airports_clarify выбирай ТОЛЬКО если пользователь ищет конкретный аэропорт по названию/коду.\n"
    "   Запрещено выбирать airports_clarify для «ближайший/самый удалённый».\n\n"
    "4) Короткие ответы (одно слово/код/число) считай продолжением текущего сценария, если контекст на него указывает.\n\n"
    "ПРИМЕРЫ:\n"
    "- «Найди самый удаленный аэропорт» -> nearest_airports\n"
    "- «Найди ближайший ко мне аэропорт и построй маршрут до него» -> nearest_airports\n"
    "- «Аэропорты в радиусе 100 км» -> nearest_airports\n"
    "- «Покажи аэропорты» -> airports_clarify\n"
    "- «Найди аэропорт Шереметьево» -> search_airports_by_name_or_code\n"
    "- «Построй маршрут от Жуковского до SVO» -> route_builder\n"
    "- «Где мой рейс SU123» -> flight_status\n\n"
    "Если запрос не подходит ни под один специализированный сценарий:\n"
    "- НЕ выбирай специализированный сценарий\n"
    "- НЕ вызывай select_scenario\n"
    "- оставь ответ без tool calls, чтобы агент использовал сценарий chitchat (болтовня) по умолчанию.\n\n"
    "Запрещено:\n"
    "- рассматривать сообщения изолированно\n"
    "- выбирать специализированный сценарий по общим фразам без предметных признаков\n"
    # "- ПРАВИЛА:\n\n"
    # "- Не выводи цепочку рассуждений.\n\n"
    # "- Никогда не печатай <think>/</think>.\n\n"
    # "- Отвечай только итогом.\n\n"
)

PARAMS_SYSTEM_PROMPT_TEMPLATE = (
    "Ты извлекаешь параметры для сценария.\n"
    "Сценарий: {scenario_id}\n"
    "Инструкции (обязательные):\n"
    "{llm_prompt}\n"
	    "Правила:\n"
	    "- Если ты можешь извлечь значения, выведи РОВНО один вызов инструмента: "
	    "<tool_call>{{\"name\":\"extract_params\",\"arguments\":{{...}}}}</tool_call>\n"
	    "- Если ты не можешь извлечь значения с уверенностью, не вызывай инструменты и верни пустой ответ.\n"
	    "- Никогда не выдумывай значения.\n"
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
    "(например, «аэропорты в радиусе 100 км», «ближайший аэропорт», «самый дальний аэропорт»)."
)

NEAREST_AIRPORTS_SUMMARY_TEMPLATE = "Найдено аэропортов в радиусе {radius_km} км: {count}."
FLIGHTS_BETWEEN_TIMES_UNAVAILABLE_TEMPLATE = (
    "Поиск рейсов по времени пока недоступен. Запрошенное окно: {start}-{end}."
)

TOOL_ASK_USER_INPUT_DESCRIPTION = "Запрашивает у пользователя недостающий ввод."
TOOL_ASK_USER_INPUT_MESSAGE_PARAM = "Текст подсказки, отображаемой пользователю."
TOOL_FLIGHT_STATUS_DESCRIPTION = "Fetches flight status by flight number or surname."
TOOL_FLIGHT_STATUS_FLIGHT_NUMBER_PARAM = "Flight number, for example SU100."
TOOL_FLIGHT_STATUS_SURNAME_PARAM = "Passenger surname, for example Ivanov."

SELECT_SCENARIO_TOOL_DESCRIPTION_TEMPLATE = (
    "Выбери лучший сценарий для обработки запроса пользователя. "
    "Если ничего не подходит, не вызывай этот инструмент. "
    "Доступные сценарии: {scenarios}"
)
SELECT_SCENARIO_TOOL_PARAM_SCENARIO_ID_DESC = "Идентификатор выбранного сценария."
SELECT_SCENARIO_TOOL_PARAM_REASON_DESC = "Краткая причина выбора."
EXTRACT_PARAMS_TOOL_DESCRIPTION = "Извлеки параметры запроса пользователя для выбранного сценария."
