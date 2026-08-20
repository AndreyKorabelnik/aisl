# knowledge-layer-core 0.59.32

Preserve member call-site value paths through composed HTTP outbound boundaries.

- Adds explicit identity composition edges between each observed raw member wire field and the corresponding KLC-composed outbound wire field.
- Request direction: raw member request wire -> composed boundary request wire.
- Response direction: composed boundary response wire -> raw member response wire.
- Preserves every observed member path instead of choosing a representative caller.
- Composition edges carry explicit provenance, composition basis and confidence; no application-specific names or Gold values are used.
- Core remains unchanged.

Real four-repository validation:
- cross-repository transport edges remain 46;
- composed-boundary member edges: 420;
- representative update/create `name.surname` path is now resolvable from a source-local serialized field through raw member wire -> composed wire -> target wire;
- path status: probable_complete because the boundary match is probable; local serialization and composition steps are confirmed.
