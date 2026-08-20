# Knowledge Integration 0.1.16 release notes

- Data Model profile upgraded to resource version 2.
- Tool catalog contract advanced to v9.
- Added `get_data_model_object_context`, a deterministic object-centric read tool over published data-model knowledge.
- The tool is available from the declared-model capability and reports optional storage enrichment explicitly when published.
- External LLMs remain responsible for reasoning and orchestration; the Knowledge API performs no LLM calls.
