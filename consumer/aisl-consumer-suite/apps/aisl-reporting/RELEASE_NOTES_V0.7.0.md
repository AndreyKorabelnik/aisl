# aisl-reporting 0.7.0

Introduces the user-requested artifact pipeline and the first artifact product: `conceptual-data-model/v1`.

## Architecture

```text
ArtifactRequest
  -> typed KLC dataset builder
  -> schema and context-budget validation
  -> one semantic synthesis call OR deterministic conservative projection
  -> deterministic provenance grounding
  -> strict artifact validation
  -> raw JSON artifact
```

There is no preliminary LLM analysis, analysis bundle or `final_response.json`.

## Conceptual data model

- complete source-object, source-association and physical-asset coverage ledgers;
- high-recall semantic synthesis contract;
- deterministic conservative projection for regression/recovery, explicitly not presented as semantic synthesis;
- exact Java classes and evidence refs populated from source IDs after synthesis;
- association endpoints validated against the actual source/target objects of each relationship;
- safe output paths and portable datasets;
- UCP migration gate preserving or strengthening all 35 old profile capabilities.
