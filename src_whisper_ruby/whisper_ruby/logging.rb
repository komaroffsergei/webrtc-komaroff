# frozen_string_literal: true

require "logger"
require "time"

STDOUT.sync = true

LOGGER = Logger.new($stdout)
LOGGER.level = Logger::INFO
LOGGER.formatter = proc do |severity, datetime, progname, msg|
  timestamp = datetime.utc.iso8601(3)
  prog = progname ? "#{progname}: " : ""
  "[#{timestamp}] #{severity} #{prog}#{msg}\n"
end
