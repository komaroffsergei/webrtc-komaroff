# frozen_string_literal: true

require "spec_helper"

RSpec.describe "free_speech scenario" do
  it "clarifies ambiguous singular references from artifact memory without an LLM call" do
    io = FakeIo.new
    engine = SrcLanggraphRbNode::Runtime::Engine.new(
      io: io,
      memory_recent_messages: 32,
      memory_summary_max_chars: 12_000,
      memory_context_max_chars: 18_000
    )

    response = engine.run(
      workflow_request(
        text: "где он",
        runtime: {
          active_workflow_id: SrcLanggraphRbNode::Runtime::ScenarioIds::FREE_SPEECH,
          context: {
            artifact_memory: {
              last_airports: [
                { id: "svo", name: "Sheremetyevo", code: "SVO" },
                { id: "vko", name: "Vnukovo", code: "VKO" }
              ]
            }
          }
        }
      )
    )

    expect(response[:status]).to eq("DONE")
    expect(response[:result]).to include("Уточните, о каком объекте речь")
    expect(io.llm_calls).to be_empty
  end
end
