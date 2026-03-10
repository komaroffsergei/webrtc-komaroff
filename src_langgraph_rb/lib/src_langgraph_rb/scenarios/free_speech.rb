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
            entry_point :prepare_context

            node :prepare_context, kind: :context_enrichment, inputs: %i[dialog_context artifacts]
            node :compose_prompt, kind: :llm_prompt, mode: :final_response

            edge :prepare_context, :compose_prompt
            edge :compose_prompt, ref(:final, :respond)
          end
        end
      end
    end
  end
end
