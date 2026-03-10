# frozen_string_literal: true

module SrcLanggraphRb
  module Schema
    Node = Data.define(:id, :kind, :config, :meta) do
      def to_h
        {
          id: id.to_s,
          kind: kind.to_s,
          config: config,
          meta: meta
        }
      end
    end
  end
end
