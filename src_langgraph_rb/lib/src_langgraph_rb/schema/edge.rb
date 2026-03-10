# frozen_string_literal: true

module SrcLanggraphRb
  module Schema
    Edge = Data.define(:type, :from, :to, :router, :path_map, :meta) do
      def direct?
        type == :direct
      end

      def conditional?
        type == :conditional
      end

      def to_h
        data = {
          type: type.to_s,
          from: from.to_s,
          meta: meta
        }
        data[:to] = to.to_s if to
        data[:router] = router.to_s if router
        data[:path_map] = path_map.transform_keys(&:to_s).transform_values(&:to_s) if path_map
        data
      end
    end
  end
end
