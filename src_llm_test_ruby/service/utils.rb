# frozen_string_literal: true

require 'json'
require_relative 'settings'

module LLMTestRuby
  module Utils
    extend self

    def log_user_query(text)
      puts "[DEBUG][USER] #{text}" if Settings::DEBUG
    end

    def log_system_prompt
      puts '[DEBUG][SYSTEM] system prompt sent' if Settings::DEBUG
    end

    def log_step(step)
      puts "[DEBUG][STEP #{step}]" if Settings::DEBUG
    end

    def log_llm_response(content, tool_calls)
      if content
        puts "[DEBUG][LLM][thinking]"
        puts content.strip if Settings::DEBUG
      end

      if tool_calls
        puts "[DEBUG][LLM][tool_calls]"
        puts JSON.pretty_generate(tool_calls) if Settings::DEBUG
      end
    end

    def log_tool_call(name, args)
      puts "[DEBUG][TOOL CALL] #{name}"
      puts JSON.pretty_generate(args) if Settings::DEBUG
    end

    def log_tool_result(name, result)
      puts "[DEBUG][TOOL RESULT] #{name}"
      puts JSON.pretty_generate(result) if Settings::DEBUG
    end

    def log_error(err)
      puts "[DEBUG][ERROR]"
      puts err.message
      puts err.backtrace.join("\n") if Settings::DEBUG
    end

    def log_final_answer(answer)
      puts "[DEBUG][FINAL ANSWER]"
      puts answer
    end

    def log_stats(steps, total_time)
      puts "[DEBUG][STATS] steps=#{steps} time=#{'%.3f' % total_time}s" if Settings::DEBUG
    end

    # Вспомогательные методы
    def normalize_tool_calls(tool_calls)
      return [] unless tool_calls

      tool_calls.map do |call|
        {
          name: call['function']['name'],
          arguments: JSON.parse(call['function']['arguments'])
        }
      end
    end

    def normalize_args(fn, args)
      normalized = {}

      fn.parameters.each do |type, param_name|
        next unless args.key?(param_name.to_s)

        value = args[param_name.to_s]
        param_sym = param_name.to_sym

        begin
          case param_sym
          when :radius_km
            normalized[param_sym] = extract_number(value).to_f
          when :require_runway_status, :surface
            normalized[param_sym] = value.to_s if value
          else
            normalized[param_sym] = value
          end
        rescue => e
          raise "Parameter #{param_name}=#{value} (#{e.message})"
        end
      end

      normalized
    end

    private

    def extract_number(str)
      match = str.to_s.match(/-?\d+(\.\d+)?/)
      match ? match[0] : str
    end
  end
end
