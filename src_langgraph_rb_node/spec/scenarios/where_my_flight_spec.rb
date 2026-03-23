# frozen_string_literal: true

require "spec_helper"

RSpec.describe "where_my_flight scenario" do
  def build_engine(io)
    SrcLanggraphRbNode::Runtime::Engine.new(
      io: io,
      memory_recent_messages: 32,
      memory_summary_max_chars: 12_000,
      memory_context_max_chars: 18_000
    )
  end

  it "returns PARTIAL when parameters are still missing" do
    io = FakeIo.new(
      llm_responses: [
        llm_ok(extracted: {}, prompt: "Назовите номер рейса.")
      ]
    )

    response = build_engine(io).run(
      workflow_request(
        text: "где мой рейс",
        runtime: { active_workflow_id: SrcLanggraphRbNode::Runtime::ScenarioIds::WHERE_MY_FLIGHT }
      )
    )

    expect(response[:status]).to eq("PARTIAL")
    expect(response.dig(:client_handler, :command)).to eq("ASK_USER_INPUT")
    expect(response.dig(:next_runtime, :active_workflow_id)).to eq(SrcLanggraphRbNode::Runtime::ScenarioIds::WHERE_MY_FLIGHT)
    expect(response.dig(:next_runtime, :pending, :missing)).to eq(["flight_number_or_last_name"])
  end

  it "continues a pending dialog and finishes after follow-up flight number" do
    io = FakeIo.new(
      llm_responses: [
        llm_ok(extracted: { flight_number: "SU123" }),
        llm_ok(response_text: "Рейс SU123 задерживается.")
      ],
      tool_responses: {
        "get_flight_status" => tool_ok(data: {
          data: {
            flight: {
              flight_number: "SU123",
              from: "SVO",
              to: "LED",
              departure_time: "2026-03-23T12:00:00Z",
              arrival_time: "2026-03-23T13:20:00Z",
              status: "DELAYED"
            }
          }
        })
      }
    )

    response = build_engine(io).run(
      workflow_request(
        text: "SU123",
        runtime: {
          active_workflow_id: SrcLanggraphRbNode::Runtime::ScenarioIds::WHERE_MY_FLIGHT,
          pending: {
            type: "tool_params",
            scenario_id: SrcLanggraphRbNode::Runtime::ScenarioIds::WHERE_MY_FLIGHT,
            tool_name: "get_flight_status",
            extracted: {},
            missing: ["flight_number_or_last_name"],
            prompt: "Назовите номер рейса."
          }
        }
      )
    )

    expect(response[:status]).to eq("DONE")
    expect(response[:result]).to eq("Рейс SU123 задерживается.")
  end

  it "reroutes to free_speech when pending follow-up becomes a different request" do
    io = FakeIo.new(
      llm_responses: [
        llm_ok(extracted: {}),
        llm_ok(workflow_id: SrcLanggraphRbNode::Runtime::ScenarioIds::FREE_SPEECH),
        llm_ok(response_text: "С погодой у меня нет проблем.")
      ]
    )

    response = build_engine(io).run(
      workflow_request(
        text: "как дела",
        runtime: {
          active_workflow_id: SrcLanggraphRbNode::Runtime::ScenarioIds::WHERE_MY_FLIGHT,
          pending: {
            type: "tool_params",
            scenario_id: SrcLanggraphRbNode::Runtime::ScenarioIds::WHERE_MY_FLIGHT,
            tool_name: "get_flight_status",
            extracted: {},
            missing: ["flight_number_or_last_name"],
            prompt: "Назовите номер рейса."
          }
        }
      )
    )

    expect(response[:status]).to eq("DONE")
    expect(response[:result]).to eq("С погодой у меня нет проблем.")
    expect(io.llm_calls.map { |call| call[:mode] }).to eq(%w[tool_params routing_decision final_response])
  end
end
