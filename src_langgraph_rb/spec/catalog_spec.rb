# frozen_string_literal: true

RSpec.describe SrcLanggraphRb::Catalog do
  let(:catalog) do
    SrcLanggraphRb.build_catalog do
      fragment :assistant_reply_tail do
        node :respond, kind: :final_response
        finish_point :respond
      end

      scenario "demo@1.0.0" do
        title "Demo"
        description "Minimal scenario"
        tags :chat
        capabilities :final_response

        graph do
          use :assistant_reply_tail, as: :final
          entry_point :start
          node :start, kind: :context_enrichment
          edge :start, ref(:final, :respond)
        end
      end

      scenario "tool@1.0.0" do
        tags :tool
        capabilities :tool_call

        graph do
          entry_point :start
          node :start, kind: :tool_call, tool_name: :demo_tool
          finish_point :start
        end
      end
    end
  end

  it "stores scenarios and filters them by metadata" do
    expect(catalog.fetch("demo@1.0.0").metadata.title).to eq("Demo")
    expect(catalog.filter(tags: ["chat"]).map(&:id)).to eq(["demo@1.0.0"])
    expect(catalog.filter(capabilities: ["tool_call"]).map(&:id)).to eq(["tool@1.0.0"])
  end

  it "produces builder plans through the catalog API" do
    plan = catalog.to_builder_plan("demo@1.0.0")

    expect(plan.to_h[:scenario_id]).to eq("demo@1.0.0")
  end
end
