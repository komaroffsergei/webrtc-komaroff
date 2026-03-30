# frozen_string_literal: true

module SrcLanggraphRbNode
  module Scenarios
    # Базовый контейнер для общих helper-методов сценариев.
    # Он не знает ничего о конкретном домене, а лишь унифицирует работу
    # с runtime-ответами и извлечением данных из общих структур.
    class BaseNodes
      private

      # Собирает стандартный done-response, которым сценарий сообщает
      # runtime, что работа завершена и пользователю можно вернуть финальный текст.
      def done_response(req, message, client_events: [])
        Runtime::Responses.done_response(req, message, client_events: client_events)
      end

      # Собирает partial-response, когда сценарий пока не закончен
      # и должен дождаться дополнительных данных от пользователя.
      def partial_response(req, prompt, active_workflow_id:, pending:)
        Runtime::Responses.partial_response(
          req,
          prompt,
          active_workflow_id: active_workflow_id,
          pending: pending
        )
      end

      # Собирает унифицированный failed-response для ошибок сценария.
      # client_handler опционален и нужен, если UI должен показать ошибку
      # отдельным клиентским действием поверх обычного текстового ответа.
      def failed_response(req, code:, message:, client_handler: nil)
        Runtime::Responses.failed_response(
          req,
          code: code,
          message: message,
          client_handler: client_handler
        )
      end

      # Извлекает финальный текст из ответа LLM.
      # Возвращает нормализованную строку без внешних пробелов
      # или пустую строку, если runtime не прислал ожидаемое поле.
      def extract_llm_text(resp)
        data = Runtime::Util.extract_hash(resp[:data])
        value = data[:response_text]
        value.is_a?(String) ? value.strip : ""
      end

      # Извлекает вложенный hash из payload формата { data: { ... } }.
      # Это позволяет сценариям не дублировать одинаковую распаковку
      # ответов инструментов и runtime-оберток.
      def extract_nested_data(payload)
        data = Runtime::Util.extract_hash(payload)
        inner = data[:data]
        inner.is_a?(Hash) ? Runtime::Util.extract_hash(inner) : nil
      end
    end
  end
end
