# frozen_string_literal: true

module SrcLanggraphRb
  module DSL
    module Support
      module Normalization
        module_function

        def normalize_hash(hash)
          return {} unless hash.is_a?(Hash)

          hash.each_with_object({}) do |(key, value), out|
            out[key.to_sym] = value
          end.freeze
        end

        def normalize_path_map(path_map)
          unless path_map.is_a?(Hash) && !path_map.empty?
            raise ValidationError, "Path map must be a non-empty hash"
          end

          path_map.each_with_object({}) do |(key, value), out|
            out[key.to_s] = Support::Identifiers.normalize_id(value)
          end.freeze
        end
      end
    end
  end
end
