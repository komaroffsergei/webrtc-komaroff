# frozen_string_literal: true

module SrcLanggraphRb
  class Error < StandardError; end
  class ValidationError < Error; end
  class RegistryError < Error; end
  class FragmentError < Error; end
end
