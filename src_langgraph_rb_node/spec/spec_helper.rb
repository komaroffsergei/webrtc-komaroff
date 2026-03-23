# frozen_string_literal: true

require "rspec"
require "src_langgraph_rb_node"

module SpecSupport
  TRACE_ID = "11111111-1111-4111-8111-111111111111"
  REQUEST_ID = "22222222-2222-4222-8222-222222222222"
  SESSION_ID = "33333333-3333-4333-8333-333333333333"

  class FakeIo
    attr_reader :llm_calls, :tool_calls

    def initialize(llm_responses: [], tool_responses: {})
      @llm_responses = Array(llm_responses).dup
      @tool_responses = tool_responses
      @llm_calls = []
      @tool_calls = []
    end

    def call_llm(parent:, mode:, input_data:, constraints: nil)
      @llm_calls << {
        parent: parent,
        mode: mode,
        input_data: input_data,
        constraints: constraints
      }
      response = @llm_responses.shift
      raise "No queued LLM response for #{mode}" unless response

      response.respond_to?(:call) ? response.call(mode: mode, input_data: input_data) : response
    end

    def call_tool(parent:, tool_name:, args:)
      @tool_calls << {
        parent: parent,
        tool_name: tool_name,
        args: args
      }

      response =
        if @tool_responses.is_a?(Array)
          @tool_responses.shift
        else
          @tool_responses.fetch(tool_name)
        end
      raise "No queued tool response for #{tool_name}" unless response

      response.respond_to?(:call) ? response.call(tool_name: tool_name, args: args) : response
    end
  end

  def workflow_request(text:, runtime: {}, edit: nil)
    {
      trace_id: TRACE_ID,
      correlation_id: TRACE_ID,
      request_id: REQUEST_ID,
      session_id: SESSION_ID,
      ts_ms: 1_710_000_000_000,
      text: text,
      runtime: { version: 1 }.merge(runtime),
      edit: edit
    }
  end

  def llm_ok(data)
    { ok: true, data: data }
  end

  def llm_error(code: "llm_failed", message: "llm failed")
    { ok: false, error: { code: code, message: message } }
  end

  def tool_ok(data)
    { ok: true, data: data }
  end

  def tool_error(code:, message:)
    { ok: false, error: { code: code, message: message } }
  end
end

FakeIo = SpecSupport::FakeIo

RSpec.configure do |config|
  config.include SpecSupport
  config.disable_monkey_patching!
  config.expect_with :rspec do |expectations|
    expectations.syntax = :expect
  end
end
