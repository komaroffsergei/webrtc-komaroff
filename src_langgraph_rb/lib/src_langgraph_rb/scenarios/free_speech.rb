# frozen_string_literal: true

module SrcLanggraphRb
  module Scenarios
    module FreeSpeech
      module_function

      TASK = "Побеседуй с пользователем в свободной форме.\n" \
             "Отвечай кратко, по-русски, дружелюбно и по делу.\n" \
             "Если вопрос непонятен, задай уточняющий вопрос.\n" \
             "Используй context_artifacts и dialog_context для референций вроде 'он/этот' и 'они/эти'.\n" \
             "При resolved_reference_mode=single не задавай повторный вопрос о том, что имелось в виду.\n" \
             "При resolved_reference_mode=multi и запросе во множественном числе отвечай по каждой сущности из resolved_entities.\n" \
             "Используй не только контекст диалога, но и общие знания модели.\n" \
             "Если в знании не уверен, явно укажи неопределенность."
      SCENARIO_CONTEXT = "Свободный диалог без сценария.\n" \
                         "Инструменты не используются.\n" \
                         "Цель — помочь пользователю и поддерживать разговор."
      FALLBACK_MESSAGE = "Сервис ответов временно недоступен. Попробуйте повторить запрос."

      def register(builder)
        builder.scenario("free_speech@2.0.0") do
          title "Free Speech"
          description "Generic free-form dialog without tools"
          routing_description "Свободный разговор: общение с пользователем без инструментов"
          tags :chat, :fallback
          capabilities :stateful_dialog, :final_response
          runtime_flags context_required: true

          graph do
            use :assistant_reply_tail, as: :final
            use :state_response_tail, as: :terminal
            entry_point :prepare_context

            node :prepare_context, kind: :compute, op: :resolve_context_references, status_key: :free_speech_entry,
              clarify_message_key: :clarify_message
            node :clarify_reference, kind: :done_response, message_source: :clarify_message
            node :compose_response, kind: :compute, op: :compose_free_speech_response, task: TASK,
              scenario_context: SCENARIO_CONTEXT, fallback_message: FALLBACK_MESSAGE,
              primary_constraints: { temperature: 0.4 }, retry_constraints: { temperature: 0.3 },
              status_key: :free_speech_result

            conditional_edge :prepare_context, :free_speech_entry, {
              "clarify" => :clarify_reference,
              "continue" => :compose_response
            }

            edge :clarify_reference, ref(:terminal, :respond)
            conditional_edge :compose_response, :free_speech_result, {
              "done" => ref(:final, :respond),
              "terminal" => ref(:terminal, :respond)
            }
          end
        end
      end
    end
  end
end
