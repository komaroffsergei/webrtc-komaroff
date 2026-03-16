# frozen_string_literal: true

require "json"
require "securerandom"

RSpec.describe "runtime integration" do
  class RuntimeSpecIo
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

  class RuntimeSpecNc
    Message = Struct.new(:data)

    attr_reader :requests

    def initialize(response_by_subject: {}, error_by_subject: {})
      @response_by_subject = response_by_subject
      @error_by_subject = error_by_subject
      @requests = []
    end

    def request(subject, payload, timeout:)
      @requests << { subject:, payload:, timeout: }
      raise @error_by_subject.fetch(subject) if @error_by_subject.key?(subject)

      body = @response_by_subject.fetch(subject) do
        raise "missing NATS stub for #{subject.inspect}"
      end
      Message.new(body)
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

  def build_engine(io)
    SrcLanggraphRb::Runtime::Engine.new(
      io: io,
      memory_recent_messages: 32,
      memory_summary_max_chars: 12_000,
      memory_context_max_chars: 18_000
    )
  end

  it "falls back to free_speech when router llm fails" do
    io = RuntimeSpecIo.new(
      llm_responses: {
        "routing_decision" => [
          { ok: false, error: { code: "llm_failed", message: "timeout" } }
        ]
      }
    )

    scenario, routing = SrcLanggraphRb::Runtime::Router.choose_scenario(
      base_request("как дела"),
      io,
      dialog_context: ""
    )

    expect(scenario).to eq(SrcLanggraphRb::Runtime::ScenarioIds::FREE_SPEECH)
    expect(routing).to eq({})
  end

  it "reroutes pending where_my_flight into free_speech" do
    io = RuntimeSpecIo.new(
      llm_responses: {
        "tool_params" => [
          { ok: true, data: { extracted: {}, missing: ["flight_number_or_last_name"], prompt: "Уточните рейс" } }
        ],
        "routing_decision" => [
          { ok: true, data: { workflow_id: SrcLanggraphRb::Runtime::ScenarioIds::FREE_SPEECH, reason: "smalltalk", confidence: 0.88 } }
        ],
        "final_response" => [
          { ok: true, data: { response_text: "Нормально." } }
        ]
      }
    )
    engine = build_engine(io)

    response = engine.run(
      base_request(
        "как дела",
        runtime: {
          active_workflow_id: SrcLanggraphRb::Runtime::ScenarioIds::WHERE_MY_FLIGHT,
          pending: {
            type: "tool_params",
            scenario_id: SrcLanggraphRb::Runtime::ScenarioIds::WHERE_MY_FLIGHT,
            extracted: {}
          }
        }
      )
    )

    expect(response[:status]).to eq("DONE")
    expect(response[:result]).to eq("Нормально.")
    expect(io.llm_calls.map { |call| call[:mode] }).to eq(%w[tool_params routing_decision final_response])
  end

  it "returns done not_found message for where_my_flight tool miss" do
    io = RuntimeSpecIo.new(
      llm_responses: {
        "routing_decision" => [
          { ok: true, data: { workflow_id: SrcLanggraphRb::Runtime::ScenarioIds::WHERE_MY_FLIGHT, reason: "flight", confidence: 0.91 } }
        ],
        "tool_params" => [
          { ok: true, data: { extracted: { flight_number: "SU123" }, missing: [], prompt: nil } }
        ]
      },
      tool_responses: {
        "get_flight_status" => [
          { ok: false, error: { code: "not_found", message: "missing" } }
        ]
      }
    )
    engine = build_engine(io)

    response = engine.run(base_request("где рейс su123"))

    expect(response[:status]).to eq("DONE")
    expect(response[:result]).to eq("Статус рейса не найден.")
    expect(response.dig(:client_handler, :command)).to eq("SHOW_MESSAGE")
  end

  it "clarifies ambiguous free_speech reference without final llm call" do
    io = RuntimeSpecIo.new(
      llm_responses: {
        "routing_decision" => [
          { ok: true, data: { workflow_id: SrcLanggraphRb::Runtime::ScenarioIds::FREE_SPEECH, reason: "chat", confidence: 0.73 } }
        ]
      }
    )
    engine = build_engine(io)

    response = engine.run(
      base_request(
        "в каком году он построен",
        runtime: {
          context: {
            artifact_memory: {
              last_airports: [
                { name: "Sheremetyevo", code: "SVO" },
                { name: "Domodedovo", code: "DME" }
              ]
            }
          }
        }
      )
    )

    expect(response[:status]).to eq("DONE")
    expect(response[:result]).to include("Уточните, о каком объекте речь")
    expect(io.llm_calls.map { |call| call[:mode] }).to eq(["routing_decision"])
  end

  it "sends llm requests through RuntimeIo with hash parents" do
    nc = RuntimeSpecNc.new(
      response_by_subject: {
        "nats.llm.user123" => JSON.generate(
          ok: true,
          data: { workflow_id: SrcLanggraphRb::Runtime::ScenarioIds::FREE_SPEECH }
        )
      }
    )
    io = SrcLanggraphRb::Runtime::RuntimeIo.new(
      nc: nc,
      llm_subject_prefix: "nats.llm.",
      tools_subject_prefix: "nats.tools.",
      user_id: "user123",
      request_timeout_s: 5
    )

    response = io.call_llm(
      parent: base_request("привет"),
      mode: "routing_decision",
      input_data: { text: "привет" },
      constraints: { temperature: 0 }
    )

    request = nc.requests.fetch(0)
    payload = JSON.parse(request[:payload])

    expect(request[:subject]).to eq("nats.llm.user123")
    expect(request[:timeout]).to eq(5.0)
    expect(payload["mode"]).to eq("routing_decision")
    expect(payload["trace_id"]).not_to be_nil
    expect(response[:ok]).to eq(true)
    expect(response.dig(:data, :workflow_id)).to eq(SrcLanggraphRb::Runtime::ScenarioIds::FREE_SPEECH)
  end

  it "returns normalized tool transport errors from RuntimeIo" do
    nc = RuntimeSpecNc.new(
      error_by_subject: {
        "nats.tools.get_flight_status" => StandardError.new("nats timeout")
      }
    )
    io = SrcLanggraphRb::Runtime::RuntimeIo.new(
      nc: nc,
      llm_subject_prefix: "nats.llm.",
      tools_subject_prefix: "nats.tools.",
      user_id: "user123",
      request_timeout_s: 3
    )

    response = io.call_tool(
      parent: base_request("где рейс"),
      tool_name: "get_flight_status",
      args: { flight_number: "SU123" }
    )

    expect(response[:ok]).to eq(false)
    expect(response.dig(:error, :code)).to eq("tool_transport_error")
    expect(response.dig(:error, :message)).to include("nats.tools.get_flight_status")
  end
end
