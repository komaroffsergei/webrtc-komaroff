# frozen_string_literal: true

RSpec.describe SrcLanggraphRb::Runtime::Engine do
  class EngineFakeIo
    attr_reader :llm_calls, :tool_calls

    def initialize(llm_responses: {}, tool_responses: {})
      @llm_responses = llm_responses.transform_values(&:dup)
      @tool_responses = tool_responses.transform_values(&:dup)
      @llm_calls = []
      @tool_calls = []
    end

    def call_llm(parent:, mode:, input_data:, constraints:)
      @llm_calls << { parent:, mode:, input_data:, constraints: }
      pull(@llm_responses, mode)
    end

    def call_tool(parent:, tool_name:, args:)
      @tool_calls << { parent:, tool_name:, args: }
      pull(@tool_responses, tool_name)
    end

    private

    def pull(source, key)
      bucket = source.fetch(key) do
        raise "missing stub for #{key.inspect}"
      end
      bucket.shift || raise("stub queue exhausted for #{key.inspect}")
    end
  end

  def base_request(text, runtime: {})
    {
      trace_id: SecureRandom.uuid,
      correlation_id: SecureRandom.uuid,
      request_id: SecureRandom.uuid,
      session_id: SecureRandom.uuid,
      ts_ms: SrcLanggraphRb::Runtime::Contracts::Common.now_ts_ms,
      text: text,
      turn_id: nil,
      edit: nil,
      runtime: SrcLanggraphRb::Runtime::Contracts::Workflow.normalize_runtime(runtime)
    }
  end

  it "routes to free_speech and returns a final message" do
    io = EngineFakeIo.new(
      llm_responses: {
        "routing_decision" => [
          { ok: true, data: { workflow_id: SrcLanggraphRb::Runtime::ScenarioIds::FREE_SPEECH, reason: "fallback", confidence: 0.8 } }
        ],
        "final_response" => [
          { ok: true, data: { response_text: "Привет!" } }
        ]
      }
    )
    engine = described_class.new(io:, memory_recent_messages: 32, memory_summary_max_chars: 12_000, memory_context_max_chars: 18_000)

    response = engine.run(base_request("как дела"))

    expect(response[:status]).to eq("DONE")
    expect(response[:result]).to eq("Привет!")
    expect(response.dig(:client_handler, :command)).to eq("SHOW_MESSAGE")
  end

  it "returns PARTIAL for where_my_flight when params are missing" do
    io = EngineFakeIo.new(
      llm_responses: {
        "routing_decision" => [
          { ok: true, data: { workflow_id: SrcLanggraphRb::Runtime::ScenarioIds::WHERE_MY_FLIGHT, reason: "flight", confidence: 0.9 } }
        ],
        "tool_params" => [
          { ok: true, data: { extracted: {}, missing: ["flight_number_or_last_name"], prompt: "Укажите номер рейса" } }
        ]
      }
    )
    engine = described_class.new(io:, memory_recent_messages: 32, memory_summary_max_chars: 12_000, memory_context_max_chars: 18_000)

    response = engine.run(base_request("где мой рейс"))

    expect(response[:status]).to eq("PARTIAL")
    expect(response[:result]).to eq("Укажите номер рейса")
    expect(response.dig(:client_handler, :command)).to eq("ASK_USER_INPUT")
    expect(response.dig(:next_runtime, :active_workflow_id)).to eq(SrcLanggraphRb::Runtime::ScenarioIds::WHERE_MY_FLIGHT)
  end

  it "executes nearest_airport end-to-end and emits map events" do
    io = EngineFakeIo.new(
      llm_responses: {
        "routing_decision" => [
          { ok: true, data: { workflow_id: SrcLanggraphRb::Runtime::ScenarioIds::FIND_NEAREST_AIRPORT, reason: "airport", confidence: 0.95 } }
        ],
        "tool_params" => [
          { ok: true, data: { extracted: { city: "Moscow", radius_km: 50 } } },
          { ok: true, data: { extracted: {} } }
        ],
        "final_response" => [
          { ok: true, data: { response_text: "Маршрут построен." } }
        ]
      },
      tool_responses: {
        "get_current_position" => [
          { ok: true, data: { data: { city: "Moscow", lat: 55.75, lon: 37.61 } } }
        ],
        "search_airports_nearby" => [
          { ok: true, data: { data: { airports: [{ name: "Sheremetyevo", code: "SVO", lat: 55.97, lon: 37.41 }] } } }
        ],
        "build_route" => [
          { ok: true, data: { data: { distance_km: 12.5, duration_min: 22, geometry: [[37.61, 55.75], [37.41, 55.97]] } } }
        ]
      }
    )
    engine = described_class.new(io:, memory_recent_messages: 32, memory_summary_max_chars: 12_000, memory_context_max_chars: 18_000)

    response = engine.run(base_request("найди ближайший аэропорт"))

    expect(response[:status]).to eq("DONE")
    expect(response[:result]).to eq("Маршрут построен.")
    expect(response[:client_events].map { |event| event[:command] }).to eq(%w[SET_POSITION SET_AIRPORTS BUILD_ROUTE])
  end
end
