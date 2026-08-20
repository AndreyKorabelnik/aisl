# Real validation — workspace interaction richness — Reporting 0.17.6

Input knowledge uses the real four-repository workspace with KLC 0.59.32.

Observed dataset result:
- business interactions: 3;
- field contracts: 46;
- cross-repository transport edges: 46;
- available representative journey candidates: 20;
- selected detailed journey cards: 5.

Selected journeys include update/create fields. Where KLC exposes raw-member serialization prefixes, Reporting now starts before the composed boundary rather than at the HTTP wire.

Examples:
- `birthDate.endDate`: source-local serialization -> raw member wire -> composed boundary wire -> target transport; six observed local variants;
- `name.endDate`: same three-segment technical structure; six observed local variants.

For deeper fields where no raw serialization prefix is observed, the report deliberately starts at the composed boundary wire and does not invent a local segment.

The renderer prompt must state that a selected prefix is representative, not canonical, when multiple local variants exist.
