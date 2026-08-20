# code-analyzer-core 0.43.24 — specialized sufficiency cleanup

This release removes the temporary conceptual-model-specific architecture audit from Core.

The platform now uses the generic Runner-owned `knowledge_architecture_audit/v1` for readiness assessment of any knowledge type. Core continues to own only its general analysis catalog, target boundary contracts, source observations and future typed evidence contracts.

No analysis runtime, profile, Foundation, scanner, prepared artifact or legacy materializer behavior changed in this release.

There is intentionally no compatibility adapter for the removed CLI command.
