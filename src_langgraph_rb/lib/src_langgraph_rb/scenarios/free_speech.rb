# frozen_string_literal: true

module SrcLanggraphRb
  module Scenarios
    module FreeSpeech
      module_function

      def register(builder)
        builder.scenario("free_speech@2.0.0") do
          title "Free Speech"
          description "Generic free-form dialog without tools"
          tags :chat, :fallback
          capabilities :stateful_dialog, :final_response
          runtime_flags context_required: true

          graph do
            use :assistant_reply_tail, as: :final
            use :state_response_tail, as: :terminal
            entry_point :prepare_context

            node :prepare_context, kind: :context_enrichment, inputs: %i[dialog_context artifacts]
            node :clarify_reference, kind: :done_response, message_source: :clarify_message
            node :compose_primary, kind: :free_speech_primary
            node :compose_retry, kind: :free_speech_retry

            conditional_edge :prepare_context, :free_speech_entry, {
              "clarify" => :clarify_reference,
              "continue" => :compose_primary
            }

            edge :clarify_reference, ref(:terminal, :respond)
            conditional_edge :compose_primary, :free_speech_primary_result, {
              "done" => ref(:final, :respond),
              "retry" => :compose_retry,
              "terminal" => ref(:terminal, :respond)
            }
            edge :compose_retry, ref(:final, :respond)
          end
        end
      end
    end
  end
end
