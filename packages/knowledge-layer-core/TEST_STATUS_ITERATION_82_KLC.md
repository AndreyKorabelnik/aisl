# Test status — iteration 82 KLC

## Focused tests

- `tests/test_sql_analysis_knowledge_layer.py`: 7 passed.

## Real datamart validation

Input: `code-analyzer-core 0.43.6` SQL artifact for `datamart_profile_fl`.

- SQL facts imported: 27,600 canonical records across the typed streams.
- business-source relations exported: 208;
- used fields exported: 1,503;
- relation evidence occurrences counted: 441;
- field evidence occurrences counted: 3,157;
- JSONL records: 209;
- JSONL byte size: 1,469,920;
- repeated export SHA-256: `1a53aad0e1fdda0d5fa7163daef79b7e6d55dbdfa1e913ae0ac8811f8924e07d`.

The two independent writes from the same Knowledge Layer produced identical bytes and hash.
