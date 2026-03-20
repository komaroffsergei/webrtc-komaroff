# frozen_string_literal: true

module SrcLanggraphRb
  module Scenarios
    module FreeSpeech
      # Делаем `register` модульной функцией, чтобы сценарий регистрировался без создания объекта.
      module_function

      # Основной prompt для свободного разговора.
      # Он задает стиль ответа и объясняет модели, как использовать context_artifacts и dialog_context.
      TASK = "Побеседуй с пользователем в свободной форме.\n" \
             "Отвечай кратко, по-русски, дружелюбно и по делу.\n" \
             "Если вопрос непонятен, задай уточняющий вопрос.\n" \
             "Используй context_artifacts и dialog_context для референций вроде 'он/этот' и 'они/эти'.\n" \
             "При resolved_reference_mode=single не задавай повторный вопрос о том, что имелось в виду.\n" \
             "При resolved_reference_mode=multi и запросе во множественном числе отвечай по каждой сущности из resolved_entities.\n" \
             "Используй не только контекст диалога, но и общие знания модели.\n" \
             "Если в знании не уверен, явно укажи неопределенность."

      # Короткое описание сценария для финального ответа.
      # Это дополнительный сигнал для `final_response`, что здесь нет tool-вызовов.
      SCENARIO_CONTEXT = "Свободный диалог без сценария.\n" \
                         "Инструменты не используются.\n" \
                         "Цель — помочь пользователю и поддерживать разговор."

      # Сообщение на крайний случай, если downstream LLM недоступна.
      FALLBACK_MESSAGE = "Сервис ответов временно недоступен. Попробуйте повторить запрос."

      # Регистрирует built-in сценарий свободного диалога.
      def register(builder)
        # Уникальный id сценария.
        builder.scenario("free_speech@2.0.0") do
          # Человекочитаемое название.
          title "Free Speech"

          # Короткое описание для разработчика.
          description "Generic free-form dialog without tools"

          # Подсказка для router'а: когда стоит выбирать именно этот сценарий.
          routing_description "Свободный разговор: общение с пользователем без инструментов"

          # Служебные теги.
          tags :chat, :fallback

          # Явно декларируем, что сценарий умеет держать диалоговый state и отдавать финальный ответ.
          capabilities :stateful_dialog, :final_response

          # Для этого сценария нужен диалоговый контекст.
          runtime_flags context_required: true

          # Ниже описывается граф исполнения сценария.
          graph do
            # Подключаем оба стандартных хвоста:
            # `final` превращает response_message в DONE,
            # `terminal` возвращает уже собранный response из state.
            use_default_tails

            # Первый узел сценария.
            # Сначала пытаемся понять, нет ли в запросе местоименной ссылки на объект из контекста.
            entry_point :prepare_context

            # Helper разворачивается в compute-op resolve_context_references.
            # Он анализирует `artifact_memory`, ищет сущности и записывает status/message в state.
            resolve_context_refs :prepare_context

            # Если reference resolution вернула clarify,
            # берем подготовленное сообщение из auto-generated key `prepare_context_message`.
            done :clarify_reference, message_source: message_of(:prepare_context)

            # Основной шаг генерации ответа.
            # Под капотом опускается в compute-op compose_free_speech_response.
            free_speech_response :compose_response,
              task: TASK, # Основной prompt для свободного ответа.
              scenario_context: SCENARIO_CONTEXT, # Контекст сценария для final_response.
              fallback_message: FALLBACK_MESSAGE, # Что вернуть при полном отказе LLM boundary.
              primary_constraints: { temperature: 0.4 }, # Параметры первого прохода.
              retry_constraints: { temperature: 0.3 } # Параметры retry-прохода при слабом первом ответе.

            # После prepare_context читаем auto-generated key `prepare_context_status`
            # и выбираем нужную ветку:
            # либо сразу уточняем, либо продолжаем генерацию ответа.
            route_status :prepare_context, {
              "clarify" => :clarify_reference,
              "continue" => :compose_response
            }

            # Узел clarify_reference уже сам собрал DONE response,
            # поэтому его надо просто довести до terminal tail.
            edge :clarify_reference, terminal

            # После compose_response читаем auto-generated key `compose_response_status`.
            # `done` идет в обычный final tail, `terminal` означает, что compute-op уже собрал response сам.
            route_status :compose_response, {
              "done" => final,
              "terminal" => terminal
            }
          end
        end
      end
    end
  end
end
