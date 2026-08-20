# AISL Reporting LLM Transport — 2026-08-19

Observed production-like failure: report dataset preparation and validation succeeded, but LLM rendering failed with `RemoteProtocolError: Server disconnected without sending a response`. The same endpoint succeeded via curl only when a client certificate/key and insecure TLS mode were supplied; curl negotiated HTTP/2.

Change is bounded to `aisl-reporting` renderer transport configuration. No AISL producer/server/knowledge contract was changed.

Canonical renderer options now include mTLS certificate/key, CA verification, explicit insecure mode, and optional HTTP/2. Defaults remain TLS verification enabled and HTTP/1.1. No silent TLS fallback is allowed.

Acceptance: aisl-reporting 103/103 PASS; CLI transport option smoke PASS. Real endpoint re-test remains external/user-environment acceptance because the endpoint and certificates are not available in this runtime.
