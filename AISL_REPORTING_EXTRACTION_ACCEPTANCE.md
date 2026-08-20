# AISL Reporting Extraction Acceptance

Acceptance criteria:

1. canonical framework contains no `knowledge-reporting` package;
2. KCP has no reporting command, report stage or report output lifecycle;
3. producer run ends after immutable AISL publication;
4. Knowledge API revision contract has no report slot;
5. Knowledge API exposes no `/reports` endpoints;
6. report bytes and SHA do not participate in AISL revision identity/reachability;
7. `aisl-reporting` is installable as an independent module;
8. `aisl-reporting` reads a pinned published revision through Knowledge API only;
9. Core/Runner/KLC/KCP are not runtime dependencies of `aisl-reporting`;
10. absence of Reporting does not change produced knowledge.
