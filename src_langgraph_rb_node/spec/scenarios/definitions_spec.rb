# frozen_string_literal: true

require "spec_helper"

RSpec.describe "scenario definitions" do
  it "builds valid built-in AsyncGraph definitions" do
    definitions = [
      SrcLanggraphRbNode::Scenarios::FreeSpeech.definition,
      SrcLanggraphRbNode::Scenarios::WhereMyFlight.definition,
      SrcLanggraphRbNode::Scenarios::FindNearestAirport.definition
    ]

    expect(definitions.map(&:id)).to eq(
      [
        SrcLanggraphRbNode::Runtime::ScenarioIds::FREE_SPEECH,
        SrcLanggraphRbNode::Runtime::ScenarioIds::WHERE_MY_FLIGHT,
        SrcLanggraphRbNode::Runtime::ScenarioIds::FIND_NEAREST_AIRPORT
      ]
    )
    definitions.each do |definition|
      expect { definition.graph.validate! }.not_to raise_error
    end
  end
end
