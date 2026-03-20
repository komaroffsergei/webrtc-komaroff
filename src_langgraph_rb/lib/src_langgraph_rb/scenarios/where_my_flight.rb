# frozen_string_literal: true

module SrcLanggraphRb
  module Scenarios
    module WhereMyFlight
      # Делаем методы модуля доступными как module-level functions,
      # чтобы сценарий можно было зарегистрировать без создания объекта.
      module_function

      # Имя tool'а, который реально ходит за статусом рейса.
      TOOL_NAME = "get_flight_status"

      # Инструкция для LLM в режиме tool_params:
      # модель должна извлечь номер рейса или фамилию пассажира
      # и, если данных не хватает, вернуть missing + текст уточнения.
      TOOL_PARAMS_TASK = "Определи параметры для поиска статуса рейса.\n" \
                         "Если параметров не хватает, верни missing и задай пользователю уточняющий вопрос на русском.\n" \
                         "Если параметр распознан как номер рейса, нормализуй его (удали пробелы внутри номера)."

      # Инструкция для LLM после успешного вызова tool'а:
      # из tool result надо собрать короткий человекочитаемый ответ.
      FINAL_TASK = "Сформируй понятный ответ пользователю по результату поиска рейса.\n" \
                   "Пиши по-русски."

      # Краткий контекст сценария, который передается в final_response,
      # чтобы модель понимала, какую задачу сейчас решает.
      SCENARIO_CONTEXT = "Пользователь хочет узнать статус рейса.\n" \
                         "Ответ должен быть кратким и на русском языке."

      # Дефолтный текст, который показываем пользователю,
      # если LLM не смогла сама нормально сформулировать уточняющий вопрос.
      ASK_INPUT_DEFAULT = "Укажите номер рейса (например, SU123) или фамилию пассажира."

      # JSON-подобная схема параметров для режима tool_params.
      # По ней LLM понимает, какие поля вообще допустимы.
      TOOL_SCHEMA = {
        parameters: {
          # Номер рейса, например SU123.
          flight_number: { type: "string", description: "Номер рейса, например SU123" },
          # Фамилия пассажира как альтернативный способ поиска.
          last_name: { type: "string", description: "Фамилия пассажира" }
        }
      }.freeze

      # Регулярка для второго сообщения в pending-сценарии.
      # Если пользователь отвечает чем-то похожим на номер рейса или фамилию,
      # считаем это продолжением текущего сценария, а не новой задачей.
      FOLLOWUP_RE = /\b(рейс|flight|номер|фамил|пассажир|su\d|[A-Za-zА-Яа-яЁё]{2,3}\s?\d{1,4})\b/i

      # Регистрирует сценарий в builder/catalog.
      # Весь блок ниже — декларативное описание графа.
      def register(builder)
        # Глобальный id сценария.
        # По нему router и runtime находят именно этот workflow.
        builder.scenario("where_my_flight@2.0.0") do
          # Человекочитаемое название сценария.
          title "Where My Flight"

          # Короткое описание для разработчика и документации.
          description "Collect flight lookup params and shape the follow-up response"

          # Текст для router'а:
          # именно его LLM видит при выборе подходящего сценария.
          routing_description "Найти статус рейса по номеру рейса или фамилии пассажира"

          # Теги для организационных целей.
          tags :flight, :lookup

          # Декларация возможностей сценария:
          # pending_params — умеет входить в режим ожидания доп. данных,
          # tool_params — умеет извлекать аргументы через LLM,
          # tool_call — умеет вызывать tool,
          # handoff — умеет reroute'иться в другой сценарий.
          capabilities :pending_params, :tool_params, :tool_call, :handoff

          # Один раз объявляем tool profile.
          # Дальше graph-узлы будут ссылаться на него по alias `:flight_lookup`
          # и не будут вручную повторять tool_name, prompts, schema и fallback'и.
          tool_profile :flight_lookup,
            tool_name: TOOL_NAME,
            params_task: TOOL_PARAMS_TASK,
            final_task: FINAL_TASK,
            tool_schema: TOOL_SCHEMA,
            ask_input_default: ASK_INPUT_DEFAULT,
            scenario_context: SCENARIO_CONTEXT,
            not_found_message: "Статус рейса не найден.",
            failure_message: "Не удалось получить статус рейса.",
            fallback_formatter: :flight_status

          # Описание графа исполнения сценария.
          graph do
            # Подключаем оба стандартных хвоста сразу:
            # `final` для SHOW_MESSAGE и `terminal` для возврата уже собранного response.
            use_default_tails

            # Стартовый узел графа.
            # Сначала всегда пытаемся собрать параметры поиска.
            entry_point :collect_params

            # Семантический helper:
            # под капотом он все еще опускается в compute-op collect_tool_params_with_pending,
            # но автору сценария больше не нужно держать в голове op, tool_name, schema
            # и внутренние state key names.
            pending_tool_params :collect_params,
              profile: :flight_lookup,
              ready_if_any_present: %i[flight_number last_name],
              pending_missing: ["flight_number_or_last_name"],
              followup_pattern: FOLLOWUP_RE

            # Узел формирует PARTIAL-ответ:
            # prompt и pending payload берутся автоматически из результата collect_params.
            ask_user_input :ask_missing, from: :collect_params

            # Узел вызывает tool и затем просит LLM сформулировать итоговый ответ.
            tool_lookup_response :call_status_tool,
              profile: :flight_lookup,
              args_source: params_of(:collect_params)

            # Узел для мягкого завершения, когда рейс не найден:
            # это не runtime error, а обычный DONE с сообщением.
            done :tool_not_found

            # Узел для жесткой ошибки tool'а:
            # формирует FAILED-ответ.
            failed :tool_failed

            # Узел для handoff в другой сценарий,
            # если пользователь после pending начал говорить уже о другой задаче.
            reroute_scenario :reroute

            # После collect_params читаем auto-generated status key
            # и выбираем следующую ветку графа.
            route_status :collect_params, {
              # Параметров уже достаточно — можно идти в tool lookup.
              "ready" => :call_status_tool,
              # Параметров не хватает — спрашиваем пользователя.
              "missing" => :ask_missing,
              # Пользователь ушел в другую тему — делаем reroute.
              "reroute" => :reroute
            }

            # После partial_response сразу возвращаем уже собранный response наружу.
            edge :ask_missing, terminal

            # После tool lookup читаем auto-generated status key
            # и выбираем правильную ветку завершения.
            route_status :call_status_tool, {
              # Успех — формируем обычный финальный ответ.
              "done" => final,
              # Рейс не найден — тоже обычное завершение, но с отдельным текстом.
              "not_found" => :tool_not_found,
              # Ошибка tool'а — идем в FAILED.
              "failed" => :tool_failed
            }

            # Все три узла ниже уже сформировали response в state,
            # поэтому остается только дойти до terminal tail.
            finish_with_state :tool_not_found, :tool_failed, :reroute
          end
        end
      end
    end
  end
end
