# Test status — knowledge-api 0.20.0

- Full pytest suite: 63 passed.
- `python -m compileall -q knowledge_api`: passed.
- Public OpenAPI regenerated and contract test passed.
- Real HTTP smoke: passed against existing revision `rev-e7cdcc1a0c26bb20499a258f`; `/data-model/declared-objects` searched Russian documentation and exact object detail returned 52 fields / 41 declared relationships for `Individual`.
- The real smoke reused the already published revision; no Core, Runner, or KLC production rerun occurred.
