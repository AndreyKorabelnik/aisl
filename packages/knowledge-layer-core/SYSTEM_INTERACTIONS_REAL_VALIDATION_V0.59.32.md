# Real validation — composed member value paths — KLC 0.59.32

Workspace: the four Manual Gold interaction repositories.

After KLC 0.59.31, all 46 field contracts crossed repository boundaries, but composed update/create wire nodes did not retain the local paths already observed on their six raw member call-site interfaces.

KLC 0.59.32 preserves that structure using explicit intra-repository identity edges:

`raw member HTTP wire -> composed HTTP boundary wire` for request values, and the reverse direction for response values.

Real counts:
- repository value nodes: 25,037;
- repository value-flow edges: 20,575;
- cross-repository transport edges: 46;
- composed-boundary member edges: 420.

Representative real acceptance (`name.surname`, one update/create member call site):
1. local serialized request field -> raw member request wire: confirmed;
2. raw member request wire -> composed update/create request wire: confirmed;
3. composed update/create request wire -> target request wire: probable.

Resolver result: `probable_complete`, no gap.

This does not collapse six local scenarios into one value origin; all observed member paths remain separately traversable while sharing one technical outbound boundary.
