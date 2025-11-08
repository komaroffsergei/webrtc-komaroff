require "rack/test"
require "rack/builder"

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
  config.include Rack::Test::Methods, type: :request
  config.include Rack::Test::AppHelper, type: :request
  config.add_setting :app

  # Load Rack app only once when first integration test runs
  config.before(:suite) do
    if RSpec.world.filtered_examples.values.flatten.any? { |e| e.metadata[:type] == :request }
      rack_app, = Rack::Builder.parse_file(File.expand_path("../../config.ru", __dir__))
      RSpec.configuration.app = rack_app
    end
  end
end
