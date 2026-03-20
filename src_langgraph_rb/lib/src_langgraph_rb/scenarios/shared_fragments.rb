# frozen_string_literal: true

module SrcLanggraphRb
  module Scenarios
    module SharedFragments
      # Делаем `register` модульной функцией, чтобы fragments можно было подключать без инстанса.
      module_function

      # Регистрирует переиспользуемые куски графа, которые затем импортируются в сценарии через `use`.
      def register(builder)
        # Fragment для обычного DONE-ответа:
        # он берет `state[:response_message]` и собирает SHOW_MESSAGE через final_response.
        builder.fragment(:assistant_reply_tail) do
          # Единственный узел fragment'а — финальный ответ пользователю.
          node :respond, kind: :final_response, response_channel: :chat

          # Обозначаем этот узел точкой завершения fragment'а.
          finish_point :respond
        end

        # Fragment для случаев, когда response уже заранее собран в state.
        builder.fragment(:state_response_tail) do
          # Узел просто возвращает существующий `state[:response]` без дополнительной сборки.
          node :respond, kind: :state_response

          # Это тоже точка завершения fragment'а.
          finish_point :respond
        end
      end
    end
  end
end
