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
      attr_reader :parents

      def initialize
        @parents = []
      end

      def call(request, parent:)
        @parents << parent.fetch(:request_id)
        case request.kind
        when :llm
          { user: { id: parent[:session_id], name: "Ada" } }
        when :tool
          { code: "ON_TIME" }
        end
      end
    end.new

    req = workflow_request(text: "graph runner")
    final_state = described_class.new(graph: graph, executor: executor).run(state: { req: req, user_id: 7 })

    expect(final_state[:profile]).to eq({ user: { id: SpecSupport::SESSION_ID, name: "Ada" } })
    expect(final_state[:status]).to eq({ code: "ON_TIME" })
    expect(executor.parents).to eq([SpecSupport::REQUEST_ID, SpecSupport::REQUEST_ID])
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
      def call(*, **)
        raise "executor should not be called"
      end
    end.new

    req = workflow_request(text: "route")
    approved = described_class.new(graph: graph, executor: executor).run(state: { req: req, approved: true })
    rejected = described_class.new(graph: graph, executor: executor).run(state: { req: req, approved: false })

    expect(approved[:result]).to eq("done")
    expect(rejected[:result]).to eq("rejected")
  end

  it "uses AsyncGraph barrier joins through the runner-backed adapter" do
    graph = AsyncGraph::Graph.new do
      node :split do
      end

      node :left do
        { left_ready: true, shared: 1 }
      end

      node :right do
        { right_ready: true, shared: 1 }
      end

      node :merge do |state, await|
        profile = await.call(
          "profile",
          :llm,
          mode: "final_response",
          input_data: { prompt: "profile", user_id: state[:user_id] },
          constraints: {}
        )
        { profile: profile }
      end

      set_entry_point :split
      edge :split, :left, branch: :left
      edge :split, :right, branch: :right
      edge %i[left right], :merge
      set_finish_point :merge
    end

    executor = Class.new do
      def call(request, parent:)
        { profile_for: request.payload.dig(:input_data, :user_id), request_id: parent[:request_id] }
      end
    end.new

    final_state = described_class.new(graph: graph, executor: executor).run(
      state: { req: workflow_request(text: "join"), user_id: 7 }
    )

    expect(final_state).to include(
      left_ready: true,
      right_ready: true,
      shared: 1,
      profile: { profile_for: 7, request_id: SpecSupport::REQUEST_ID }
    )
  end
end
