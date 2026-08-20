# Analysis UI 2.0.0a78

Adds System Description to the existing generic Knowledge Profile workflow.

- Adds `system-description-v1` as a source-backed multi-repository Knowledge Profile using the existing `repositories` source mode and workspace execution path.
- The profile requests only the existing `system-description` Knowledge Product, uses reporting profile `system-description/v1`, and opens the same generic revision-bound chat with Assistant policy `system-description/v1`.
- No System-Description-specific wizard, executor, context type or Assistant runtime was introduced.
- Business-purpose questions remain chat-time LLM interpretation over prepared knowledge; the production wizard selects only stable repository context.
- Runtime dependency is aligned to Knowledge Assistant 0.21.x; Core 0.44.16 / Runner 0.10.9 / KLC 0.59.36 contracts remain unchanged.
