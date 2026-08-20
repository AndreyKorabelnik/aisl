# analysis-ui 2.0.0a89

Architecture Boundary Simplification — Control Plane / Runner product ownership.

- Removed Runner-owned product semantics from `ProfileInfo`: `required_external_inputs`, `expected_capabilities`, and `knowledge_input_requirements`.
- Added read-only `/api/v1/knowledge-products`, a compact projection of the pinned Runner `knowledge_catalog/v2`.
- Frontend product labels now come from the Runner-owned catalog instead of hardcoded product maps.
- Removed frontend product-ID logic that reconstructed which Knowledge Products require PDM.
- Kept scenario/input UX separate from product semantics; PDM UI is driven by the scenario's explicit context parameter until a generic Input Context Contract is introduced.
- No Core/KLC/Knowledge API/Assistant production semantics changed.
