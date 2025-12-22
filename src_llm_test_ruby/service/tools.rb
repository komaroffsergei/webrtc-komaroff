require_relative 'mcp_tools'
require 'json'
require 'faraday'

module LLMTestRuby
  module Tools
    extend self

    API_BASE = 'http://127.0.0.1:8100/api'.freeze
    @artifacts = {}

    # Сначала определяем все методы инструментов
    def get_current_position
      uri = URI("#{API_BASE}/pilot/location")
      response = Net::HTTP.get_response(uri)

      raise "API error: #{response.code}" unless response.is_a?(Net::HTTPSuccess)

      pos = JSON.parse(response.body)
      @artifacts[:current_position] = pos

      [true, {
        status: 'ok',
        artifact_key: 'current_position'
      }]
    end

    def search_nearest_airports(radius_km:)
      unless @artifacts[:current_position]
        return [true, {
          status: 'error',
          message: 'Необходимо сначала выполнить запрос текущей гео-позиции пользователя'
        }]
      end

      pos = @artifacts[:current_position]
      uri = URI("#{API_BASE}/airports/nearest")

      params = {
        lat: pos['lat'],
        lon: pos['lon'],
        radius_km: radius_km,
        status: 'open'
      }

      uri.query = URI.encode_www_form(params)
      response = Net::HTTP.get_response(uri)

      raise "API error: #{response.code}" unless response.is_a?(Net::HTTPSuccess)

      res = JSON.parse(response.body)['results']
      @artifacts[:selected_airports] = res

      [true, {
        status: 'ok',
        artifact_key: 'selected_airports',
        count: res.length,
        message: "Найдено #{res.length} ближайших аэродрома к заданным координатам"
      }]
    end

    def select_airport_with_shortest_runway(require_runway_status: nil, surface: nil)
      unless @artifacts[:selected_airports]
        return [true, {
          status: 'error',
          message: 'Необходимо сначала выполнить поиск аэродромов'
        }]
      end

      selected = nil
      shortest_length = nil

      @artifacts[:selected_airports].each do |airport|
        airport['runways'].each do |runway|
          next if require_runway_status && runway['status'] != require_runway_status
          next if surface && runway['surface'] != surface

          length = runway['length_m']
          if shortest_length.nil? || length < shortest_length
            shortest_length = length
            selected = {
              **airport,
              'runways' => [runway]
            }
          end
        end
      end

      unless selected
        return [false, {
          status: 'error',
          message: 'Не найдено ВПП, подходящих под условия'
        }]
      end

      @artifacts[:selected_airports] = [selected]

      [false, {
        status: 'ok',
        selected_airport_id: selected['id'],
        shortest_runway_length_m: shortest_length
      }]
    end

    def build_route_to_first_airport
      unless @artifacts[:current_position]
        return [true, {
          status: 'error',
          message: 'Необходимо сначала выполнить запрос текущей гео-позиции пользователя'
        }]
      end

      unless @artifacts[:selected_airports]
        return [true, {
          status: 'error',
          message: 'Необходимо сначала выполнить поиск аэродромов'
        }]
      end

      pos = @artifacts[:current_position]
      airport = @artifacts[:selected_airports].first

      uri = URI("#{API_BASE}/routes/build")
      params = {
        start_lat: pos['lat'],
        start_lon: pos['lon'],
        end_lat: airport['lat'],
        end_lon: airport['lon']
      }

      uri.query = URI.encode_www_form(params)
      response = Net::HTTP.get_response(uri)

      raise "API error: #{response.code}" unless response.is_a?(Net::HTTPSuccess)

      route = JSON.parse(response.body)
      @artifacts[:route] = route

      [false, route]
    end

    # Теперь регистрируем все инструменты, после определения методов
    McpTools.mcp_tool(
      name: 'get_current_position',
      description: 'Получает текущую позицию пользователя',
      provides: ['current_position']
    ).call(method(:get_current_position))

    McpTools.mcp_tool(
      name: 'search_nearest_airports',
      description: 'Поиск ближайших открытых аэропортов',
      consumes: ['current_position'],
      provides: ['airports'],
      parameters: {
        radius_km: 'Радиус поиска в километрах'
      }
    ).call(method(:search_nearest_airports))

    McpTools.mcp_tool(
      name: 'select_airport_with_shortest_runway',
      description: 'Выбирает аэропорт с самой короткой взлётно-посадочной полосой из ранее найденных аэропортов.',
      consumes: ['selected_airports'],
      provides: ['selected_airports'],
      parameters: {
        require_runway_status: 'Если указано, учитывать только ВПП с данным статусом: free, busy или closed',
        surface: 'Если указано, учитывать только ВПП с данным материалом: concrete или asphalt'
      }
    ).call(method(:select_airport_with_shortest_runway))

    McpTools.mcp_tool(
      name: 'build_route_to_first_airport',
      description: 'Построение маршрута от текущей позиции до выбранного аэропорта',
      consumes: ['current_position', 'selected_airports'],
      provides: ['route']
    ).call(method(:build_route_to_first_airport))

    def artifacts
      @artifacts
    end
  end
end
