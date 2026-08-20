# knowledge-api 0.5.1

Iteration 24 integration hotfix.

- Request validation errors are normalized through the public `errors()` API.
- Pydantic-only `include_url` arguments are no longer passed to FastAPI `RequestValidationError`.
- Invalid publication payloads return canonical `422 request_validation_failed`.
