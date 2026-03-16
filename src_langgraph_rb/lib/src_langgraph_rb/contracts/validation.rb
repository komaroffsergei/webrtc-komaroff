# frozen_string_literal: true

module SrcLanggraphRb
  module Contracts
    module Validation
      UUID_RE = /\A[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}\z/i
      module_function

      def hash!(value, label)
        return value if value.is_a?(Hash)

        raise ValidationError, "#{label} must be a hash"
      end

      def array(value)
        value.is_a?(Array) ? value : []
      end

      def string!(value, label)
        text = value.is_a?(String) ? value.strip : value.to_s.strip
        raise ValidationError, "#{label} must be provided" if text.empty?

        text
      end

      def optional_string(value)
        return nil if value.nil?

        text = value.is_a?(String) ? value.strip : value.to_s.strip
        text.empty? ? nil : text
      end

      def uuid!(value, label)
        text = string!(value, label)
        raise ValidationError, "#{label} must be a UUID" unless text.match?(UUID_RE)

        text
      end

      def optional_uuid(value)
        return nil if value.nil?

        text = optional_string(value)
        return nil if text.nil?

        raise ValidationError, "UUID value must be valid" unless text.match?(UUID_RE)

        text
      end

      def integer!(value, label)
        number = Integer(value)
        raise ValidationError, "#{label} must be positive" if number <= 0

        number
      rescue ArgumentError, TypeError
        raise ValidationError, "#{label} must be an integer"
      end

      def bool(value)
        value == true
      end

      def deep_copy_hash(value)
        return {} unless value.is_a?(Hash)

        Marshal.load(Marshal.dump(value))
      end
    end
  end
end
