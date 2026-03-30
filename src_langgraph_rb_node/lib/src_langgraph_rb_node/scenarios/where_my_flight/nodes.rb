# frozen_string_literal: true

module SrcLanggraphRbNode
  module Scenarios
    module WhereMyFlight
      # Набор нод для сценария поиска статуса рейса.
      # Основной поток здесь такой:
      # 1. Извлечь номер рейса или фамилию пассажира из запроса.
      # 2. Если данных мало, попросить пользователя уточнить запрос.
      # 3. Если пользователь ушел в другую тему, запустить reroute.
      # 4. Если данных достаточно, вызвать tool статуса рейса.
      # 5. Превратить tool-результат в финальный ответ.
      class Nodes < BaseNodes
        # Имя инструмента, который умеет искать статус рейса.
        TOOL_NAME = "get_flight_status"

        # Инструкция для LLM по извлечению параметров поиска.
        # Модель должна:
        # - вытащить номер рейса и/или фамилию,
        # - при нехватке данных вернуть missing и prompt,
        # - нормализовать номер рейса, если он распознан.
        TOOL_PARAMS_TASK = "Определи параметры для поиска статуса рейса.\n" \
                           "Если параметров не хватает, верни missing и задай пользователю уточняющий вопрос на русском.\n" \
                           "Если параметр распознан как номер рейса, нормализуй его (удали пробелы внутри номера)."

        # Инструкция для LLM по сборке финального ответа на основе tool-результата.
        FINAL_TASK = "Сформируй понятный ответ пользователю по результату поиска рейса.\n" \
                     "Пиши по-русски."

        # Сценарный контекст, который объясняет модели тип задачи и желаемый стиль ответа.
        SCENARIO_CONTEXT = "Пользователь хочет узнать статус рейса.\n" \
                           "Ответ должен быть кратким и на русском языке."

        # Резервный текст, который будет использован, если LLM не вернет свой prompt.
        ASK_INPUT_DEFAULT = "Укажите номер рейса (например, SU123) или фамилию пассажира."

        # Схема параметров для режима tool_params.
        TOOL_SCHEMA = {
          parameters: {
            flight_number: { type: "string", description: "Номер рейса, например SU123" },
            last_name: { type: "string", description: "Фамилия пассажира" }
          }
        }.freeze

        # Регулярное выражение для эвристического определения, что новый ответ пользователя
        # все еще относится к сценарию поиска рейса, а не к другому сценарию.
        FOLLOWUP_RE = /\b(рейс|flight|номер|фамил|пассажир|su\d|[A-Za-zА-Яа-яЁё]{2,3}\s?\d{1,4})\b/i

        # Извлекает параметры поиска рейса из текущего сообщения пользователя.
        # Метод также учитывает pending-состояние, если сценарий уже задавал уточняющий вопрос.
        def collect_params(state, await)
          # Сохраняем исходный req для доступа к тексту и pending-данным.
          req = state.fetch(:req)
          # Берем pending-состояние из runtime, если сценарий уже ждал уточнения.
          pending = Runtime::Util.extract_hash(req.dig(:runtime, :pending))
          # Отмечаем, был ли уже активен незавершенный шаг этого сценария.
          had_pending = !pending.empty?
          # Из pending извлекаем ранее распознанные параметры, чтобы не потерять их.
          previous = Runtime::Util.extract_hash(pending[:extracted])

          # Просим LLM выделить параметры инструмента из текущего пользовательского текста.
          params_resp = await.call(
            "collect_params",
            :llm,
            mode: "tool_params",
            input_data: {
              task: TOOL_PARAMS_TASK,
              user_message: req[:text],
              tool_name: TOOL_NAME,
              tool_schema: TOOL_SCHEMA,
              dialog_context: state[:dialog_context].to_s
            },
            constraints: { temperature: 0 }
          )

          # Нормализуем ответ LLM в структуру вида { extracted:, prompt: }.
          parsed = normalize_tool_params(params_resp)
          # Объединяем старые и новые параметры, не затирая полезные значения пустыми.
          merged = merge_non_empty_params(previous, parsed[:extracted])

          # Если после merge у нас есть хотя бы один пригодный идентификатор рейса, можно вызывать tool.
          if ready_with_any_field?(merged, %i[flight_number last_name])
            { collected_params: merged, collect_status: "ready" }
          else
            # Иначе пытаемся взять уточняющий prompt от модели.
            prompt = parsed[:prompt].to_s.strip
            # Если модель не вернула prompt, используем стабильный fallback.
            prompt = ASK_INPUT_DEFAULT if prompt.empty?

            # Собираем pending-state, который runtime сохранит между сообщениями.
            pending_state = {
              type: "tool_params",
              scenario_id: state[:current_scenario_id],
              tool_name: TOOL_NAME,
              extracted: merged,
              missing: ["flight_number_or_last_name"],
              prompt: prompt
            }

            # Если pending уже был, но новый ответ не похож на ответ по теме рейса,
            # значит пользователь, вероятно, сменил намерение и его нужно reroute'ить.
            if had_pending && !FOLLOWUP_RE.match?(req[:text].to_s)
              # Исключаем текущий сценарий из списка кандидатов для reroute.
              available_scenarios = filtered_router_scenarios(state, state[:current_scenario_id])
              # Просим router-LLM выбрать другой сценарий под новый текст пользователя.
              reroute_resp = await.call(
                "reroute_decision",
                :llm,
                mode: "routing_decision",
                input_data: {
                  task: Runtime::Router::ROUTER_TASK,
                  text: req[:text],
                  available_scenarios: available_scenarios,
                  dialog_context: state[:dialog_context].to_s,
                  context_artifacts: Runtime::Util.extract_hash(state[:context_artifacts])
                },
                constraints: { temperature: 0 }
              )
              # Нормализуем выбранный workflow_id в один из допустимых scenario ids.
              reroute_id = normalize_routing_choice(reroute_resp, available_scenarios)
              { reroute_scenario_id: reroute_id, collect_status: "reroute" }
            else
              # Иначе остаемся в текущем сценарии и просим пользователя уточнить параметры.
              {
                collected_params: merged,
                collect_prompt: prompt,
                collect_pending: pending_state,
                collect_status: "missing"
              }
            end
          end
        end

        # Routing после стадии извлечения параметров.
        def route_after_collect(state)
          case state[:collect_status]
          when "ready"
            # Параметры готовы, можно дергать tool.
            AsyncGraph::Command.goto(:call_status_tool)
          when "missing"
            # Нужны дополнительные данные от пользователя.
            AsyncGraph::Command.goto(:ask_missing)
          when "reroute"
            # Текущий сценарий больше не подходит, передаем управление дальше.
            AsyncGraph::Command.goto(:reroute)
          else
            # Любой неожиданный статус считаем ошибкой маршрутизации сценария.
            AsyncGraph::Command.update_and_goto(
              {
                error_code: "collect_params_failed",
                error_message: "Не удалось определить дальнейший шаг сценария поиска рейса."
              },
              :emit_failed_response
            )
          end
        end

        # Возвращает partial-response с уточняющим вопросом и pending-данными.
        def ask_missing(state)
          {
            response: partial_response(
              state.fetch(:req),
              state[:collect_prompt],
              active_workflow_id: state[:current_scenario_id],
              pending: Runtime::Util.extract_hash(state[:collect_pending])
            )
          }
        end

        # Вызывает инструмент получения статуса рейса и подготавливает текст ответа.
        def call_status_tool(state, await)
          # Исходный req нужен для финального LLM-ответа.
          req = state.fetch(:req)
          # Аргументы инструмента берем из уже собранных параметров.
          args = Runtime::Util.extract_hash(state[:collected_params])
          # Выполняем tool lookup статуса рейса.
          tool_resp = await.call(
            "flight_lookup",
            :tool,
            tool_name: TOOL_NAME,
            args: args
          )

          # При ошибке инструмента разбираем специальные и общие кейсы.
          unless tool_resp[:ok]
            # Достаем машинный код ошибки.
            code = Runtime::Util.extract_hash(tool_resp[:error])[:code].to_s
            # Если код не пришел, используем общий fallback-код.
            code = "tool_failed" if code.empty?

            # not_found считаем бизнес-результатом, а не системной ошибкой.
            if code == "not_found"
              return {
                response_message: "Статус рейса не найден.",
                tool_status: "not_found"
              }
            end

            # Для всех остальных ошибок готовим стандартный error payload.
            failure_message = "Не удалось получить статус рейса."
            return {
              error_code: code,
              error_message: failure_message,
              error_client_handler: {
                command: "SHOW_ERROR_MESSAGE",
                payload: { message: failure_message, code: code }
              },
              tool_status: "failed"
            }
          end

          # Если tool сработал, просим LLM сформировать человекочитаемый ответ.
          final_resp = await.call(
            "flight_response",
            :llm,
            mode: "final_response",
            input_data: {
              task: FINAL_TASK,
              user_message: req[:text],
              tool_results: [{ tool_name: TOOL_NAME, result: tool_resp[:data] }],
              scenario_context: SCENARIO_CONTEXT,
              dialog_context: state[:dialog_context].to_s
            },
            constraints: { temperature: 0.1 }
          )

          # Сначала пробуем взять текст от LLM.
          message = extract_llm_text(final_resp)
          # Если LLM промолчала, формируем текст сами из tool payload.
          message = fallback_flight_status_message(tool_resp[:data]) if message.to_s.empty?
          # Последний страховочный fallback на случай совсем пустых данных.
          message = "Готово." if message.to_s.empty?

          # Возвращаем финальный текст и успешный статус stage.
          {
            response_message: message,
            tool_status: "done"
          }
        end

        # Routing после вызова инструмента статуса рейса.
        def route_after_tool(state)
          case state[:tool_status]
          when "done"
            # Успешный ответ готов к выдаче пользователю.
            AsyncGraph::Command.goto(:emit_final_response)
          when "not_found"
            # Ничего не нашли, но это нормальный пользовательский исход.
            AsyncGraph::Command.goto(:emit_not_found_response)
          when "failed"
            # Инструмент или сценарий завершились ошибкой.
            AsyncGraph::Command.goto(:emit_failed_response)
          else
            # Непредвиденное состояние считаем ошибкой workflow.
            AsyncGraph::Command.update_and_goto(
              {
                error_code: "flight_lookup_failed",
                error_message: "Не удалось завершить сценарий поиска рейса."
              },
              :emit_failed_response
            )
          end
        end

        # Формирует обычный done-response при успешном поиске.
        def emit_final_response(state)
          { response: done_response(state.fetch(:req), state[:response_message]) }
        end

        # Формирует обычный done-response при business-case "не найдено".
        def emit_not_found_response(state)
          { response: done_response(state.fetch(:req), state[:response_message]) }
        end

        # Формирует failed-response для ошибочных финалов сценария.
        def emit_failed_response(state)
          # Берем код ошибки из state.
          code = state[:error_code].to_s
          # Если код не заполнен, используем общий fallback.
          code = "workflow_failed" if code.empty?
          # Берем текст ошибки из state.
          message = state[:error_message].to_s
          # Подстраховываемся общим текстом на случай пустого сообщения.
          message = "Workflow failed." if message.empty?

          # Возвращаем стандартизированный failed-response runtime.
          {
            response: failed_response(
              state.fetch(:req),
              code: code,
              message: message,
              client_handler: state[:error_client_handler]
            )
          }
        end

        # Передает управление другому сценарию через scenario_runner.
        def reroute(state)
          # scenario_runner уже умеет запускать другой workflow на текущем state.
          response = state.fetch(:scenario_runner).call(state[:reroute_scenario_id], state)
          { response: response }
        end

        private

        # Нормализует LLM-ответ режима tool_params.
        # Возвращает extracted-поля и prompt в предсказуемой форме.
        def normalize_tool_params(resp)
          # Если LLM отработала успешно, извлекаем полезную нагрузку.
          data = resp[:ok] ? Runtime::Util.extract_hash(resp[:data]) : {}
          # extracted должен быть hash, иначе считаем его пустым.
          extracted = data[:extracted].is_a?(Hash) ? Runtime::Util.extract_hash(data[:extracted]) : {}
          # prompt может прийти не строкой, поэтому нормализуем его отдельно.
          prompt = data[:prompt]
          prompt = prompt.to_s unless prompt.nil? || prompt.is_a?(String)
          { extracted: extracted, prompt: prompt }
        end

        # Объединяет старые и новые параметры так, чтобы пустые значения
        # не затирали уже собранные полезные поля.
        def merge_non_empty_params(base, new_values)
          # Начинаем с копии старых параметров.
          merged = Runtime::Util.extract_hash(base)
          # По очереди применяем новые значения.
          Runtime::Util.extract_hash(new_values).each do |key, value|
            # nil значения пропускаем.
            next if value.nil?
            # Пустые строки тоже не переносим, чтобы не затирать хорошие данные.
            next if value.is_a?(String) && value.strip.empty?

            merged[key] = value
          end
          merged
        end

        # Проверяет, есть ли среди указанных полей хотя бы одно валидное значение.
        def ready_with_any_field?(payload, fields)
          Array(fields).map(&:to_sym).any? do |key|
            value = payload[key]
            value.is_a?(String) ? !value.strip.empty? : !value.nil?
          end
        end

        # Возвращает список сценариев для reroute без текущего активного сценария.
        def filtered_router_scenarios(state, excluded_scenario_id)
          # Текущий сценарий нужно исключить из кандидатов.
          excluded = excluded_scenario_id.to_s
          Array(state[:router_scenarios]).filter_map do |item|
            # Нормализуем каждую запись реестра сценариев.
            entry = Runtime::Util.extract_hash(item)
            # Пропускаем текущий сценарий.
            next if entry[:id].to_s == excluded

            # Оставляем только поля, нужные router LLM.
            { id: entry[:id].to_s, description: entry[:description].to_s }
          end
        end

        # Нормализует ответ router-LLM в допустимый scenario id.
        def normalize_routing_choice(resp, available_scenarios)
          # Собираем whitelist разрешенных id.
          allowed_ids = available_scenarios.map { |item| item[:id].to_s }
          # Извлекаем payload только если router-ответ успешный.
          data = resp[:ok] ? Runtime::Util.extract_hash(resp[:data]) : {}
          # Берем выбранный workflow_id и очищаем пробелы.
          candidate = data[:workflow_id].to_s.strip
          # Возвращаем candidate только если он действительно разрешен.
          return candidate if allowed_ids.include?(candidate)

          # Иначе переводим пользователя в free_speech как безопасный fallback.
          Runtime::ScenarioIds::FREE_SPEECH
        end

        # Собирает резервный текст ответа по статусу рейса, если LLM не вернула свой текст.
        def fallback_flight_status_message(tool_data)
          # Извлекаем внутренний payload инструмента.
          data = extract_nested_data(tool_data) || {}
          # Пытаемся достать hash с описанием рейса.
          flight = data[:flight].is_a?(Hash) ? Runtime::Util.extract_hash(data[:flight]) : {}
          # Если flight-поля нет, возвращаем простой not found текст.
          return "Статус рейса не найден." if flight.empty?

          # Нормализуем номер рейса.
          flight_number = flight[:flight_number].to_s.strip
          flight_number = "рейс" if flight_number.empty?
          # Нормализуем аэропорт отправления.
          from = flight[:from].to_s.strip
          from = "?" if from.empty?
          # Нормализуем аэропорт прибытия.
          to = flight[:to].to_s.strip
          to = "?" if to.empty?
          # Приводим время вылета к компактному виду.
          departure = compact_time(flight[:departure_time])
          # Приводим время прилета к компактному виду.
          arrival = compact_time(flight[:arrival_time])
          # Переводим внутренний код статуса в русский текст.
          status = status_text(flight[:status].to_s)

          # Собираем лаконичную финальную фразу.
          "Рейс #{flight_number} (#{from} → #{to}), вылет #{departure}, прибытие #{arrival}. Статус: #{status}."
        end

        # Нормализует ISO-like timestamp в короткий формат HH:MM.
        def compact_time(value)
          # Преобразуем вход к строке и обрезаем пробелы.
          text = value.to_s.strip
          # Для пустого значения возвращаем placeholder.
          return "?" if text.empty?
          # Для ISO-времени берем только часовую часть и минуты.
          return text[11, 5] if text.length >= 16 && text.include?("T")

          # Во всех остальных случаях возвращаем исходный текст.
          text
        end

        # Преобразует внутренний код статуса рейса в русский человекочитаемый текст.
        def status_text(value)
          # Нормализуем статус в upper-case для lookup по словарю.
          status = value.to_s.strip.upcase
          # Если статус не пришел, возвращаем обобщенное значение.
          return "неизвестен" if status.empty?

          # Локализуем известные статусы и сохраняем запасной fallback.
          {
            "ON_TIME" => "вовремя",
            "DELAYED" => "задерживается",
            "CANCELLED" => "отменен"
          }.fetch(status, status.downcase)
        end
      end
    end
  end
end
