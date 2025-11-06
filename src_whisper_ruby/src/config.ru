# frozen_string_literal: true

require "json"

begin
  require "stack-service-base"
  StackServiceBase.rack_setup(self)
rescue LoadError
  warn "[whisper_ruby] stack-service-base not available, continuing without it"
end

require_relative "lib/whisper_ruby/service"

unless defined?(WhisperRuby::SERVICE_INSTANCE)
  autostart = if ENV.key?("WHISPER_RUBY_AUTOSTART")
                ENV["WHISPER_RUBY_AUTOSTART"].to_s.downcase == "true"
              else
                ENV["APP_ENV"].to_s != "test"
              end

  if autostart
    WhisperRuby::SERVICE_INSTANCE = WhisperRuby::Service.new
    WhisperRuby::SERVICE_INSTANCE.start
  end
end

class HealthApp
  STATUS_OK = JSON.dump(status: "ok")
  NOT_FOUND = JSON.dump(error: "not_found")

  def call(env)
    case env["PATH_INFO"]
    when "/healthcheck"
      [200, {"Content-Type" => "application/json"}, [STATUS_OK]]
    else
      [404, {"Content-Type" => "application/json"}, [NOT_FOUND]]
    end
  end
end

run HealthApp.new
