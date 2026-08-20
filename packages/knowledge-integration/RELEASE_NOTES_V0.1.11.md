# knowledge-integration 0.1.11

Consumer ergonomics for `attribute-addition-plan/v1` profile v13.

- Keeps the same capability-gated tool name/count and one pinned revision.
- Routes `get_data_model_attribute_extension_context` to the Knowledge API compact attribute-extension guidance projection instead of the full canonical detail payload.
- The projection surfaces KLC-owned `usefulness`, exact-vs-analog SQL JOIN relevance, storage-reference observations, key/reference expressions, SQL anchors, residual checks and explicit gaps without adding inference.
- Full canonical attribute-extension detail remains available in Knowledge API for targeted verification; truncation in the compact projection is explicit and must not be interpreted as absence.
- Tool catalog contract version is now 4; profile version is 13.
