# code-analyzer-core 0.44.15

- SQL scoped analysis no longer aborts an entire repository when SQLGlot reports a duplicate relation alias while lazily resolving `Scope.selected_sources`.
- Ambiguous SQL is preserved conservatively: relation/projection/join observations remain available and affected column usages keep the existing `ambiguous / ambiguous_alias` resolution status.
- No alias guessing or silent fallback is introduced; lexical CTE/derived scope linking is skipped only for the failing SQLGlot scope.
