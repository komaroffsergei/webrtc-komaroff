# frozen_string_literal: true

require "bundler/setup"
require "src_langgraph_rb"

RSpec.configure do |config|
  config.disable_monkey_patching!
  config.order = :random
  Kernel.srand config.seed
end
