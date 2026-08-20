# Test status — iteration 92 KLC

## Focused tests

- `tests/test_sql_analysis_knowledge_layer.py`
- `tests/test_sql_workflow_context.py`

Result: **16 passed, 0 failed**.

Covered:

- existing SQL artifact build and workflow-context contracts;
- ranking a published business target before a technical intermediate;
- explainable reasons and target kind;
- capability exposure;
- argument validation;
- prevention of repeated-workflow score inflation.

## Real repository smoke

Source: existing `datamart_profile_fl` Knowledge Layer built by KLC 0.52.6.

Request hints:

- source relations: `Individual`, `BirthPlace`, `Region`;
- source columns: `birthPlace`, `regionCode`, `name`;
- business entity: `client`.

Result:

- candidate inventory: 77 logical targets;
- rank 1: `epk_client`;
- kind: `published_or_terminal`;
- reasons include `declared_workflow_target`, `business_entity_primary_suffix`, `target_consumed_outside_own_workflow`;
- no DuckDB rebuild or source reanalysis required.

## Deliberately not run

The full KLC suite was not run. No schema, ingestion, builder, data-model, topology or non-SQL materialization code changed. The new surface is a read-only query over existing tables and is covered by focused tests plus a real artifact smoke.
