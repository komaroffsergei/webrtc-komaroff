# frozen_string_literal: true

require 'json'
require 'faraday'
require_relative 'mcp_tools'

module LLMTestRuby
  module Tools
    extend self

    API_BASE = 'http://127.0.0.1:8100/api'

    def artifacts
      @artifacts ||= {}
    end

    def reset!
      @artifacts = {}
    end

    def http
      @http ||= Faraday.new(url: API_BASE) do |f|
        f.response :raise_error
        f.adapter Faraday.default_adapter
      end
    end

    # -----------------------------
    # TOOL METHODS
    # -----------------------------
    def display_airports
      [false, { status: 'ok', result: artifacts[:selected_airports] }]
    end

    def get_current_position
      resp = http.get('pilot/location')
      pos = JSON.parse(resp.body)
      artifacts[:current_position] = pos

      [true, { status: 'ok', artifact_key: 'current_position' }]
    end

    def search_nearest_airports(radius_km:)
      unless artifacts[:current_position]
        return [true, { status: 'error', code: 'NO_CURRENT_POSITION', message: 'Сначала нужно получить текущую позицию' }]
      end

      pos = artifacts[:current_position]
      resp = http.get('airports/nearest', { lat: pos['lat'], lon: pos['lon'], radius_km: radius_km })
      res = JSON.parse(resp.body)

      artifacts[:selected_airports] = res

      [true, {
        status: 'ok',
        artifact_key: 'selected_airports',
        count: res.length,
        message: "Найдено #{res.length} ближайших аэродрома к заданным координатам"
      }]
    end

    def select_airport_with_shortest_runway(require_runway_status: nil, surface: nil)
      unless artifacts[:selected_airports]
        return [true, { status: 'error', message: 'Необходимо сначала выполнить поиск аэродромов' }]
      end

      selected = nil
      shortest_length = nil

      artifacts[:selected_airports].each do |airport|
        airport['runways'].each do |runway|
          next if require_runway_status && runway['status'] != require_runway_status
          next if surface && runway['surface'] != surface

          length = runway['length_m']
          if shortest_length.nil? || length < shortest_length
            shortest_length = length
            selected = airport.merge('runways' => [runway])
          end
        end
      end

      unless selected
        return [false, { status: 'error', message: 'Не найдено ВПП, подходящих под условия' }]
      end

      artifacts[:selected_airports] = [selected]

      [false, {
        status: 'ok',
        selected_airport_id: selected['id'],
        shortest_runway_length_m: shortest_length
      }]
    end

    def build_route_to_first_airport
      unless artifacts[:current_position]
        return [true, { status: 'error', message: 'Сначала нужно получить текущую позицию' }]
      end
      unless artifacts[:selected_airports]&.any?
        return [true, { status: 'error', message: 'Сначала нужно выбрать аэропорт' }]
      end

      start = artifacts[:current_position]
      airport = artifacts[:selected_airports].first


      route = {
        from: start,
        to: airport.slice('id', 'name', 'lat', 'lon'),
        distance_km: 42.0
      }

      artifacts[:route] = route
      [false, { status: 'ok', artifact_key: 'route', route: route }]
    end

    # -----------------------------
    # MCP REGISTRATION
    # -----------------------------

    McpTools.mcp_tool(
      name: 'get_current_position',
      description: 'Получает текущую позицию пользователя',
      provides: ['current_position']
    ).call(method(:get_current_position))

    McpTools.mcp_tool(
      name: 'search_nearest_airports',
      description: 'Ищет ближайшие аэропорты в радиусе от текущей позиции',
      consumes: ['current_position'],
      provides: ['selected_airports'],
      parameters: {
        'radius_km' => 'Радиус поиска в километрах'
      }
    ).call(method(:search_nearest_airports))

    McpTools.mcp_tool(
      name: 'select_airport_with_shortest_runway',
      description: 'Выбирает аэропорт с самой короткой ВПП среди найденных',
      consumes: ['selected_airports'],
      provides: ['selected_airports'],
      parameters: {
        'require_runway_status' => 'Если указано, учитывать только ВПП с данным статусом: free, busy или closed',
        'surface' => 'Если указано, учитывать только ВПП с данным материалом: concrete или asphalt'
      }
    ).call(method(:select_airport_with_shortest_runway))

    McpTools.mcp_tool(
      name: 'build_route_to_first_airport',
      description: 'Строит маршрут от текущей позиции до выбранного аэропорта',
      consumes: ['current_position', 'selected_airports'],
      provides: ['route']
    ).call(method(:build_route_to_first_airport))
  end
end
