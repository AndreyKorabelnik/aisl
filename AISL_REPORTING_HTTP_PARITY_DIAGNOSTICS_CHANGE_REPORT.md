# AISL Reporting HTTP Parity & Diagnostics — 2026-08-19

Observed user acceptance after 0.4.2: mTLS/TLS and HTTP/2 succeeded far enough to receive HTTP 404 from the corporate LLM service. Therefore TLS handshake is no longer the active gap.

0.4.3 narrows the remaining transport delta with the user's successful curl: explicit JSON Accept/Content-Type headers, redirect following, and useful HTTP diagnostics. The exact report payload can be replayed using the prepared `renderer-messages.json`.

No AISL producer/server/knowledge contract changed.
