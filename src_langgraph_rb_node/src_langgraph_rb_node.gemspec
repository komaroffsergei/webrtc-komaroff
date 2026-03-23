# frozen_string_literal: true

require_relative "lib/src_langgraph_rb_node/version"

Gem::Specification.new do |spec|
  spec.name = "src_langgraph_rb_node"
  spec.version = SrcLanggraphRbNode::VERSION
  spec.authors = ["OpenAI Codex"]
  spec.email = ["noreply@example.com"]

  spec.summary = "Ruby workflow runtime on AsyncGraph with native scenario graphs"
  spec.description = "AsyncGraph-based Ruby NATS workflow runtime with library-style scenario authoring."
  spec.homepage = "https://github.com/artyomb/async-graph"
  spec.license = "MIT"
  spec.required_ruby_version = ">= 3.4.0"

  spec.metadata["homepage_uri"] = spec.homepage
  spec.metadata["source_code_uri"] = spec.homepage

  spec.files = Dir.chdir(__dir__) do
    Dir["README.md", "CODEMAP.md", "bin/*", "lib/**/*", "spec/**/*"].sort
  end
  spec.require_paths = ["lib"]

  spec.add_dependency "async-graph"
  spec.add_dependency "logger"
  spec.add_dependency "nats-pure", "~> 2.5"

  spec.add_development_dependency "rspec", "~> 3.13"
end
