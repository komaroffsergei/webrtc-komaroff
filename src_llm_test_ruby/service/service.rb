# frozen_string_literal: true

require 'ollama'
require_relative 'settings'
require_relative 'db'
require_relative 'tools'
require_relative 'utils'
require_relative 'mcp_tools'

module LLMTestRuby
  class Service
    MAX_STEPS = 10
    SYSTEM_PROMPT = <<-PROMPT.freeze
      Ты — MCP агент.

      Правила работы:
      - НИКОГДА НЕ возвращай JSON в content, придерживаясь вызова инструмента.
      - НИКОГДА НЕ выдумывай значения-заглушки.
      - НИКОГДА НЕ выдумывай параметры.
      - НИКОГДА НЕ запрашивай значения у пользователя.
      - НИКОГДА НЕ повторяй тот же вызов с теми же аргументами после ошибки.
      - ВСЕГДА СТРОГО соблюдай тип данных параметров.

      ПРАВИЛО ГЕОПОЗИЦИИ (ОБЯЗАТЕЛЬНО):
      Если запрос пользователя:
      - содержит слова: радиус, км, расстояние, ближайший, аэропорт
      - или требует географического расчёта
      ТО:
      - ТЫ ОБЯЗАН первым действием вызвать get_current_position
      - ЗАПРЕЩЕНО использовать любые координаты, полученные ранее
      - ЗАПРЕЩЕНО продолжать рассуждение без этого вызова

      Перед каждым действием пиши в content: РАССУЖДЕНИЕ: и кратко объясняй, что ты собираешься делать.
      Ограничения:
      - НИКОГДА НЕ пиши текст в поле content при вызове инструментов.
      - НИКОГДА НЕ описывай вызовы инструментов обычным текстом.

      В завершение: ВЕРНИ финальный ответ обычным текстом на русском языке.
    PROMPT

    def initialize
      config = Ollama::Client::Config[
        base_url: Settings::OLLAMA_URL,
        output: $stdout,
        connect_timeout: 15,
        read_timeout: 300
      ]

      # Initialize client using the configuration
      @client = Ollama::Client.configure_with(config)
      # @client = Ollama::Client.new(host: Settings::OLLAMA_URL, timeout: 60)
      @log = Logger.new(STDOUT)
    end

    def run_model(model, user_query, user_id = Settings::USER_ID)
      start_time = Process.clock_gettime(Process::CLOCK_MONOTONIC)
      session_id = DB.create_session(user_id)
      intent_id = nil
      messages = [
        { role: 'system', content: SYSTEM_PROMPT },
        { role: 'user', content: user_query }
      ]

      Utils.log_user_query(user_query)
      Utils.log_system_prompt

      steps = 0
      last_response = nil

      MAX_STEPS.times do |step|
        steps += 1
        Utils.log_step(step + 1)

        intent_id = DB.create_intent(
          session_id: session_id,
          user_id: user_id,
          intent_type: 'GENERIC_QUERY'
        )

        begin
          response = call_llm(model, messages)
          last_response = response
          messages << response['message']

          Utils.log_llm_response(
            response['message']['content'],
            response['message']['tool_calls']
          )

          if response['message']['tool_calls'].present?
            tool_results = handle_tool_calls(
              response['message']['tool_calls'],
              session_id,
              intent_id
            )

            tool_results.each do |result|
              messages << {
                role: 'tool',
                tool_name: result[:tool_name],
                content: result[:content].to_json
              }
            end

            break unless tool_results.any? { |r| r[:continue] }
          else
            break
          end
        rescue => e
          Utils.log_error(e)
          DB.log_event(
            session_id: session_id,
            intent_id: intent_id,
            seq: step,
            role: 'SYSTEM',
            event_type: 'ERROR',
            name: model,
            input_data: nil,
            output_data: { error: e.message }
          )
          break
        end
      end

      final_answer = last_response&.dig('message', 'content') || 'Не удалось получить ответ'
      Utils.log_final_answer(final_answer)

      DB.finish_intent(session_id, intent_id, final_answer)
      DB.finish_session(session_id)

      total_time = Process.clock_gettime(Process::CLOCK_MONOTONIC) - start_time
      Utils.log_stats(steps, total_time)

      final_answer
    end

    private

    def call_llm(model, messages)
      @client.chat(
        model: model,
        messages: messages,
        tools: McpTools.registry.values.map { |tool| tool[:schema] },
        options: { temperature: 0.0 }
      )
    end

    def handle_tool_calls(tool_calls, session_id, intent_id)
      normalized_calls = Utils.normalize_tool_calls(tool_calls)
      results = []

      normalized_calls.each do |call|
        tool_name = call[:name]
        args = call[:arguments]

        Utils.log_tool_call(tool_name, args)

        begin
          tool = Tools.registry[tool_name.to_sym]
          safe_args = Utils.normalize_args(tool, args)
          continue, result = tool.call(**safe_args)

          DB.log_artifact(
            session_id: session_id,
            intent_id: intent_id,
            artifact_type: 'tool_result',
            name: tool_name,
            data: { arguments: safe_args, result: result }
          )

          Utils.log_tool_result(tool_name, result)

          results << {
            tool_name: tool_name,
            content: result,
            continue: continue
          }
        rescue => e
          Utils.log_error(e)
          results << {
            tool_name: tool_name,
            content: { error: e.message },
            continue: false
          }
        end
      end

      results
    end
  end
end
