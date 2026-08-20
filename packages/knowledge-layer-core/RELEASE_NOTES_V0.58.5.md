# knowledge-layer-core 0.58.5

HTTP interaction matching no longer treats loopback addresses observed in test configuration as production address conflicts. The original localhost evidence remains visible, but is explicitly non-binding. Raw Java variables such as `updateOrCreateLightClientPath` are no longer normalized as host authorities.

This fixes real application matching for exact HTTP method/path candidates when the production base URL remains an unresolved configuration binding. Such matches are published as `probable`, not `confirmed`.
