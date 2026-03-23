# frozen_string_literal: true

module SrcLanggraphRbNode
  class Error < StandardError; end
  class ValidationError < Error; end
  class RegistryError < Error; end
end
