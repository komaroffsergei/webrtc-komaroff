# frozen_string_literal: true

require "spec_helper"

RSpec.describe SrcLanggraphRbNode::Runtime::GraphRunner do
  it "resolves await.all requests and returns the merged final state" do
    graph = AsyncGraph::Graph.new do
      node :fetch do |state, await|
        results = await.all(
          profile: [:llm, { mode: "final_response", input_data: { prompt: "profile" }, constraints: {} }],
          status: [:tool, { tool_name: "get_status", args: { id: state[:user_id] } }]
        )

        {
          profile: results[:profile],
          status: results[:status]
        }
      end

      set_entry_point :fetch
      set_finish_point :fetch
    end

    executor = Class.new do
      def call(request, state:)
        case request.kind
        when :llm
          { user: { id: state[:user_id], name: "Ada" } }
        when :tool
          { code: "ON_TIME" }
        end
      end
    end.new

    final_state = described_class.new(graph: graph, executor: executor).run(state: { user_id: 7 })

    expect(final_state[:profile]).to eq({ user: { id: 7, name: "Ada" } })
    expect(final_state[:status]).to eq({ code: "ON_TIME" })
  end

  it "follows AsyncGraph::Command.goto branches" do
    graph = AsyncGraph::Graph.new do
      node :route do |state|
        if state[:approved]
          AsyncGraph::Command.goto(:done)
        else
          AsyncGraph::Command.update_and_goto({ reason: "rejected" }, :failed)
        end
      end

      node :done do
        { result: "done" }
      end

      node :failed do |state|
        { result: state[:reason] }
      end

      set_entry_point :route
      set_finish_point :done
      set_finish_point :failed
    end

    executor = Class.new do
      def call(*)
        raise "executor should not be called"
      end
    end.new

    approved = described_class.new(graph: graph, executor: executor).run(state: { approved: true })
    rejected = described_class.new(graph: graph, executor: executor).run(state: { approved: false })

    expect(approved[:result]).to eq("done")
    expect(rejected[:result]).to eq("rejected")
  end
end
