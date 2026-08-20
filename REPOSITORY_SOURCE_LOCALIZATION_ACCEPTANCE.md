# Repository Inventory — Source Localization Acceptance

Date: 2026-08-17  
Status: **PASS**

Machine record: `validation/repository-source-localization-2026-08-17/REAL_SOURCE_LOCALIZATION_ACCEPTANCE.json`.

## Real publications

### UCP Java data model

Fresh publication:

- system: `source-occ-ucp`;
- revision: `rev-098c480dfa59d679c5633a89`;
- normalized SourceOccurrences: **670**;
- object-occurrence links: **2010**.

A known `data_model` classification traces through its observed family/evidence to:

- `ucp-common-api/src/main/java/com/sbt/bm/ucp/model/DedupEdge.java`;
- localization: exact span, lines **6-65**;
- file SHA-256 verified against the real source file.

The same observed structural family has **40** source occurrences, proving that Inventory preserves multiplicity rather than selecting a benchmark representative.

### Datamart SQL / YAML

Fresh preflight Repository Inventory publication:

- system: `source-occ-datamart`;
- revision: `rev-2f7821f46c65b37826589675`;
- normalized SourceOccurrences: **491**;
- object-occurrence links: **2188**.

A YAML structural occurrence is file-level and its SHA-256 was verified against the real source file. No YAML node span is invented because the current official structured-file evidence does not publish one.

Fresh official Core `sql-analysis/v1` evidence separately completed its SQL analyzer stage with **475** `sql_statement` facts. The official Repository Inventory `_evidence_families()` builder produced a `sql_statement` family of count **475**; generic SourceOccurrence normalization produced exactly **475** `statement` occurrences. A sample SQL file SHA was verified against the real repository file.

The later heavy SQL knowledge derivation did not finish within the execution window and is **not counted as PASS**. It is not required for this source-provenance acceptance because the official Core SQL evidence had already completed and Source Localization consumes that evidence without reparsing source.

## Coverage/unresolved cases

Verified:

- a source-localized structural discovery gap has **592** occurrence links;
- a concept-evaluation gap is `analysis_scope / not_source_localized` and has **0** source occurrences;
- an unresolved gap is `unresolved / unresolved` and has **0** source occurrences.

No source file/span was fabricated for the non-localized cases.

## Benchmark/Portfolio boundary

Verified through published API/Portfolio data:

- unknown primitive and structural novelty candidates carry occurrence IDs;
- Portfolio aggregates occurrence IDs but does not copy source paths into candidate records;
- a downstream Miner can select a candidate ID, list its occurrence IDs and resolve a selected occurrence through Knowledge API without scanning industrial source.

Framework stops at knowledge + SourceOccurrence + provenance. Source fragment extraction, Security review and redaction are outside this implementation.

## Limitations

- Local source snapshots may not expose a VCS revision; v1 does not invent one.
- Structured JSON/YAML evidence currently provides file-level localization, not node spans.
- Preflight Repository Inventory does not produce deep `sql-analysis`; statement precision becomes available when official `sql-analysis/v1` evidence exists.
- Analysis-scope/unresolved gaps intentionally may have no SourceOccurrence.
