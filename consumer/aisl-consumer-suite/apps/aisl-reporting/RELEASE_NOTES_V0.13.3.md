# aisl-reporting 0.13.3

## AT900 pilot-quality reporting

### System description

- Enforced the configured report-detail budget instead of copying complete relationship and interface payloads into several sections.
- Removed compatibility duplicate sections for interfaces, integrations and relationships.
- Kept complete boundary counts and compact catalogs while retaining exact provenance in the bounded interface map and representative journeys.
- Limited the standard dataset to 20 relationships, 25 representative physical objects, 14 evidence-rich interface entries, 16 dependencies and 20 technical references.
- Replaced raw token-frequency capability grouping with conservative, interface-backed, source-diverse candidates.
- Transport/configuration vocabulary and identifier-like acronyms no longer become business capability labels.
- Data-domain groups now use simple physical object names rather than schema prefixes or free-form comments and may overlap when one table belongs to several themes.

### Data model report

- Added explicit report modes: `logical_and_physical`, `logical_only`, `physical_only`, and `not_observed`.
- When no logical object model is observed but physical tables and relationships exist, the report uses `physical_only` and treats the physical model as the primary observed model.
- Added physical object and relationship counts to coverage and section status.
- Removed hidden selection/substitution language from the deterministic dataset and renderer contract.
- The renderer is prohibited from inventing logical entities when only physical evidence exists.

### Validation

- Fresh AT900 default-system-analysis completed on 1,038 files with Core 0.43.18, Runner 0.9.29 and KLC 0.53.4.
- System-description canonical dataset: 218,518 bytes, 152 evidence entries, no dangling evidence.
- Data-model canonical dataset: 61,283 bytes, 75 evidence entries, no dangling evidence.
- Full aisl-reporting suite: 54 passed, 16 optional skipped.
- Real AT900 profile tests: 2 passed.
