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


    def initialize
      config = Ollama::Client::Config[
        base_url: Settings::OLLAMA_URL,
        output: $stdout,
        connect_timeout: 60,
        read_timeout: 300
      ]

      # Initialize client using the configuration
      @client = Ollama::Client.configure_with(config)
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
      final_result = nil
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


          message_data = response[:message]
          messages << message_data

          content = message_data[:content] || ''
          thinking = message_data[:thinking] || ''
          tool_calls = message_data[:tool_calls] || []

          Utils.log_llm_response(content, thinking, tool_calls)

          if tool_calls.any?
            tool_results = handle_tool_calls(tool_calls, session_id, intent_id)






            tool_results.each do |result|
              content_str = result[:content].respond_to?(:to_json) ?
                              result[:content].to_json :
                              result[:content].to_s

              messages << {
                role: 'tool',
                name: result[:tool_name],
                content: content_str
              }
            end

            final_tool = tool_results.find do |r|
              r[:continue] == false || r[:tool_name] == 'display_result'
            end


            if final_tool
              final_result = final_tool[:content]
              break
            end


          else
            raise "LLM finished without calling display_result. Textual final answer is forbidden."
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

      # === ИСПРАВЛЕНО: правильное извлечение финального ответа ===
      final_answer =
        if final_result
          final_result
        else
          raise "Agent finished without display_result"
        end


      Utils.log_final_answer(final_answer)

      DB.finish_intent(session_id, intent_id, final_answer)
      DB.finish_session(session_id)

      total_time = Process.clock_gettime(Process::CLOCK_MONOTONIC) - start_time
      Utils.log_stats(steps, total_time)

      final_answer
    end

    private

    def call_llm(model, messages)
      # === ИСПРАВЛЕНО: гарантируем непотоковый ответ ===
      response = @client.chat(
        model: model,
        messages: sanitize_messages(messages),
        tools: McpTools.registry.values.map { |tool| tool[:schema] },
        options: { temperature: 0.0 },
        stream: false,
        # think: false
      )

      # Если ответ приходит в потоковом формате даже при stream: false
      if response.is_a?(Enumerator)
        full_response = {
          message: {
            role: 'assistant',
            content: '',
            tool_calls: []
          },
          model: model,
          created_at: Time.now.utc.iso8601
        }

        response.each do |chunk|
          if chunk.respond_to?(:message) && chunk.message.respond_to?(:content)
            full_response[:message][:content] << chunk.message.content
          end

          if chunk.respond_to?(:message) && chunk.message.respond_to?(:tool_calls)
            full_response[:message][:tool_calls] = chunk.message.tool_calls
          end
        end

        return OpenStruct.new(
          message: OpenStruct.new(
            role: full_response[:message][:role],
            content: full_response[:message][:content],
            tool_calls: full_response[:message][:tool_calls]
          ),
          model: full_response[:model],
          created_at: full_response[:created_at]
        )
      end

      response
    end

    # === ИСПРАВЛЕНО: очистка сообщений для API ===
    def sanitize_messages(messages)
      messages.map do |msg|
        case msg[:role] || msg['role']
        when 'system', 'user', 'assistant'
          {
            role: (msg[:role] || msg['role']).to_s,
            content: (msg[:content] || msg['content'] || '').to_s
          }
        when 'tool'
          {
            role: 'tool',
            name: (msg[:name] || msg['name'] || '').to_s,
            content: (msg[:content] || msg['content'] || '').to_s
          }
        else
          {
            role: 'user',
            content: (msg[:content] || msg['content'] || msg.to_s)
          }
        end
      end
    end

    def handle_tool_calls(tool_calls, session_id, intent_id)
      normalized_calls = Utils.normalize_tool_calls(tool_calls)
      results = []

      normalized_calls.each do |call|
        tool_name = call[:name]
        args = call[:arguments]

        Utils.log_tool_call(tool_name, args)

        begin
          tool_info = McpTools.registry[tool_name.to_sym]
          unless tool_info
            raise "Инструмент '#{tool_name}' не найден в реестре"
          end

          tool = tool_info[:fn]
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
            content: { error: e.message, arguments: args },
            continue: false
          }
        end
      end

      results
    end

    # === ИСПРАВЛЕНО: обработка объектов Ollama::Response ===
    def extract_ollama_message(response)
      if response.respond_to?(:message)
        {
          role: (response.message.role rescue 'assistant'),
          content: (response.message.content rescue response.message.thinking rescue ''),
          tool_calls: (response.message.tool_calls rescue [])
        }
      elsif response.is_a?(Hash) && response.key?('message')
        {
          role: response['message']['role'],
          content: response['message']['content'],
          tool_calls: response['message']['tool_calls'] || []
        }
      else
        {
          role: 'assistant',
          content: response.to_s,
          tool_calls: []
        }
      end.transform_keys(&:to_sym)
    end

    # === ИСПРАВЛЕНО: безопасное извлечение финального ответа ===
    def extract_final_answer(response)
      if response.respond_to?(:message) && response.message.respond_to?(:content)
        response.message.content.strip
      elsif response.is_a?(Hash) && response.dig('message', 'content')
        response.dig('message', 'content').strip
      else
        'Не удалось извлечь ответ из ответа модели'
      end
    end
  end
end
