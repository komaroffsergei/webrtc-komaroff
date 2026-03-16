# frozen_string_literal: true

module SrcLanggraphRb
  module Runtime
    module Scenarios
      module Common
        module_function

        def extract_llm_text(resp)
          data = Runtime::Util.extract_hash(resp[:data])
          value = data[:response_text]
          return nil unless value.is_a?(String) && !value.strip.empty?

          value.strip
        end

        def normalize_tool_params(resp)
          data = resp[:ok] ? Runtime::Util.extract_hash(resp[:data]) : {}
          extracted = data[:extracted].is_a?(Hash) ? Runtime::Util.extract_hash(data[:extracted]) : {}
          missing = Array(data[:missing]).map(&:to_s)
          prompt = data[:prompt]
          prompt = prompt.to_s if !prompt.nil? && !prompt.is_a?(String)
          { extracted:, missing:, prompt: prompt }
        end

        def merge_non_empty_params(base, new_values)
          merged = Runtime::Util.extract_hash(base)
          Runtime::Util.extract_hash(new_values).each do |key, value|
            next if value.nil?
            next if value.is_a?(String) && value.strip.empty?

            merged[key] = value
          end
          merged
        end

        def extract_nested_data(payload)
          data = Runtime::Util.extract_hash(payload)
          inner = data[:data]
          inner.is_a?(Hash) ? Runtime::Util.extract_hash(inner) : nil
        end
      end
    end
  end
end
