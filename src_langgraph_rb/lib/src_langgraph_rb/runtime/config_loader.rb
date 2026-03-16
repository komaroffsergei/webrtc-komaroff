# frozen_string_literal: true

require "json"
require "pathname"

module SrcLanggraphRb
  module Runtime
    module ConfigLoader
      CONFIG_DIR = Pathname(__dir__).join("..", "..", "..", "config", "scenarios").expand_path.freeze
      module_function

      def load_config(name)
        path = CONFIG_DIR.join("#{name}.json")
        data = JSON.parse(path.read)
        raise ValidationError, "Invalid config shape in #{path}" unless data.is_a?(Hash)

        data
      end

      def text_block(value, default)
        case value
        when String
          value.strip.empty? ? default : value.strip
        when Array
          lines = value.filter_map do |item|
            text = item.to_s.strip
            text unless text.empty?
          end
          lines.empty? ? default : lines.join("\n")
        else
          default
        end
      end

      def dict_value(value, default = {})
        value.is_a?(Hash) ? value.dup : default.dup
      end

      def list_of_dicts(value, default = [])
        return default.map(&:dup) unless value.is_a?(Array)

        out = value.select { |item| item.is_a?(Hash) }.map(&:dup)
        out.empty? ? default.map(&:dup) : out
      end
    end
  end
end
