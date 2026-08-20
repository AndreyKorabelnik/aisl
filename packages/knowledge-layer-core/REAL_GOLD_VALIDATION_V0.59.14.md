# Real Gold validation — knowledge-layer-core 0.59.14

Validation basis: full real UCPDataModel + UCP TSA + full datamart SQL/workflow evidence, with the physical-model input restricted only to the two real PDM target tables `epk_client_doc` and `epk_client_doc_flags`. No SQL/source fixture or synthetic logical model was used.

Compared with 0.59.13 on the same real slice:

- logical-field physical-lineage evidence rows: 448 -> 472;
- target-column coverage: 34 -> 38;
- `epk_client_doc_flags.doc_id`: restored from the eight observed concrete document subtypes;
- `epk_client_doc_flags.enddate`: restored from `DocumentFlag.endDate`;
- `epk_client_doc_flags.flag_id`: restored from `DocumentFlag.id`;
- `epk_client_doc_flags.versionstartdate`: correctly has both `DocumentFlag.startDate` and `DocumentFlag.versionStartDate` as observed inputs because the SQL derives it with `least(...)`;
- `epk_client_doc.startDate`: deliberately NOT auto-resolved because one joined relation remains opaque. One `unqualified_column_owner_candidate` diagnostic is published instead.

The full 470-target rebuild was not used as the release gate in this environment because the unchanged 0.59.13 baseline also exceeded the same execution limit. This is therefore not evidence of a 0.59.14 performance regression.
