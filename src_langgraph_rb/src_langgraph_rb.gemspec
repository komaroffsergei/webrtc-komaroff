# frozen_string_literal: true

require_relative "lib/src_langgraph_rb/version"

Gem::Specification.new do |spec|
  spec.name = "src_langgraph_rb"
  spec.version = SrcLanggraphRb::VERSION
  spec.authors = ["OpenAI Codex"]
  spec.email = ["noreply@example.com"]

  spec.summary = "Ruby workflow runtime and declarative scenario DSL for src_langgraph"
  spec.description = "Ruby NATS runtime for migrated workflow scenarios plus a declarative DSL that translates reusable scenario specs into LangGraphRB builder plans."
  spec.homepage = "https://github.com/fulit103/langgraph_rb"
  spec.license = "MIT"
  spec.required_ruby_version = ">= 3.4.0"

  spec.metadata["homepage_uri"] = spec.homepage
  spec.metadata["source_code_uri"] = spec.homepage

  spec.files = Dir.chdir(__dir__) do
    Dir["README.md", "bin/*", "config/**/*", "lib/**/*"].sort
  end
  spec.require_paths = ["lib"]

  spec.add_dependency "langgraph_rb", "~> 0.1.11"
  spec.add_dependency "logger"
  spec.add_dependency "nats-pure", "~> 2.5"
end
