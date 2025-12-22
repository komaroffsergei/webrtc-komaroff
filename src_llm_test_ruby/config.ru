# frozen_string_literal: true

require 'bundler/setup'
Bundler.require(:default)

require_relative 'service/service'
require_relative 'service/settings'
require_relative 'service/db'
require_relative 'service/tools'

run lambda { |env|
  req = Rack::Request.new(env)

  if req.path == '/healthcheck'
    [200, { 'Content-Type' => 'application/json' }, [{ status: 'Healthy' }.to_json]]
  elsif req.post? && req.path == '/query'
    begin
      params = JSON.parse(req.body.read)
      model = params['model']
      user_query = params['query']
      user_id = params['user_id'] || LLMTestRuby::Settings::USER_ID

      service = LLMTestRuby::Service.new
      response = service.run_model(model, user_query, user_id)

      [200, { 'Content-Type' => 'application/json' }, [{ answer: response }.to_json]]
    rescue => e
      [500, { 'Content-Type' => 'application/json' }, [{ error: e.message }.to_json]]
    end
  else
    [404, { 'Content-Type' => 'application/json' }, [{ error: 'Not found' }.to_json]]
  end
}