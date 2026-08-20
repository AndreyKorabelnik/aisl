# knowledge-integration 0.1.2

- Bumped `attribute-addition-plan/v1` to profile version 10.
- Added an explicit source-extraction mode for questions that ask for source-table JOINs / SQL extraction without modifying a target datamart.
- Changed retrieval guidance to short discovery (`include_fields=false`) followed by one exact object and its declared relationships.
- Prioritized evidence for executable JOINs as observed SQL → published KLC technical JOIN context → PDM structural relationship → explicitly marked interpretation.
- Kept declared relationships distinct from physical SQL JOIN evidence.
- Made the source-extraction answer concise and centered on Source / Relations and JOIN / SQL / Gaps rather than raw tool JSON/provenance.
- Tool catalog and public tool set are unchanged.
