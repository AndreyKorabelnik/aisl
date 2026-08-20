# knowledge-api 0.3.0a3

## Purpose

Close the production API defects exposed by the complete UCP source replay.

## Changes

- accept KLC polymorphic target values represented as plain FQCN strings or mappings;
- ignore empty polymorphic targets and remove duplicates while preserving order;
- resolve known polymorphic objects through the public catalog and derive safe names for unknown owned types;
- populate exact `relationship_count` values in table summaries with one aggregate KLC query;
- preserve the existing `/api/knowledge/v1` schema and route set.

## Full-source validation

The release was validated using the supplied full `UCPDataModel` and `UCPucp-tsa-v4` archives:

- 2/2 repositories analyzed;
- 528,494,592-byte DuckDB Knowledge Layer published;
- 312 public API tables;
- `Individual`: 53 fields, 1 key, 40 relationships;
- `identifications`: 8 valid polymorphic targets;
- `partyToPartyGroups`: 11 valid polymorphic targets;
- direct Knowledge API and analysis-ui same-origin proxy: 8/8 byte-identical routes.
