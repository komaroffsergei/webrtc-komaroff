# frozen_string_literal: true

require_relative "nodes"

module SrcLanggraphRbNode
  module Scenarios
    module FindNearestAirport
      class Graph
        # Строит ориентированный граф шагов для сценария поиска аэропорта.
        # В этом классе описывается только topology: сами действия живут в Nodes.
        def self.build
          # Один экземпляр Nodes предоставляет callables для всех нод графа.
          nodes = Nodes.new

          AsyncGraph::Graph.new do
            # Запрашиваем текущую позицию пользователя.
            node :get_position, &nodes.method(:get_position)
            # Выбираем дальнейший путь после получения позиции.
            node :route_after_position, &nodes.method(:route_after_position)
            # Готовим параметры для поиска ближайших аэропортов.
            node :prepare_airport_search, &nodes.method(:prepare_airport_search)
            # Вызываем инструмент поиска аэропортов.
            node :search_airports, &nodes.method(:search_airports)
            # Ветвим сценарий после поиска аэропортов.
            node :route_after_search, &nodes.method(:route_after_search)
            # Готовим аргументы для построения маршрута.
            node :prepare_route, &nodes.method(:prepare_route)
            # Ветвим сценарий после подготовки аргументов маршрута.
            node :route_after_route_args, &nodes.method(:route_after_route_args)
            # Вызываем инструмент построения маршрута.
            node :build_route, &nodes.method(:build_route)
            # Ветвим сценарий после ответа инструмента маршрута.
            node :route_after_build_route, &nodes.method(:route_after_build_route)
            # Формируем финальный успешный ответ.
            node :emit_final_response, &nodes.method(:emit_final_response)
            # Финальные fail-ноды для разных стадий сценария.
            node :position_failed, &nodes.method(:position_failed)
            node :search_failed, &nodes.method(:search_failed)
            node :route_args_failed, &nodes.method(:route_args_failed)
            node :build_route_failed, &nodes.method(:build_route_failed)

            # Сценарий стартует с определения текущей позиции.
            set_entry_point :get_position
            # После вызова get_position переходим в routing-узел.
            edge :get_position, :route_after_position
            # После подготовки параметров поиска запускаем сам поиск.
            edge :prepare_airport_search, :search_airports
            # После поиска аэропортов выбираем следующую ветку.
            edge :search_airports, :route_after_search
            # После подготовки маршрута проверяем, можно ли строить его дальше.
            edge :prepare_route, :route_after_route_args
            # После вызова build_route проверяем результат отдельно.
            edge :build_route, :route_after_build_route
            # Все терминальные состояния графа.
            set_finish_point :emit_final_response
            set_finish_point :position_failed
            set_finish_point :search_failed
            set_finish_point :route_args_failed
            set_finish_point :build_route_failed
          end
        end
      end
    end
  end
end
