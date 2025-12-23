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
    def display_result(artifact_keys:)
      raise "artifact_keys must be Array" unless artifact_keys.is_a?(Array)

      result = {}

      artifact_keys.each do |key|
        sym = key.to_sym
        unless artifacts.key?(sym)
          raise "Artifact #{sym} not found"
        end

        result[sym] = artifacts[sym]
      end

      [
        false, # ⛔️ ФИНАЛ
        {
          status: "ok",
          result: result
        }
      ]
    end




    def get_current_position
      resp = http.get('pilot/location')
      pos = JSON.parse(resp.body)
      artifacts[:current_position] = pos

      [true, { status: 'ok', artifact_key: 'current_position' }]
    end

    def search_nearest_airports(radius_km)
      unless artifacts[:current_position]
        return [true, { status: 'error', code: 'NO_CURRENT_POSITION', message: 'Сначала нужно получить текущую позицию' }]
      end

      pos = artifacts[:current_position]
      resp = http.get('airports/nearest', { lat: pos['lat'], lon: pos['lon'], radius_km: radius_km })
      res = JSON.parse(resp.body)

      artifacts[:selected_airports] = res['results']

      [true, {
        status: 'ok',
        artifact_key: 'selected_airports',
        count: res.length,
        message: "Найдено #{res.length} ближайших аэродрома к заданным координатам"
      }]
    end

    def select_airport_with_shortest_runway
      airports = artifacts[:selected_airports]

      unless airports.is_a?(Array)
        return [true, {
          status: 'error',
          message: 'Ожидался массив аэропортов в artifacts[:selected_airports]'
        }]
      end

      selected = nil
      shortest_length = nil

      airports.each do |entry|
        airport =
          case entry
          when Hash
            entry
          when Array
            entry.first
          else
            next
          end

        next unless airport.is_a?(Hash)

        runways = airport['runways']
        next unless runways.is_a?(Array)

        runways.each do |runway|
          next unless runway.is_a?(Hash)

          length = runway['length_m']
          next unless length.is_a?(Numeric)

          if shortest_length.nil? || length < shortest_length
            shortest_length = length
            selected = airport.merge('runways' => [runway])
          end
        end
      end

      unless selected
        return [false, {
          status: 'error',
          message: 'Не удалось найти ВПП с корректной длиной'
        }]
      end

      artifacts[:selected_airports] = [selected]

      [
        true, # true -> to display_result
        {
          status: 'ok',
          selected_airport_id: selected['id'],
          shortest_runway_length_m: shortest_length
        }
      ]
    end

    def select_airport_with_shortest_runway_by_status(require_runway_status)
      unless artifacts[:selected_airports]
        return [true, {
          status: 'error',
          message: 'Необходимо сначала выполнить поиск аэродромов'
        }]
      end

      unless require_runway_status
        return [false, {
          status: 'error',
          message: 'Не указан обязательный статус ВПП'
        }]
      end

      selected = nil
      shortest_length = nil

      artifacts[:selected_airports].each do |airport|
        airport['runways'].each do |runway|
          next if runway['status'] != require_runway_status

          length = runway['length_m']
          next unless length

          if shortest_length.nil? || length < shortest_length
            shortest_length = length
            selected = airport.merge('runways' => [runway])
          end
        end
      end

      unless selected
        return [false, {
          status: 'error',
          message: "Не найдено ВПП со статусом #{require_runway_status}"
        }]
      end

      artifacts[:selected_airports] = [selected]

      [
        false,
        {
          status: 'ok',
          selected_airport_id: selected['id'],
          shortest_runway_length_m: shortest_length,
          runway_status: require_runway_status
        }
      ]
    end

    def select_airport_with_shortest_runway_by_surface(surface, require_runway_status: nil)
      unless artifacts[:selected_airports]
        return [true, { status: 'error', message: 'Необходимо сначала выполнить поиск аэродромов' }]
      end

      selected = nil
      shortest_length = nil

      artifacts[:selected_airports].each do |airport|
        airport['runways'].each do |runway|
          next if runway['surface'] != surface
          next if require_runway_status && runway['status'] != require_runway_status

          length = runway['length_m']
          if shortest_length.nil? || length < shortest_length
            shortest_length = length
            selected = airport.merge('runways' => [runway])
          end
        end
      end

      unless selected
        return [false, {
          status: 'error',
          message: "Не найдено ВПП с покрытием #{surface}"
        }]
      end

      artifacts[:selected_airports] = [selected]

      [
        false,
        {
          status: 'ok',
          selected_airport_id: selected['id'],
          shortest_runway_length_m: shortest_length,
          surface: surface
        }
      ]
    end


    def build_route_to_first_airport
      unless artifacts[:current_position].is_a?(Hash)
        return [true, {
          status: 'error',
          message: 'Сначала нужно получить текущую позицию'
        }]
      end

      airports = artifacts[:selected_airports]
      unless airports.is_a?(Array) && airports.any?
        return [true, {
          status: 'error',
          message: 'Сначала нужно выбрать аэропорт'
        }]
      end

      # --- нормализация аэропорта ---
      raw_airport = airports.first

      airport =
        case raw_airport
        when Hash
          raw_airport
        when Array
          raw_airport.first
        else
          nil
        end

      unless airport.is_a?(Hash)
        return [false, {
          status: 'error',
          message: 'Некорректная структура данных аэропорта'
        }]
      end

      start = artifacts[:current_position]

      route = {
        from: start,
        to: {
          'id'   => airport['id'],
          'name' => airport['name'],
          'lat'  => airport['lat'],
          'lon'  => airport['lon']
        },
        distance_km: 42.0 # заглушка
      }

      artifacts[:route] = route

      [
        false,
        {
          status: 'ok',
          artifact_key: 'route',
          route: route
        }
      ]
    end

    # -----------------------------
    # MCP REGISTRATION
    # -----------------------------
    McpTools.mcp_tool(
      name: 'display_result',
      description: 'Возвращает форматированный ответ пользователю после выполнения всех требуемых операций. в параметр artifact_keys передаются ключи артефактов используемые для получения результатов',
      parameters: {
        'artifact_keys' => 'Массив ключей артефактов используемых при получении ответа'
      }
    ).call(method(:display_result))


    McpTools.mcp_tool(
      name: 'get_current_position',
      description: 'Получает текущую позицию пользователя',
      provides: ['current_position'],
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
      description: 'Выбирает аэропорт с самой короткой ВПП без учёта статуса',
      consumes: ['selected_airports'],
      provides: ['selected_airports'],
      parameters: {}
    ).call(method(:select_airport_with_shortest_runway))


    McpTools.mcp_tool(
      name: 'select_airport_with_shortest_runway_by_status',
      description: 'Выбирает аэропорт с самой короткой ВПП с учётом статуса',
      consumes: ['selected_airports'],
      provides: ['selected_airports'],
      parameters: {
        'require_runway_status' => 'Обязательный статус ВПП: free, busy или closed'
      }
    ).call(method(:select_airport_with_shortest_runway_by_status))


    McpTools.mcp_tool(
      name: 'select_airport_with_shortest_runway_by_surface',
      description: 'Выбирает аэропорт с самой короткой ВПП по материалу покрытия',
      consumes: ['selected_airports'],
      provides: ['selected_airports'],
      parameters: {
        'surface' => 'Материал покрытия ВПП: concrete или asphalt',
        'require_runway_status' => 'Учитывать только ВПП с данным статусом: free, busy или closed'
      }
    ).call(method(:select_airport_with_shortest_runway_by_surface))


    McpTools.mcp_tool(
      name: 'build_route_to_first_airport',
      description: 'Строит маршрут от текущей позиции до выбранного аэропорта',
      consumes: ['current_position', 'selected_airports'],
      provides: ['route']
    ).call(method(:build_route_to_first_airport))
  end
end
