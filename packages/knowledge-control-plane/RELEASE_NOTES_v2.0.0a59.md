# Analysis UI 2.0.0a59 — long Knowledge API publication timeout

Revision publication no longer shares the short 30-second timeout used by health, read and proxy requests. Publishing a Knowledge Layer DuckDB and report now uses `KNOWLEDGE_API_PUBLICATION_TIMEOUT_SECONDS`, default `600` seconds.

A publication timeout is reported as `knowledge_api_timeout` with the method, path, operation and configured timeout. Connection refusal and other transport failures remain `knowledge_api_unavailable`.

The change is backend-only. Frontend source and npm dependencies are unchanged.
