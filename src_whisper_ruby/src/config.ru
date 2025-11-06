# frozen_string_literal: true

require "json"


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
