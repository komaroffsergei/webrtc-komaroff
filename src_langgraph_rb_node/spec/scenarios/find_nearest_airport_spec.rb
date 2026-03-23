# frozen_string_literal: true

require "spec_helper"

RSpec.describe "find_nearest_airport scenario" do
  it "builds a route and emits map events" do
    io = FakeIo.new(
      llm_responses: [
        llm_ok(extracted: { city: "Moscow", radius_km: 25 }),
        llm_ok(extracted: {}),
        llm_ok(response_text: "Ближайший аэропорт найден, маршрут построен.")
      ],
      tool_responses: {
        "get_current_position" => tool_ok(data: { data: { city: "Moscow", lat: 55.75, lon: 37.61 } }),
        "search_airports_nearby" => tool_ok(data: {
          data: {
            airports: [
              { id: 1, code: "SVO", name: "Sheremetyevo", lat: 55.9726, lon: 37.4146 }
            ]
          }
        }),
        "build_route" => tool_ok(data: {
          data: {
            distance_km: 31.5,
            duration_min: 40,
            geometry: [[37.61, 55.75], [37.4146, 55.9726]]
          }
        })
      }
    )

    engine = SrcLanggraphRbNode::Runtime::Engine.new(
      io: io,
      memory_recent_messages: 32,
      memory_summary_max_chars: 12_000,
      memory_context_max_chars: 18_000
    )

    response = engine.run(
      workflow_request(
        text: "найди ближайший аэропорт",
        runtime: { active_workflow_id: SrcLanggraphRbNode::Runtime::ScenarioIds::FIND_NEAREST_AIRPORT }
      )
    )

    expect(response[:status]).to eq("DONE")
    expect(response[:result]).to eq("Ближайший аэропорт найден, маршрут построен.")
    expect(response[:client_events].map { |item| item[:command] }).to eq(%w[SET_POSITION SET_AIRPORTS BUILD_ROUTE])
  end
end
