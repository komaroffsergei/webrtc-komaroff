# frozen_string_literal: true

require "json"
require "securerandom"

module SrcLanggraphRb
  module Runtime
    module Util
      module_function

      UUID_RE = /\A[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}\z/i

      def deep_symbolize(value)
        case value
        when Hash
          value.each_with_object({}) do |(key, item), out|
            out[key.to_sym] = deep_symbolize(item)
          end
        when Array
          value.map { |item| deep_symbolize(item) }
        else
          value
        end
      end

      def deep_stringify(value)
        case value
        when Hash
          value.each_with_object({}) do |(key, item), out|
            out[key.to_s] = deep_stringify(item)
          end
        when Array
          value.map { |item| deep_stringify(item) }
        else
          value
        end
      end

      def extract_hash(value)
        value.is_a?(Hash) ? deep_symbolize(value) : {}
      end

      def text(value)
        clean = value.to_s.strip
        clean.empty? ? nil : clean
      end

      def integer(value, default: nil)
        return default if value.nil?

        Integer(value)
      rescue ArgumentError, TypeError
        default
      end

      def float(value, default: nil)
        return default if value.nil?

        Float(value)
      rescue ArgumentError, TypeError
        default
      end

      def uuid_string?(value)
        value.is_a?(String) && UUID_RE.match?(value)
      end

      def require_uuid!(value, label)
        raise ArgumentError, "#{label} must be a UUID string" unless uuid_string?(value)

        value
      end

      def require_positive_integer!(value, label)
        int = integer(value)
        raise ArgumentError, "#{label} must be a positive integer" unless int && int.positive?

        int
      end

      def require_non_empty_string!(value, label)
        clean = text(value)
        raise ArgumentError, "#{label} must be provided" unless clean

        clean
      end

      def generate_uuid
        SecureRandom.uuid
      end
    end
  end
end
