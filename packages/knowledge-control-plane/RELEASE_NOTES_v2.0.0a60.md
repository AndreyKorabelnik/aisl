# Analysis UI 2.0.0a60 — visible model endpoint rejection diagnostics

Analysis UI now handles `knowledge-assistant` structured model-call failures separately from generic assistant runtime errors.

An upstream HTTP 4xx response is recorded as:

- phase: `assistant.model.rejected`;
- API error code: `assistant_model_request_rejected`;
- safe details: status, duration, upstream request id, endpoint path, model, structured validation errors and request-size statistics.

Transport/5xx/empty-response failures use `assistant.model.failed` and `assistant_model_call_failed`.

Prompt text, conversation content and response body are not written to logs or API error payloads.

The package now requires `knowledge-assistant>=0.14.10,<0.15.0`. Frontend sources and npm dependencies are unchanged.
