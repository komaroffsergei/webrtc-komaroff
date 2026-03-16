# frozen_string_literal: true

RSpec.describe SrcLanggraphRb::Adapters::LangGraphRB::BuilderPlan do
  let(:catalog) { SrcLanggraphRb.built_in_catalog }

  it "translates a scenario spec into a LangGraphRB builder plan" do
    spec = catalog.fetch("where_my_flight@2.0.0")
    plan = described_class.from_spec(spec)

    expect(plan.to_h[:scenario_id]).to eq("where_my_flight@2.0.0")
    expect(plan.instructions.map { |instruction| instruction[:op] }).to include(:node, :set_entry_point, :conditional_edge, :set_finish_point)
  end

  it "builds an uncompiled LangGraphRB graph without invoking compile" do
    spec = catalog.fetch("free_speech@2.0.0")
    plan = described_class.from_spec(spec)
    graph = plan.build_graph

    expect(graph).to be_a(LangGraphRB::Graph)
    expect(graph.compiled?).to be(false)
    expect(graph.nodes.keys).to include(:prepare_context, :compose_primary, :compose_retry, :final__respond, :terminal__respond)
  end
end
