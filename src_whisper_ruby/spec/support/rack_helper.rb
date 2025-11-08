require 'stack-service-base/logging'
require 'rspec-benchmark'
require 'rack/test'
require 'async/rspec'
require 'rack/builder'
require "rspec/snapshot"
require 'testcontainers'

ENV['STACK_SERVICE_NAME']='rspec_ruby_wisper'
ENV['NATS_WHISPER_SUBJECT']='voice_chat_transcription'
ENV['NATS_LOGS_SUBJECT']='voice_chat_logs'
ENV['WHISPER_MODEL_NAME']='medium'
ENV['WHISPER_VAD_MODEL_NAME']='silero-v5.1.2'
ENV['WHISPER_MODELS_DIR']='/app/models'

module Rack::Test::AppHelper
  def app = RSpec.configuration.app
end

RSpec.configure do |config|
  config.include Rack::Test::AppHelper, type: :request
  config.include Rack::Test::Methods, type: :request
  config.include RSpec::Benchmark::Matchers
  config.include RSpec::Snapshot
  config.include_context Async::RSpec::Reactor
  config.add_setting :app

  # Tag anything under /integration as :integration
  # config.define_derived_metadata(file_path: %r{/spec/integration/}) { |m| m[:type] = :integration }

  # ensure this only runs for request specs; avoid leaking into other types
  config.before(type: :request) do
    header 'Host', 'localhost'
  end

  # Load Rack app only once when first integration test runs
  config.before(:suite) do
    if RSpec.world.filtered_examples.values.flatten.any? { |e| e.metadata[:type] == :request }
      rack_app, = Rack::Builder.parse_file(File.expand_path("../../config.ru", __dir__))
      RSpec.configuration.app = rack_app
    end
  end
end
