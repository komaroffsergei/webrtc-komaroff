# frozen_string_literal: true

module SrcLanggraphRb
  module DSL
    module Support
      module Identifiers
        module_function

        def normalize_id(value)
          text = value.to_s.strip
          raise ValidationError, "Identifier must be provided" if text.empty?

          text.tr(" ", "_").to_sym
        end

        def normalize_router(value)
          raise ValidationError, "Inline router callables are not supported in declarative specs" if value.respond_to?(:call)

          normalize_id(value)
        end

        def namespaced_id(namespace, value)
          namespace_text = namespace.to_s.strip
          return normalize_id(value) if namespace_text.empty?

          normalize_id("#{namespace_text}__#{value}")
        end
      end
    end
  end
end
