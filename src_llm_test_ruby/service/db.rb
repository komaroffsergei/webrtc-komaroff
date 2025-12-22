# frozen_string_literal: true

require 'securerandom'
require 'time'

module LLMTestRuby
  module DB
    extend self

    def reset!
      @store = {
        sessions: [],
        intents: [],
        artifacts: [],
        events: []
      }
    end

    reset!

    def store
      @store
    end

    def now
      Time.now.utc.iso8601
    end

    def create_session(user_id)
      session_id = SecureRandom.uuid
      @store[:sessions] << {
        session_id: session_id,
        user_id: user_id,
        status: 'RUNNING',
        created_at: now,
        updated_at: now
      }
      session_id
    end

    def finish_session(session_id, status = 'COMPLETED')
      session = @store[:sessions].find { |s| s[:session_id] == session_id }
      return unless session

      session[:status] = status
      session[:updated_at] = now
    end

    def create_intent(session_id:, user_id:, intent_type:)
      intent_id = SecureRandom.uuid
      @store[:intents] << {
        intent_id: intent_id,
        session_id: session_id,
        user_id: user_id,
        intent_type: intent_type,
        status: 'RUNNING',
        created_at: now
      }
      intent_id
    end

    def finish_intent(_session_id, intent_id, final_answer)
      intent = @store[:intents].find { |i| i[:intent_id] == intent_id }
      return unless intent

      intent[:status] = 'COMPLETED'
      intent[:result] = final_answer
    end

    def log_event(session_id:, intent_id:, seq:, role:, event_type:, name:, input_data:, output_data:)
      @store[:events] << {
        event_id: @store[:events].length + 1,
        session_id: session_id,
        intent_id: intent_id,
        seq: seq,
        role: role,
        event_type: event_type,
        name: name,
        input: input_data,
        output: output_data,
        created_at: now
      }
    end

    def log_artifact(session_id:, intent_id:, artifact_type:, name:, data:)
      @store[:artifacts] << {
        artifact_id: SecureRandom.uuid,
        session_id: session_id,
        intent_id: intent_id,
        type: artifact_type,
        name: name,
        data: data,
        created_at: now
      }
    end
  end
end
