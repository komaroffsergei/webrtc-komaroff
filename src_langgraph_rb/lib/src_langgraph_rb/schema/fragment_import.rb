# frozen_string_literal: true

module SrcLanggraphRb
  module Schema
    FragmentImport = Data.define(:name, :alias_name) do
      def to_h
        {
          name: name.to_s,
          alias: alias_name.to_s
        }
      end
    end
  end
end
