# AGENTS.md

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

## Code Style and Ruby Idioms

- **Readability Priority**: When there's a conflict between brevity and clarity, **prioritize clarity**, but generally strive for concise, idiomatic Ruby (Ruby way).
- **Ruby Practices**: Follow common Ruby idioms. RuboCop/formatter is recommended but not mandatory if linter rules create unnecessary complexity.
- **Standard Library**: Prefer standard library and framework tools if they simplify the task.
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

- **File Size**: If a file exceeds ~1000 lines **or** clearly contains 2+ independent responsibilities (e.g., utility methods + style formatting methods + mathematical functions), consider splitting into multiple files/modules by responsibility.
- **Single Responsibility**: One helper = one responsibility. If a helper becomes a "monolith", extract utility methods into `utils`/`services`/`presenters` as appropriate.

## Design Patterns and Principles

- **Pattern Application**: Follow basic principles (SOLID, DRY, etc.), but apply patterns contextually: use patterns if they make code clearer and more testable; avoid if they add unnecessary complexity.
- **Polymorphism**: Polymorphism is acceptable when it solves a real problem (alternative implementations, strategies, extensibility).

## Sensitive Changes and Review

- **Critical Changes**: Changes affecting database migrations, authentication/authorization, external service integrations, and secret storage require human review. Agents should not automatically merge such changes without approval.
- **Documentation**: For non-obvious changes, include a brief description of motivation and link to tests.

## StackServiceBase Integration

- **Framework Setup**: Use `StackServiceBase.rack_setup(self)` in `config.ru` to automatically configure the service with logging, monitoring, and middleware.
- **Automatic Middleware**: The gem provides built-in middleware for CORS, health checks, request profiling, authentication, and error handling.
- **Logging System**: Uses structured logging with context awareness. Access via `LOGGER` constant with methods: `info`, `debug`, `warn`, `error`.
- **OpenTelemetry Integration**: Automatic tracing when `OTEL_EXPORTER_OTLP_ENDPOINT` environment variable is set. Use `otl_span(name, attributes)` for custom spans.
- **Database Integration**: Automatic Sequel database connection with retry logic and logging integration when Sequel is present.
- **NATS Service**: Optional NATS microservice integration when `NATS_URL` environment variable is set.
- **Prometheus Metrics**: Automatic metrics collection and export when `PROMETHEUS_METRICS_EXPORT=true`.
- **Environment Variables**: Key variables include `QUIET`, `PERFORMANCE`, `STACK_NAME`, `STACK_SERVICE_NAME`, `OTEL_EXPORTER_OTLP_ENDPOINT`, `NATS_URL`.
- **Async Support**: Built-in support for Async gem with proper context propagation for OpenTelemetry.

## Agent Instructions

- **Minimal Changes**: When making corrections, minimize the scope of code changes (small diffs).
- **Metaprogramming Documentation**: If using metaprogramming, add a one-line comment `# reason: ...` before the construct and ensure tests are provided.
- **Refactoring Process**: When refactoring large helpers, propose a splitting plan and make changes step-by-step.
- **OOP vs Module Decision**: When uncertain between OOP and module, choose module/functional style and propose a class if state/extensibility requirements arise.
