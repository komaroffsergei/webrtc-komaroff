# frozen_string_literal: true

require_relative "nodes"

module SrcLanggraphRbNode
  module Scenarios
    module FreeSpeech
      class Graph
        # Строит компактный граф свободного диалога.
        # Граф либо просит уточнить неоднозначную ссылку, либо сразу формирует ответ.
        def self.build
          # Объект Nodes содержит исполняемую логику всех вершин графа.
          nodes = Nodes.new

          AsyncGraph::Graph.new do
            # Анализируем контекст и разрешаем референции пользователя.
            node :prepare_context, &nodes.method(:prepare_context)
            # Выбираем следующую ветку после подготовки контекста.
            node :route_after_prepare, &nodes.method(:route_after_prepare)
            # Возвращаем уточняющий вопрос при неоднозначной ссылке.
            node :clarify_reference, &nodes.method(:clarify_reference)
            # Генерируем содержательный ответ пользователю.
            node :compose_response, &nodes.method(:compose_response)
            # Упаковываем текст ответа в runtime done-response.
            node :emit_final_response, &nodes.method(:emit_final_response)

            # Входная точка сценария.
            set_entry_point :prepare_context
            # После подготовки контекста всегда выполняем routing.
            edge :prepare_context, :route_after_prepare
            # После генерации текста завершаем сценарий финальным response.
            edge :compose_response, :emit_final_response
            # Терминальные состояния графа.
            set_finish_point :clarify_reference
            set_finish_point :emit_final_response
          end
        end
      end
    end
  end
end
