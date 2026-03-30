# frozen_string_literal: true

require_relative "nodes"

module SrcLanggraphRbNode
  module Scenarios
    module WhereMyFlight
      class Graph
        # Строит граф сценария получения статуса рейса.
        # Граф умеет либо спросить недостающие параметры, либо вызвать tool lookup,
        # либо отдать управление другому сценарию через reroute.
        def self.build
          # Экземпляр Nodes предоставляет обработчики всех вершин графа.
          nodes = Nodes.new

          AsyncGraph::Graph.new do
            # Пытаемся извлечь из пользовательского ввода параметры поиска рейса.
            node :collect_params, &nodes.method(:collect_params)
            # Определяем следующий шаг после извлечения параметров.
            node :route_after_collect, &nodes.method(:route_after_collect)
            # Спрашиваем недостающие данные у пользователя.
            node :ask_missing, &nodes.method(:ask_missing)
            # Вызываем tool статуса рейса при достаточных параметрах.
            node :call_status_tool, &nodes.method(:call_status_tool)
            # Определяем финальную ветку после ответа инструмента.
            node :route_after_tool, &nodes.method(:route_after_tool)
            # Возвращаем успешный финальный ответ.
            node :emit_final_response, &nodes.method(:emit_final_response)
            # Возвращаем осмысленный ответ для случая "ничего не найдено".
            node :emit_not_found_response, &nodes.method(:emit_not_found_response)
            # Возвращаем стандартизированную ошибку сценария.
            node :emit_failed_response, &nodes.method(:emit_failed_response)
            # Передаем выполнение в другой сценарий, если текущий контекст ушел в сторону.
            node :reroute, &nodes.method(:reroute)

            # Входная точка сценария всегда сбор параметров.
            set_entry_point :collect_params
            # После сбора параметров нужно решить, куда идти дальше.
            edge :collect_params, :route_after_collect
            # После tool lookup тоже нужен отдельный routing-узел.
            edge :call_status_tool, :route_after_tool
            # Все терминальные состояния графа.
            set_finish_point :ask_missing
            set_finish_point :emit_final_response
            set_finish_point :emit_not_found_response
            set_finish_point :emit_failed_response
            set_finish_point :reroute
          end
        end
      end
    end
  end
end
