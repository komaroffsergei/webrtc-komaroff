# frozen_string_literal: true

RSpec.describe "graph DSL" do
  it "imports fragments with aliases and resolves references through ref" do
    catalog = SrcLanggraphRb.build_catalog do
      fragment :assistant_reply_tail do
        node :respond, kind: :final_response
        finish_point :respond
      end

      scenario "fragment_demo@1.0.0" do
        graph do
          use :assistant_reply_tail, as: :final
          entry_point :prepare
          node :prepare, kind: :local
          edge :prepare, ref(:final, :respond)
        end
      end
    end

    graph = catalog.fetch("fragment_demo@1.0.0").graph

    expect(graph.nodes.map(&:id)).to contain_exactly(:final__respond, :prepare)
    expect(graph.finish_points).to eq([:final__respond])
    expect(graph.imports.map(&:to_h)).to eq([{ name: "assistant_reply_tail", alias: "final" }])
  end

  it "fails when a scenario imports an unknown fragment" do
    expect do
      SrcLanggraphRb.build_catalog do
        scenario "broken@1.0.0" do
          graph do
            use :missing_fragment, as: :x
            entry_point :start
            node :start, kind: :local
            finish_point :start
          end
        end
      end
    end.to raise_error(SrcLanggraphRb::FragmentError, /missing_fragment/)
  end
end
