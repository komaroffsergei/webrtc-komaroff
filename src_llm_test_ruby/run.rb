# frozen_string_literal: true

require "json"
require_relative "service/service"

MODELS = [
  "qwen3:0.6b",
  # "qwen2.5:7b",
  # "qwen3:1.7b",
].freeze

QUERIES = [
  # "Найди аэропорт в радиусе 250 км с самой короткой ВПП",
  "Найди ближайший открытый аэропорт",
  # "Построй маршрут до ближайшего аэропорта",
].freeze

USER_ID = "user123"

SYSTEM_PROMPT = <<-PROMPT.freeze
      Ты — MCP агент.

      Правила работы:
      - НИКОГДА НЕ возвращай JSON в content, придерживаясь вызова инструмента.
      - НИКОГДА НЕ выдумывай значения-заглушки.
      - НИКОГДА НЕ выдумывай параметры.
      - НИКОГДА НЕ запрашивай значения у пользователя.
      - НИКОГДА НЕ повторяй тот же вызов с теми же аргументами после ошибки.
      - НИКОГДА НЕ делай предположения о следующих шагах.
      - ВСЕГДА СТРОГО соблюдай тип данных параметров.
      - ВСЕГДА ВЫЗЫВАЙ ИНСТРУМЕНТ.



      В завершение: ВЕРНИ финальный ответ обычным текстом на русском языке.
    PROMPT

def run_model(model, query, user_id)
  service = LLMTestRuby::Service.new

  started_at = Time.now
  result = service.run_model(model, query, user_id)
  duration = Time.now - started_at

  {
    model: model,
    query: query,
    duration_sec: duration.round(3),
    result_preview: result.to_s[0, 200],
  }
end

puts "=== LLM TEST RUN ==="

stats = []

MODELS.each do |model|
  QUERIES.each do |query|
    puts "\nMODEL=#{model}"
    puts "QUERY=#{query}"

    s = run_model(model, query, USER_ID)
    stats << s

    puts "DONE in #{s[:duration_sec]}s"
  end
end

puts "\n=== RUN SUMMARY ==="
stats.each { |s| puts s.inspect }

if defined?(DB_STORE)
  puts "\n=== DB SNAPSHOT ==="
  puts JSON.pretty_generate(DB_STORE)
end
