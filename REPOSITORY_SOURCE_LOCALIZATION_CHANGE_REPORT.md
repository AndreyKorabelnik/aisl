# Repository Inventory — Source Localization Change Report

Date: 2026-08-17  
Status: **COMPLETE**

## Goal

Add a generic framework capability that traces published Repository Inventory knowledge back to observed source provenance without creating a second source parser, source scanner, benchmark-specific locator or source-export/security subsystem.

`SourceOccurrence` is provenance for observed evidence. It is not itself proof of a semantic concept.

## Block A — provenance audit

The audit found no mandatory provenance class that required a Core change.

- repository structure already publishes repository-relative file paths and file SHA-256;
- Java structure evidence publishes source refs with declaration/line ranges;
- SQL analysis publishes official facts with file and line ranges;
- structured-file shape evidence supports honest file-level provenance plus SHA;
- data-model and several persistence/storage evidence products already expose source refs.

The principal loss was downstream aggregation: Repository Inventory retained artifact/evidence identity but did not expose a normalized reusable source occurrence.

Therefore Core remains unchanged at `0.44.23a7`.

## Blocks B-C — generic SourceOccurrence and linkage

KLC `0.61.0a37` advances Repository Inventory to `repository-inventory/v4` and adds normalized relations:

- `repository_inventory_source_occurrence`;
- `repository_inventory_object_occurrence`.

A SourceOccurrence contains only proven source provenance available from official evidence contracts: repository-relative path, localization precision, observed line range when available, file SHA when available, and provenance basis.

Supported precision is bounded to the provenance actually present: `exact_span`, `declaration`, `statement`, `section`, `file`. Missing precision is not guessed.

Knowledge linkage is generic and many-to-many. Current links cover structural families/members, discovery candidates, concept classifications and source-localizable coverage gaps.

Concept meaning is not copied into SourceOccurrence. The trace remains concept classification → evidence/family → occurrence.

## Block D — coverage/unresolved provenance pass-through

Coverage gaps stay fully published. They are not forced into a source-localized shape.

Repository Inventory now exposes explicit localization scope/status, including:

- `source_occurrence / localized` when provenance naturally exists;
- `evidence_artifact / not_source_localized`;
- `analysis_scope / not_source_localized`;
- `unresolved / unresolved`.

Only related family provenance or explicit diagnostic `source_ref/source_refs` can create a source link. Paths mentioned only in diagnostic text are deliberately ignored.

## Block E — thin read boundary

Prepared Knowledge Runtime `0.1.0.post11` and Knowledge API `0.36.0` expose read-only occurrence queries:

- list/filter SourceOccurrences by object/path/precision;
- get one occurrence with reverse knowledge-object links;
- coverage-gap localization scope/status.

The API reads prepared immutable knowledge only. It never reads industrial source and performs no concept inference or benchmark selection.

## Block F — Portfolio aggregation

Portfolio carries occurrence IDs/metadata only, not source paths or bytes:

- concept summaries can reference occurrences of their top observed family;
- discovery candidates carry occurrence IDs;
- coverage gaps carry occurrence IDs plus localization scope/status.

Portfolio does not cluster, select representatives, localize source or implement Benchmark Miner behavior.

## Block G — real acceptance

Fresh UCP and datamart Repository Inventory publications succeeded and were queried through the API.

Validated examples include:

- Java concept evidence → exact source occurrence with verified file SHA;
- one Java structural family with 40 occurrences;
- YAML file-level occurrence with verified SHA;
- novelty and unknown-primitive candidates with occurrence IDs;
- a source-localized coverage gap;
- analysis-scope and unresolved gaps with zero fabricated SourceOccurrences;
- Portfolio occurrence IDs without copied source paths;
- Miner-style candidate ID → occurrence ID → API lookup without source scanning.

For SQL statement precision, fresh official Core `sql-analysis/v1` evidence contained 475 `sql_statement` facts. The official Repository Inventory family builder produced the `sql_statement` family with count 475, and the generic SourceOccurrence graph produced exactly 475 statement occurrences with line ranges and file SHA. The default preflight Repository Inventory intentionally treats `sql-analysis` as `existing_only`; it does not launch deep SQL analysis itself.

## Architecture invariants

- Core owns observed evidence/provenance and is unchanged.
- KLC owns derived Inventory knowledge and knowledge-object → occurrence linkage.
- SourceOccurrence remains provenance, not semantic proof.
- Repository Inventory remains complete: known, novelty, unknown, coverage gaps, unresolved and diagnostics are all preserved.
- No source parser/scanner was added downstream.
- No source export, Security workflow, redaction, reducer, minimizer or pseudonymizer was added.
- Coverage gaps are not automatically promoted to benchmark cases.
- No backward-compatibility adapter or dual-read/write path was introduced.
