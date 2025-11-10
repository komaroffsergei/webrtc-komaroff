require "sinatra"
require "json"
require "stack-service-base"
require_relative "whisper_ruby/rack_bootstrap"

StackServiceBase.rack_setup(self)

configure do
  WhisperRuby::RackBootstrap.configure
end

get "/healthcheck" do
  state = WhisperRuby::RackBootstrap.current_state
  content_type :json
  status(state.healthy? ? 200 : 503)
  state.payload.to_json
end

run Sinatra::Application
