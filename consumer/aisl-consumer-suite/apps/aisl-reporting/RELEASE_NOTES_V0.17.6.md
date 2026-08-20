# aisl-reporting 0.17.6

Representative source-local prefixes for composed interaction journeys.

- Reuses KLC `boundary_composition` and `serialization` edges when a field contract has no single source occurrence because several raw call sites were composed into one shared outbound boundary.
- Selects one deterministic evidence-backed local prefix only for the bounded journey card and publishes the number of observed alternatives.
- Never treats the representative prefix as canonical or unique; all variants remain in KLC and execution contexts.
- Falls back to the composed transport wire when no source-local serialization prefix is observed.
- Renderer instructions explicitly explain representative source-local variants.
- No interaction matching, confidence or business semantics are changed.

Real four-repository validation on KLC 0.59.32:
- journey candidates: 20;
- selected journey cards: 5;
- update/create journeys are present;
- selected `birthDate.endDate` and `name.endDate` journeys contain source-local serialization + boundary-composition + transport;
- each exposes six observed source-local variants;
- target-local continuation remains enabled.
