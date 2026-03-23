# frozen_string_literal: true

require "spec_helper"

RSpec.describe SrcLanggraphRbNode::Runtime::Engine do
  it "starts the scenario directly from runtime.active_workflow_id without calling the top-level router" do
    io = FakeIo.new(
      llm_responses: [
        llm_ok(extracted: { flight_number: "SU123" }),
        llm_ok(response_text: "Рейс SU123 вовремя.")
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
              status: "ON_TIME"
            }
          }
        })
      }
    )

    engine = described_class.new(
      io: io,
      memory_recent_messages: 32,
      memory_summary_max_chars: 12_000,
      memory_context_max_chars: 18_000
    )

    response = engine.run(
      workflow_request(
        text: "где мой рейс su123",
        runtime: { active_workflow_id: SrcLanggraphRbNode::Runtime::ScenarioIds::WHERE_MY_FLIGHT }
      )
    )

    expect(response[:status]).to eq("DONE")
    expect(response[:result]).to eq("Рейс SU123 вовремя.")
    expect(io.llm_calls.map { |call| call[:mode] }).to eq(%w[tool_params final_response])
  end
end
