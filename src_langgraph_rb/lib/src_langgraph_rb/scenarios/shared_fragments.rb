# frozen_string_literal: true

module SrcLanggraphRb
  module Scenarios
    module SharedFragments
      module_function

      def register(builder)
        builder.fragment(:assistant_reply_tail) do
          node :respond, kind: :final_response, response_channel: :chat
          finish_point :respond
        end

        builder.fragment(:state_response_tail) do
          node :respond, kind: :state_response
          finish_point :respond
        end
      end
    end
  end
end
