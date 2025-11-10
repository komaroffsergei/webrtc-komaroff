# frozen_string_literal: true

module WhisperRuby
  module TextUtils
    module_function

    def ensure_utf8(value)
      case value
      when String
        str = value.dup.force_encoding(Encoding::UTF_8)
        str.encode!(Encoding::UTF_8, invalid: :replace, undef: :replace)
        str
      when Hash
        value.transform_values { |v| ensure_utf8(v) }
      when Array
        value.map { |v| ensure_utf8(v) }
      else
        value
      end
    end
  end
end
