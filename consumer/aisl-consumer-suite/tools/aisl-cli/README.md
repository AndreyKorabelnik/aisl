# aisl-cli 0.2.0

Generic CLI for consuming published AISL knowledge through Knowledge API.

It is a thin command-line layer over `aisl-sdk`. It does not run Core, Runner,
KLC or KCP; it does not select LLM tools; and it does not invent missing joins,
storage mappings or business meaning.

## Install

```bash
pip install ./aisl_sdk-0.3.0-py3-none-any.whl
pip install ./aisl_cli-0.2.0-py3-none-any.whl
```

The installed command is:

```bash
aisl --version
```


## Export a complete data-model object

```bash
aisl project data-model-object \
  --api-url http://127.0.0.1:8080 \
  --system-id ucp-data-model \
  --revision-id rev-... \
  --profile data-model/v1 \
  --object com.sbt.bm.ucp.retail.model.individual.Individual \
  --output individual.json
```

`--object` accepts an exact object id, exact FQCN, or a unique object name. Prefer
an object id or FQCN for deterministic automation.

If `--revision-id` is omitted, the active revision is resolved once and then pinned
for the command execution.

## Generic agent/tool usage

List the canonical tools allowed by a profile:

```bash
aisl tools \
  --api-url http://127.0.0.1:8080 \
  --system-id ucp-data-model \
  --profile data-model/v1
```

Execute a tool already selected by the caller/LLM:

```bash
aisl call \
  --api-url http://127.0.0.1:8080 \
  --system-id ucp-data-model \
  --profile data-model/v1 \
  search_declared_data_objects \
  --args-json '{"repo_id":null,"search":"Individual","type_annotations":[],"include_fields":false,"offset":0,"limit":20}'
```

The CLI deliberately preserves published `ambiguous`, `not_observed`, gaps and
provenance. A declared relationship is not promoted to a confirmed physical JOIN.
