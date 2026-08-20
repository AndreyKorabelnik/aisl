# knowledge-api 0.30.7

- Declared-object search now publishes retrieval score/basis, bounded match evidence and observed binding summary.
- Declared-object detail exposes incoming binding summary.
- Retrieval score is lexical ranking metadata and is not semantic confidence.
- Declared-model query read contract is `code-declared-data-model-query/v2`; deployment pins the matching prepared runtime.
