# AGENTS.md

## General Instructions

The description of the connected Intellij MCP server tools:
https://www.jetbrains.com/help/idea/mcp-server.html#supported-tools

- At the beginning of the session, collect the list of project files, modules, classes, methods, variables, constants. Analyze the service workflows.
  Just remember, don't print report.

- Try to add new functionality with minimal code lines, avoiding code when behavior can be achieved without it.
- Prefer concise idioms for simple expressions; avoid expanding one-line constructs into multi-line blocks without need.
- Strive to be the best Python coder: favor modern, elegant idioms and expressive, readable code.
- After applying code changes do review for the refactoring and improvements available.
- When persisting structured data, rely on the database ORM's native JSON/JSONB support instead of manual parsing/serialization.
- When using ORM JSON/JSONB fields, insert plain Python dictionaries/lists—no need to manually serialize with `json.dumps` unless specifically required.
- When performing upserts with SQLAlchemy, use `ON CONFLICT` clauses via Core or `merge` carefully, preferring explicit `get_or_create` patterns or `ON CONFLICT DO UPDATE` when available via extensions like `sqlalchemy-utils` or raw SQL if necessary.
- Prefer property decorators (`@property`) for simple computed attributes when idiomatic Python allows it.
  Use them only when the body is a single expression with no branching or side effects (e.g., attr-style accessors, simple calculations, or formatters returning a string). Fall back to regular methods whenever the logic includes assignments, conditionals, or multiple statements.

This file contains coding guidelines and architectural principles for Python microservices projects. These rules help maintain consistency and enable AI agents to work safely and predictably with the codebase.

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
- **Microservice Simplicity**: For small microservices, the main application file (e.g., `main.py`, `app.py`) can contain business logic directly. Only extract to separate files when the service grows beyond simple routing and basic functionality.

## Code Style and Python Idioms

- **Readability Priority**: When there's a conflict between brevity and clarity, **prioritize clarity**, but generally strive for concise, idiomatic Python (Pythonic way).
- **PEP 8**: Follow PEP 8 style guide. Black/formatter is recommended but not mandatory if linter rules create unnecessary complexity.
- **Python Practices**: Follow common Python idioms. Leverage list/dict comprehensions, generators, `with` statements, `pathlib`, `dataclasses`, etc., where appropriate.
- **Standard Library**: Prefer standard library and framework tools if they simplify the task.
- **HTTP Requests**: Use `requests` for REST fetch requests with proper configuration:
  - Set timeouts: `timeout=(10, 15)` (connect, read)
  - Implement retry logic using `urllib3.util.retry.Retry` and `requests.adapters.HTTPAdapter`.
  - Example:
    ```python
    from requests.adapters import HTTPAdapter
    from urllib3.util.retry import Retry
    session = requests.Session()
    retry_strategy = Retry(total=3, backoff_factor=1, status_forcelist=[429, 500, 502, 503, 504])
    adapter = HTTPAdapter(max_retries=retry_strategy)
    session.mount("http://", adapter)
    session.mount("https://", adapter)
    ```
- **Type Hints**: Use type hints (`typing` module) for function signatures and variable annotations where clarity is improved, especially for public APIs and complex functions.
- **Comments**: Minimize comments - write comments only for truly non-obvious logic. Public methods may have brief docstrings (Google, NumPy, or Sphinx style) - this is useful. Tests do **not** replace documentation for public methods.
- **Error Messages**: All error messages and log messages should be clear, concise, and in English.

## Metaprogramming and "Python Magic"

- **Metaprogramming Usage**: Metaprogramming (e.g., `getattr`, `setattr`, `__getattr__`, decorators) is allowed if it **explicitly** reduces duplication and remains readable.
- **Public API**: Avoid metaprogramming in public APIs. If used, add a brief comment explaining the reason and test(s) covering the behavior.
- **Examples**: `functools.wraps` for decorators is standard; `dataclasses` for boilerplate reduction is encouraged; `eval`/string code generation is prohibited without strict tests and documentation.

## Constructs, Compactness, and Readability

- **Compact Code**: Strive for compact code - `if/else` expressions (`x = a if condition else b`), method chaining (if clear), and concise lambdas are appropriate **if** the code is easy to read.
- **Complex Constructs**: Avoid nested `if/else` expressions and chaining longer than 3 calls if it impairs understanding.
- **Logic Decomposition**: Break complex logic into small named functions with clear names.

## File and Module Organization

- **Separation of Concerns**: Split code only when ALL conditions are met:
  - Code is reused in 2+ places OR
  - File exceeds ~500-1000 lines OR
  - Clearly contains 2+ independent responsibilities
  - **Otherwise** - keep related code together in one file

- **Microservice File Structure**:
  - **Simple services** (1-2 classes): place all files next to the main application file (e.g., `app.py`, `main.py`)
  - **Complex services** (5+ classes): create directories `services/`, `models/`, `utils/`, etc.
  - **Don't create directories "just in case"**

- **Class Utility Methods**: If a method is used only within one class - keep it as a `private` method (prefixed with `_`) of that class
- **Don't extract private methods to modules** - this complicates code without benefit
- **Create modules only for reusable code** between different classes

## Design Patterns and Principles

- **Pattern Application**: Follow basic principles (SOLID, DRY, etc.), but apply patterns contextually: use patterns if they make code clearer and more testable; avoid if they add unnecessary complexity.
- **Polymorphism**: Polymorphism is acceptable when it solves a real problem (alternative implementations, strategies, extensibility).

## Sensitive Changes and Review

- **Critical Changes**: Changes affecting database migrations, authentication/authorization, external service integrations, and secret storage require human review. Agents should not automatically merge such changes without approval.
- **Documentation**: For non-obvious changes, include a brief description of motivation and link to tests.

## StackServiceBase Integration (Conceptual for Python)

### Service Creation Foundation

- **Project Generator**: A foundational tool (e.g., `cookiecutter`, custom generator) is the foundational tool for creating new microservices. Use `python_service_generator init [option] <service_name>` to generate complete project structure.
- **Default Platform**: If no platform specified, use GitLab CI/CD (`python_service_generator init --gitlab-c <service_name>`).
- **Project Structure**: Creates complete service structure including Docker, CI/CD, tests, and basic Flask/FastAPI application with common utilities integration.

### Framework Integration

- **Framework Setup**: Integrate common utilities (logging, monitoring, middleware) via a setup function in the main application file. Example: `from common_lib import setup_app; app = setup_app()`.
- **Critical Import Order**: Import common libraries and configuration *before* importing the main web framework application in the main file.
- **Automatic Middleware**: The common library provides built-in middleware for CORS, health checks, request profiling, authentication, and error handling.
- **Health Check**: Common library automatically provides `/health` endpoint - no need to implement custom health checks.
- **Logging System**: Uses structured logging (e.g., `structlog`, `json-logging`) with context awareness. Access via `LOGGER` instance with methods: `info`, `debug`, `warning`, `error`.
- **Observability Integration**: Automatic tracing when `OTEL_EXPORTER_OTLP_ENDPOINT` environment variable is set. Use decorators or context managers for custom spans. Apply tracing only to the most critical functions, not to all functions indiscriminately.
- **Database Integration**: Automatic database connection (e.g., SQLAlchemy) with retry logic and logging integration.
- **Message Queue Service**: Optional message queue integration (e.g., NATS, RabbitMQ) when relevant environment variables are set.
- **Metrics**: Automatic metrics collection and export when relevant environment variables are set.
- **Environment Variables**: Key variables include `LOG_LEVEL`, `PERFORMANCE`, `SERVICE_NAME`, `OTEL_EXPORTER_OTLP_ENDPOINT`, relevant service URLs.
- **Async Support**: Built-in support for `asyncio` with proper context propagation for observability if applicable.

### Service Creation Commands

- **Empty Directory**: If working in empty directory, create new service with `python_service_generator init --gitlab-c <service_name>`
- **Platform Options**: `--gitlab-c` (default), `--github`, `--gitlab` for different CI/CD platforms
- **Template Structure**: Generates `src/` or `app/`, `docker/`, CI/CD configs, `requirements.txt`, main application file, and test structure

## Agent Instructions

- **Minimal Changes**: When making corrections, minimize the scope of code changes (small diffs).
- **Metaprogramming Documentation**: If using metaprogramming, add a one-line comment `# reason: ...` before the construct and ensure tests are provided.
- **Refactoring Process**: When refactoring large helpers, propose a splitting plan and make changes step-by-step.
- **OOP vs Module Decision**: When uncertain between OOP and module, choose module/functional style and propose a class if state/extensibility requirements arise.
