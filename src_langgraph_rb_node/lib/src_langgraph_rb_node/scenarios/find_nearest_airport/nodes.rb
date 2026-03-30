# frozen_string_literal: true

module SrcLanggraphRbNode
  module Scenarios
    module FindNearestAirport
      # Узлы сценария поиска ближайшего аэропорта и построения маршрута до него.
      # Сценарий работает в несколько фаз:
      # 1. Получает текущую позицию пользователя через tool.
      # 2. Просит LLM подготовить аргументы для поиска ближайших аэропортов.
      # 3. Ищет аэропорты рядом с пользователем.
      # 4. Просит LLM подготовить координаты для построения маршрута.
      # 5. Строит маршрут и формирует финальный пользовательский ответ.
      class Nodes < BaseNodes
        # Имя инструмента, который возвращает текущую позицию пользователя.
        POSITION_TOOL = "get_current_position"
        # Имя инструмента, который ищет аэропорты рядом с заданной точкой/городом.
        SEARCH_TOOL = "search_airports_nearby"
        # Имя инструмента, который строит маршрут между двумя точками.
        BUILD_ROUTE_TOOL = "build_route"

        # Резервный город, который используется, если LLM и tool позиции не дали город.
        DEFAULT_CITY = "Moscow"
        # Резервный радиус поиска аэропортов в километрах.
        DEFAULT_RADIUS_KM = 50.0

        # Инструкция для LLM по подготовке параметров поиска аэропортов.
        # LLM должна либо взять город из текста пользователя,
        # либо, если город не назван, использовать результат инструмента позиции.
        SEARCH_PARAMS_TASK = "Подготовь параметры для поиска ближайших аэропортов.\n" \
                             "Если город не указан явно, используй данные о текущей позиции из tool_results."

        # Инструкция для LLM по подготовке координат для построения маршрута.
        # Источник координат старта: текущая позиция пользователя.
        # Источник координат назначения: первый найденный аэропорт.
        ROUTE_PARAMS_TASK = "Подготовь параметры для построения маршрута до выбранного аэропорта.\n" \
                            "Используй текущую позицию пользователя и координаты первого найденного аэропорта."

        # Инструкция для LLM по сборке финального ответа после всех tool-вызовов.
        FINAL_TASK = "Сформируй финальный ответ пользователю по найденному аэропорту и маршруту.\n" \
                     "Пиши по-русски."

        # Короткий контекст сценария, который передается в финальный LLM-вызов.
        SCENARIO_CONTEXT = "Пользователь хочет найти ближайший аэропорт и построить маршрут."

        # Схема параметров для инструмента поиска аэропортов.
        # Используется не самим tool, а LLM при режиме tool_params,
        # чтобы модель знала допустимые аргументы и их смысл.
        SEARCH_TOOL_SCHEMA = {
          parameters: {
            city: { type: "string", description: "Город для поиска ближайших аэропортов" },
            radius_km: { type: "number", description: "Радиус поиска в километрах", default: 50 }
          }
        }.freeze

        # Схема параметров для инструмента построения маршрута.
        ROUTE_TOOL_SCHEMA = {
          parameters: {
            from_lat: { type: "number" },
            from_lon: { type: "number" },
            to_lat: { type: "number" },
            to_lon: { type: "number" }
          }
        }.freeze

        # Первый шаг сценария: получить текущую позицию пользователя.
        # На входе нода состояние не использует, поэтому первый аргумент `_state`.
        # На выходе либо сохраняет успешный ответ инструмента,
        # либо подготавливает унифицированное описание ошибки.
        def get_position(_state, await)
          # Runtime приостанавливает ноду и выполняет tool-вызов.
          tool_resp = await.call(
            "get_position",
            :tool,
            tool_name: POSITION_TOOL,
            args: {}
          )

          # При успехе сохраняем полный ответ инструмента и маркер успешной стадии.
          if tool_resp[:ok]
            {
              position_response: tool_resp,
              position_status: "ok"
            }
          else
            # Пытаемся вытащить машинный код ошибки из runtime-формата.
            code = Runtime::Util.extract_hash(tool_resp[:error])[:code].to_s
            # Если код не пришел, ставим общий fallback-код.
            code = "tool_failed" if code.empty?
            # Человеко-читаемый текст ошибки для ответа и UI.
            message = "Не удалось получить текущую позицию."

            # Возвращаем поля, которые downstream fail-нода преобразует в failed_response.
            {
              error_code: code,
              error_message: message,
              error_client_handler: {
                command: "SHOW_ERROR_MESSAGE",
                payload: { message: message, code: code }
              },
              position_status: "failed"
            }
          end
        end

        # Routing-узел после попытки получить текущую позицию.
        # Если позиция найдена, двигаемся дальше по сценарию.
        # Если нет, переходим в финальную fail-ноду.
        def route_after_position(state)
          if state[:position_status] == "ok"
            AsyncGraph::Command.goto(:prepare_airport_search)
          else
            AsyncGraph::Command.goto(:position_failed)
          end
        end

        # Готовит аргументы для инструмента поиска аэропортов.
        # Сам tool здесь ещё не вызывается: сначала LLM помогает собрать удобные параметры.
        def prepare_airport_search(state, await)
          # Оригинальный пользовательский запрос нужен как для LLM, так и для логики fallback.
          req = state.fetch(:req)
          # Нормализуем сырой ответ инструмента позиции в обычный hash.
          position_resp = Runtime::Util.extract_hash(state[:position_response])
          # Извлекаем вложенный payload с координатами/городом из результата инструмента.
          position_data = extract_nested_data(position_resp[:data] || position_resp) || {}
          # Формируем историю tool_results, которую передадим в LLM.
          tool_results = [{ tool_name: POSITION_TOOL, result: position_resp[:data] || position_resp }]

          # Просим LLM подготовить параметры для инструмента поиска аэропортов.
          params_resp = await.call(
            "airport_search_params",
            :llm,
            mode: "tool_params",
            input_data: {
              task: SEARCH_PARAMS_TASK,
              user_message: req[:text],
              tool_name: SEARCH_TOOL,
              tool_schema: SEARCH_TOOL_SCHEMA,
              tool_results: tool_results,
              dialog_context: state[:dialog_context].to_s
            },
            constraints: { temperature: 0 }
          )

          # Нормализуем extracted-параметры из ответа LLM.
          extracted = normalize_tool_params(params_resp)
          # Сначала берем город из extracted-параметров.
          city = extracted[:city].to_s.strip
          # Если модель не вернула город, пробуем взять его из текущей позиции.
          city = position_data[:city].to_s.strip if city.empty?
          # Если и там пусто, используем жесткий резервный fallback.
          city = DEFAULT_CITY if city.empty?
          # Радиус поиска приводим к float и тоже защищаем резервным значением.
          radius_km = Runtime::Util.float(extracted[:radius_km], default: DEFAULT_RADIUS_KM) || DEFAULT_RADIUS_KM

          # Сохраняем в состояние:
          # - текущую позицию,
          # - накопленные tool_results,
          # - готовые аргументы для следующего tool-вызова.
          {
            current_position: position_data,
            tool_results: tool_results,
            search_args: { city: city, radius_km: radius_km }
          }
        end

        # Вызывает инструмент поиска ближайших аэропортов.
        def search_airports(state, await)
          # Передаем в tool только нормализованные аргументы поиска.
          tool_resp = await.call(
            "search_airports",
            :tool,
            tool_name: SEARCH_TOOL,
            args: Runtime::Util.extract_hash(state[:search_args])
          )

          # Успех сохраняем отдельно от ошибок, чтобы routing-нода могла быстро принять решение.
          if tool_resp[:ok]
            {
              search_response: tool_resp,
              search_status: "ok"
            }
          else
            # Извлекаем код ошибки инструмента.
            code = Runtime::Util.extract_hash(tool_resp[:error])[:code].to_s
            # Если код пустой, используем общий fallback.
            code = "tool_failed" if code.empty?
            # Готовим русский текст для пользователя/клиента.
            message = "Не удалось найти ближайшие аэропорты."

            # Возвращаем согласованный набор полей для fail-ветки.
            {
              error_code: code,
              error_message: message,
              error_client_handler: {
                command: "SHOW_ERROR_MESSAGE",
                payload: { message: message, code: code }
              },
              search_status: "failed"
            }
          end
        end

        # Routing после поиска аэропортов.
        def route_after_search(state)
          if state[:search_status] == "ok"
            AsyncGraph::Command.goto(:prepare_route)
          else
            AsyncGraph::Command.goto(:search_failed)
          end
        end

        # Готовит координаты для инструмента построения маршрута.
        # Здесь LLM помогает собрать четыре числа: from_lat/from_lon/to_lat/to_lon.
        def prepare_route(state, await)
          # Снова берем исходный запрос пользователя для prompt-контекста.
          req = state.fetch(:req)
          # Нормализуем ответ предыдущего tool-вызова.
          search_resp = Runtime::Util.extract_hash(state[:search_response])
          # Расширяем цепочку tool_results свежим результатом поиска аэропортов.
          tool_results = Array(state[:tool_results]) + [{ tool_name: SEARCH_TOOL, result: search_resp[:data] || search_resp }]

          # Просим LLM подготовить аргументы маршрута по позиции пользователя и найденному аэропорту.
          params_resp = await.call(
            "airport_route_params",
            :llm,
            mode: "tool_params",
            input_data: {
              task: ROUTE_PARAMS_TASK,
              user_message: req[:text],
              tool_name: BUILD_ROUTE_TOOL,
              tool_schema: ROUTE_TOOL_SCHEMA,
              tool_results: tool_results,
              dialog_context: state[:dialog_context].to_s
            },
            constraints: { temperature: 0 }
          )

          # Нормализуем и дополняем аргументы маршрута:
          # LLM может вернуть часть координат,
          # остальные добираем из текущей позиции и первого найденного аэропорта.
          route_args = normalize_route_args(
            normalize_tool_params(params_resp),
            Runtime::Util.extract_hash(state[:current_position]),
            extract_nested_data(search_resp[:data] || search_resp) || {}
          )

          # Если все четыре координаты готовы, передаем их дальше по сценарию.
          if route_args
            {
              route_args: route_args,
              tool_results: tool_results,
              route_args_status: "ready"
            }
          else
            # Иначе отмечаем стадию как failed, чтобы routing увел сценарий в fail-ноду.
            {
              error_code: "route_params_missing",
              error_message: "Не удалось собрать координаты для маршрута.",
              route_args_status: "failed"
            }
          end
        end

        # Routing после подготовки аргументов маршрута.
        def route_after_route_args(state)
          if state[:route_args_status] == "ready"
            AsyncGraph::Command.goto(:build_route)
          else
            AsyncGraph::Command.goto(:route_args_failed)
          end
        end

        # Вызывает инструмент построения маршрута и формирует финальный текст ответа.
        def build_route(state, await)
          # Оригинальный req нужен для final_response режима LLM.
          req = state.fetch(:req)
          # Запускаем tool построения маршрута по уже готовым координатам.
          route_resp = await.call(
            "build_route",
            :tool,
            tool_name: BUILD_ROUTE_TOOL,
            args: Runtime::Util.extract_hash(state[:route_args])
          )

          # Если инструмент завершился ошибкой, сразу выходим в fail-ветку.
          unless route_resp[:ok]
            # Извлекаем код ошибки инструмента.
            code = Runtime::Util.extract_hash(route_resp[:error])[:code].to_s
            # При отсутствии кода ставим общий fallback.
            code = "tool_failed" if code.empty?
            # Подготавливаем сообщение для пользователя и UI.
            message = "Не удалось построить маршрут."

            # Возвращаем error payload и статус неуспешной стадии.
            return {
              error_code: code,
              error_message: message,
              error_client_handler: {
                command: "SHOW_ERROR_MESSAGE",
                payload: { message: message, code: code }
              },
              build_route_status: "failed"
            }
          end

          # Если маршрут построен, расширяем историю tool_results новым результатом.
          tool_results = Array(state[:tool_results]) + [{ tool_name: BUILD_ROUTE_TOOL, result: route_resp[:data] }]
          # Просим LLM собрать связный финальный ответ для пользователя.
          final_resp = await.call(
            "airport_final_response",
            :llm,
            mode: "final_response",
            input_data: {
              task: FINAL_TASK,
              user_message: req[:text],
              tool_results: tool_results,
              scenario_context: SCENARIO_CONTEXT,
              dialog_context: state[:dialog_context].to_s
            },
            constraints: { temperature: 0.1 }
          )

          # Пытаемся достать финальный текст из ответа модели.
          message = extract_llm_text(final_resp)
          # Если модель не вернула текст, используем короткий резервный вариант.
          message = "Маршрут построен." if message.empty?

          # Из результата поиска достаем список аэропортов для клиентского события.
          airports_data = extract_nested_data(state.dig(:search_response, :data) || state[:search_response]) || {}
          # Из результата build_route достаем сам маршрут для UI.
          route_data = extract_nested_data(route_resp[:data]) || {}

          # Возвращаем:
          # - финальный текст,
          # - события для клиентского интерфейса,
          # - статус завершенной стадии.
          {
            response_message: message,
            client_events: [
              { command: "SET_POSITION", payload: { data: { current_position: Runtime::Util.extract_hash(state[:current_position]) } } },
              { command: "SET_AIRPORTS", payload: { data: { airports: airports_data[:airports] || [] } } },
              { command: "BUILD_ROUTE", payload: { data: { route: route_data } } }
            ],
            build_route_status: "done"
          }
        end

        # Routing после финальной стадии build_route.
        def route_after_build_route(state)
          if state[:build_route_status] == "done"
            AsyncGraph::Command.goto(:emit_final_response)
          else
            AsyncGraph::Command.goto(:build_route_failed)
          end
        end

        # Заворачивает подготовленный текст и client_events в итоговый done-response.
        def emit_final_response(state)
          {
            response: done_response(
              state.fetch(:req),
              state[:response_message],
              client_events: Array(state[:client_events])
            )
          }
        end

        # Финальная fail-нода для ошибки получения позиции.
        def position_failed(state)
          { response: scenario_failed_response(state) }
        end

        # Финальная fail-нода для ошибки поиска аэропортов.
        def search_failed(state)
          { response: scenario_failed_response(state) }
        end

        # Финальная fail-нода для ошибки подготовки координат маршрута.
        def route_args_failed(state)
          { response: scenario_failed_response(state) }
        end

        # Финальная fail-нода для ошибки построения маршрута.
        def build_route_failed(state)
          { response: scenario_failed_response(state) }
        end

        private

        # Сводит поля ошибки из state в единый failed_response.
        def scenario_failed_response(state)
          # Берем код ошибки из state.
          code = state[:error_code].to_s
          # Если код не заполнен, используем общий workflow_failed.
          code = "workflow_failed" if code.empty?
          # Берем текст ошибки из state.
          message = state[:error_message].to_s
          # Если текста нет, используем общий fallback.
          message = "Workflow failed." if message.empty?

          # Возвращаем стандартизированный failed-response runtime.
          failed_response(
            state.fetch(:req),
            code: code,
            message: message,
            client_handler: state[:error_client_handler]
          )
        end

        # Нормализует extracted-часть ответа LLM в режиме tool_params.
        def normalize_tool_params(resp)
          # Если LLM-ответ успешный, достаем payload, иначе считаем его пустым.
          data = resp[:ok] ? Runtime::Util.extract_hash(resp[:data]) : {}
          # Возвращаем только extracted-hash, если он действительно имеет правильный тип.
          data[:extracted].is_a?(Hash) ? Runtime::Util.extract_hash(data[:extracted]) : {}
        end

        # Собирает валидный набор аргументов для build_route.
        # Функция комбинирует:
        # - то, что вернула LLM,
        # - текущую позицию пользователя,
        # - координаты первого найденного аэропорта.
        def normalize_route_args(extracted, current_position, airports_data)
          # Начинаем с пустого контейнера для итоговых координат.
          out = {}

          # Сначала пытаемся взять каждое из четырех обязательных полей из LLM extracted.
          %i[from_lat from_lon to_lat to_lon].each do |key|
            value = Runtime::Util.float(Runtime::Util.extract_hash(extracted)[key])
            out[key] = value if value
          end

          # Если стартовые координаты отсутствуют, пробуем заполнить их текущей позицией.
          out[:from_lat] ||= Runtime::Util.float(current_position[:lat])
          out[:from_lon] ||= Runtime::Util.float(current_position[:lon])

          # Для точки назначения берем первый аэропорт из списка найденных.
          first_airport = Array(airports_data[:airports]).first
          airport = first_airport.is_a?(Hash) ? Runtime::Util.extract_hash(first_airport) : {}
          out[:to_lat] ||= Runtime::Util.float(airport[:lat])
          out[:to_lon] ||= Runtime::Util.float(airport[:lon])

          # Проверяем, что обязательный набор координат заполнен полностью.
          required = %i[from_lat from_lon to_lat to_lon]
          return nil unless required.all? { |key| out.key?(key) }

          # Возвращаем только обязательные ключи в предсказуемом порядке.
          required.each_with_object({}) { |key, memo| memo[key] = out[key] }
        end
      end
    end
  end
end
