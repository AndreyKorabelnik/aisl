# Handover — Repository Inventory Source Localization

Date: 2026-08-17  
Status: **SOURCE_LOCALIZATION_COMPLETE**

## Canonical state

Restore from the canonical/recovery ZIP produced with this release and verify its published SHA-256 and manifests before editing.

Versions:

- Core `0.44.23a7` — unchanged;
- Runner `0.10.27` — unchanged;
- KLC `0.61.0a37`;
- Prepared Knowledge Runtime `0.1.0.post11`;
- Knowledge API `0.36.0`;
- KCP `1.2.0a29`.

## Completed

Blocks A-G of Repository Source Localization are complete:

1. provenance audit showed no required Core provenance gap;
2. generic normalized SourceOccurrence contract/materialization;
3. Repository Inventory object→occurrence linkage;
4. honest coverage/unresolved localization scope;
5. thin Prepared Runtime/Knowledge API read boundary;
6. Portfolio occurrence-ID aggregation;
7. real Java/SQL/YAML/unknown/novelty/gap/API acceptance.

## Architectural boundary

Framework publishes all knowledge and provenance. SourceOccurrence is observed provenance, not concept proof.

Benchmark Miner may cluster/deduplicate/prioritize and select occurrence IDs. It must not scan source, implement concept detection or source localization.

Coverage gaps/unresolved remain fully visible and aggregatable but route to human research before becoming benchmark cases.

Source fragment extraction, Security review, redaction and export remain outside framework.

## Known limitations / gaps

- no invented VCS revision for local snapshots without revision identity;
- structured JSON/YAML localization is currently file-level;
- SQL statement localization is existing-evidence driven: preflight does not produce deep sql-analysis;
- non-source-localizable coverage gaps may correctly remain analysis-scope/unresolved.

These are explicit limitations, not silent fallbacks.

## Next step

No automatic Source Localization block remains. The natural next consumer work is Benchmark Miner consumption of Repository/Portfolio occurrence IDs, but that should be started only as an explicit product decision. Security/export/redaction scope remains outside framework.
