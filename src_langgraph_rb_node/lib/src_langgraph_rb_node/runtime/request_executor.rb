# frozen_string_literal: true

module SrcLanggraphRbNode
  module Runtime
    class RequestExecutor
      def initialize(io:)
        @io = io
      end

      def call(request, state:)
        case request.kind.to_sym
        when :llm
          @io.call_llm(
            parent: state.fetch(:req),
            mode: request.payload.fetch(:mode).to_s,
            input_data: Runtime::Util.extract_hash(request.payload[:input_data]),
            constraints: Runtime::Util.extract_hash(request.payload[:constraints])
          )
        when :tool
          @io.call_tool(
            parent: state.fetch(:req),
            tool_name: request.payload.fetch(:tool_name).to_s,
            args: Runtime::Util.extract_hash(request.payload[:args])
          )
        else
          raise ValidationError, "Unsupported AsyncGraph request kind '#{request.kind}'"
        end
      end
    end
  end
end
