module LLMTestRuby
  module McpTools
    extend self

    @registry = {}

    def registry
      @registry
    end

    def mcp_tool(name: nil, description: nil, provides: [], consumes: [], parameters: {})
      proc do |fn|
        tool_name = name || fn.name
        @registry[tool_name.to_sym] = {
          fn: fn,
          schema: build_schema(fn, tool_name, description, parameters),
          provides: provides,
          consumes: consumes
        }
      end
    end

    private

    def build_schema(fn, name, description, param_desc)
      properties = {}
      required = []

      # Получаем параметры метода
      fn.parameters.each do |type, param_name|
        param_info = {
          'type' => 'string' # по умолчанию
        }

        if param_desc && param_desc[param_name.to_s]
          param_info['description'] = param_desc[param_name.to_s]
        end

        properties[param_name.to_s] = param_info

        # Если параметр обязателен (не имеет значения по умолчанию)
        required << param_name.to_s if type == :req
      end

      {
        'type' => 'function',
        'function' => {
          'name' => name,
          'description' => description || '',
          'parameters' => {
            'type' => 'object',
            'properties' => properties,
            'required' => required
          }
        }
      }
    end
  end
end
