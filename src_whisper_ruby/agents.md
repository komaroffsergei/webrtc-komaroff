# AGENTS.md

## General Instructions

The description of th connected Intellij MCP server tools:
https://www.jetbrains.com/help/idea/mcp-server.html#supported-tools

- At the beginning of the session, collect the list of project files, modules, classes, methods, variables, constants. Analyze the service workflows.
  Just remember, don't print report.


- Try to add new functionality with minimal code lines, avoiding code when behavior can be achieved without it.
- Prefer concise idioms for simple expressions; avoid expanding one-line constructs into multi-line blocks without need.
- Strive to be the best Ruby coder: favor modern, elegant idioms and expressive, readable code.
- After applying code changes do review for the refactoring and improvements available.   
- When persisting structured data, rely on Sequel's native JSON/JSONB support instead of manual parsing/serialization.
- When using Sequel's pg_json extension, insert plain Ruby hashes/arrays—no need to wrap with `Sequel.pg_jsonb`.
  read before use https://sequel.jeremyevans.net/rdoc-plugins/files/lib/sequel/extensions/pg_json_rb.html
- When performing upserts with Sequel, call `insert_conflict` on the dataset (`Model.dataset.insert_conflict(...)`) rather than on the model class itself.
- Prefer endless method definitions (`def x = ...`) for simple readers/wrappers when idiomatic Ruby allows it.
  Use them only when the body is a single expression with no branching or side effects (e.g., attr-style accessors, delegations, or formatters returning a string). Fall back to multi-line methods whenever the logic includes assignments, conditionals, rescues, or multiple statements.

This file contains coding guidelines and architectural principles for Ruby microservices projects. These rules help maintain consistency and enable AI agents to work safely and predictably with the codebase.

## General Principles

- **Microservices Architecture**: The project consists of small, focused services. Each business goal should have its own dedicated service.
- **Language**: All comments, log messages, and error text must be in **English**. (Commit descriptions may be in Russian for internal company use, but code artifacts must be in English)

## Architecture and Abstractions

- **Simplicity First**: Choose minimal architecture sufficient for functionality and testability.
- **OOP Usage**: Use Object-Oriented Programming only when one or more of the following apply:
  - Need for state encapsulation (objects with lifecycle)
  - Reuse in 2+ places
  - Planned extensibility (plugins/behavior variants)
  Otherwise, prefer modules/procedural or functional approaches.
- **Abstraction Introduction**: Introduce abstractions when they improve reusability or testability; avoid introducing them "just in case".
- **File Structure**: Do not add new top-level directories or files without a brief explanation of why the refactor/file is needed.
- **Microservice Simplicity**: For small microservices, `config.ru` can contain business logic directly. Only extract to separate files when the service grows beyond simple routing and basic functionality.

## Code Style and Ruby Idioms

- **Readability Priority**: When there's a conflict between brevity and clarity, **prioritize clarity**, but generally strive for concise, idiomatic Ruby (Ruby way).
- **Ruby Practices**: Follow common Ruby idioms. RuboCop/formatter is recommended but not mandatory if linter rules create unnecessary complexity.
- **Code Style**: Be compact, use modern Ruby syntax.
- **Standard Library**: Prefer standard library and framework tools if they simplify the task.
- **HTTP Requests**: Use Faraday for REST fetch requests with proper configuration:
  - Configure retry logic: `max: 2, interval: 0.2, backoff_factor: 2`
  - Set timeouts: `timeout: 15, open_timeout: 10`
  - Use persistent adapter: `net_http_persistent` with `pool_size: 10, idle_timeout: 60`
  - Example: `Faraday.new(url) do |f| f.request :retry, max: 2; f.options.timeout = 15; f.adapter :net_http_persistent end`
- **Comments**: Minimize comments - write comments only for truly non-obvious logic. Public methods may have brief docstrings (RDoc/YARD) - this is useful. Tests do **not** replace documentation for public methods.
- **Error Messages**: All error messages and log messages should be clear, concise, and in English.

## Metaprogramming and "Ruby Magic"

- **Metaprogramming Usage**: Metaprogramming is allowed if it **explicitly** reduces duplication and remains readable.
- **Public API**: Avoid metaprogramming in public APIs. If used, add a brief comment explaining the reason and test(s) covering the behavior.
- **Examples**: `define_method` is allowed for series of similar delegated methods; `eval`/string code generation is prohibited without strict tests and documentation.

## Constructs, Compactness, and Readability

- **Compact Code**: Strive for compact code - ternary operators, method chaining, and short lambdas are appropriate **if** the code is easy to read.
- **Complex Constructs**: Avoid nested ternaries and chaining longer than 3 calls if it impairs understanding.
- **Logic Decomposition**: Break complex logic into small named methods with clear names.

## File and Module Organization

- **Separation of Concerns**: Split code only when ALL conditions are met:
  - Code is reused in 2+ places OR
  - File exceeds ~1000 lines OR  
  - Clearly contains 2+ independent responsibilities
  - **Otherwise** - keep related code together in one file

- **Microservice File Structure**:
  - **Simple services** (1-2 classes): place all files next to `config.ru`
  - **Complex services** (5+ classes): create directories `services/`, `models/`, etc.
  - **Don't create directories "just in case"**

- **Class Utility Methods**: If a method is used only within one class - keep it as a `private` method of that class
- **Don't extract private methods to modules** - this complicates code without benefit
- **Create modules only for reusable code** between different classes

## Design Patterns and Principles

- **Pattern Application**: Follow basic principles (SOLID, DRY, etc.), but apply patterns contextually: use patterns if they make code clearer and more testable; avoid if they add unnecessary complexity.
- **Polymorphism**: Polymorphism is acceptable when it solves a real problem (alternative implementations, strategies, extensibility).

## Sensitive Changes and Review

- **Critical Changes**: Changes affecting database migrations, authentication/authorization, external service integrations, and secret storage require human review. Agents should not automatically merge such changes without approval.
- **Documentation**: For non-obvious changes, include a brief description of motivation and link to tests.

## StackServiceBase Integration

### Service Creation Foundation

- **Project Generator**: StackServiceBase is the foundational tool for creating new microservices. Use `ssbase init [option] <service_name>` to generate complete project structure.
- **Default Platform**: If no platform specified, use GitLab CI/CD (`ssbase init --gitlab-c <service_name>`).
- **Project Structure**: Creates complete service structure including Docker, CI/CD, tests, and basic Sinatra application with StackServiceBase integration.

### Framework Integration

- **Framework Setup**: Use `StackServiceBase.rack_setup(self)` in `config.ru` to automatically configure the service with logging, monitoring, and middleware.
- **Critical Import Order**: require `stack-service-base` BEFORE requiring `sinatra` in `config.ru`. StackServiceBase registers Sinatra extensions and middleware that must be available during Sinatra initialization.
- **Automatic Middleware**: The gem provides built-in middleware for CORS, health checks, request profiling, authentication, and error handling.
- **Health Check**: StackServiceBase automatically provides `/health` endpoint - no need to implement custom health checks.
- **Logging System**: Uses structured logging with context awareness. Access via `LOGGER` constant with methods: `info`, `debug`, `warn`, `error`.
- **OpenTelemetry Integration**: Automatic tracing when `OTEL_EXPORTER_OTLP_ENDPOINT` environment variable is set. Use `otl_span(name, attributes) { block }` for custom spans and `otl_def :method_name` after method definition for automatic method tracing. Apply `otl_def` only to the most critical methods, not to all methods indiscriminately.
- **Database Integration**: Automatic Sequel database connection with retry logic and logging integration when Sequel is present.
- **NATS Service**: Optional NATS microservice integration when `NATS_URL` environment variable is set.
- **Prometheus Metrics**: Automatic metrics collection and export when `PROMETHEUS_METRICS_EXPORT=true`.
- **Environment Variables**: Key variables include `QUIET`, `PERFORMANCE`, `STACK_NAME`, `STACK_SERVICE_NAME`, `OTEL_EXPORTER_OTLP_ENDPOINT`, `NATS_URL`.
- **Async Support**: Built-in support for Async gem with proper context propagation for OpenTelemetry.

### Service Creation Commands

- **Empty Directory**: If working in empty directory, create new service with `ssbase init --gitlab-c <service_name>`
- **Platform Options**: `--gitlab-c` (default), `--github`, `--gitlab` for different CI/CD platforms
- **Template Structure**: Generates `src/`, `docker/`, CI/CD configs, `Gemfile`, `config.ru`, and test structure

## Agent Instructions

- **Minimal Changes**: When making corrections, minimize the scope of code changes (small diffs).
- **Metaprogramming Documentation**: If using metaprogramming, add a one-line comment `# reason: ...` before the construct and ensure tests are provided.
- **Refactoring Process**: When refactoring large helpers, propose a splitting plan and make changes step-by-step.
- **OOP vs Module Decision**: When uncertain between OOP and module, choose module/functional style and propose a class if state/extensibility requirements arise.
