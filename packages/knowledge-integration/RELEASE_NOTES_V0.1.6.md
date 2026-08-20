# knowledge-integration 0.1.6

- Separates source pagination (`source_has_more`) from model-view projection truncation (`projection_truncated`).
- Adds deterministic batch model-result merging for independent declared-object discovery calls.
- Batch discovery de-duplicates candidates by observed identity and preserves lexical query/task provenance without inventing semantic scores.
- Data-model retrieval guidance states that `search_declared_data_objects.search` is lexical discovery: use short independent terms rather than concatenated synonym strings.
