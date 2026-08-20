# aisl-reporting architecture

`aisl-reporting` has two explicit product pipelines over typed analysis artifacts.

## Reports

```text
ReportRequest v2
  -> profile/input-kind guard
  -> deterministic ReportDataset
  -> schema and evidence validation
  -> one short renderer call
  -> validated Markdown
```

## User-requested artifacts

```text
ArtifactRequest
  -> versioned artifact profile
  -> deterministic ArtifactDataset
  -> dataset + synthesis-context budgets
  -> semantic renderer OR deterministic conservative projector
  -> profile-specific deterministic grounding
  -> profile-specific strict validator
  -> raw JSON artifact
```

The generic artifact runtime knows nothing about conceptual-model semantics. Each artifact profile owns its builder, optional projector, grounder, schemas, prompt and validator.

For `conceptual-data-model/v1`, the LLM may decide concept grouping, business-facing names, stereotypes and explicit coverage dispositions. It may not invent source IDs or provenance. Exact Java classes and evidence refs are reconstructed from selected object, field and relationship IDs after synthesis.

No pipeline uses preliminary analysis profiles, analysis bundles, arbitrary DuckDB SQL or `final_response.json`.
