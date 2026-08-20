# knowledge-control-plane 1.2.0a31

- Repins the generated Runner knowledge catalog to static-analysis-runner 0.10.28.
- The pinned `code-declared-data-model` policy now carries the canonical optional `logical-storage-mapping` enrichment; KCP remains orchestration-only and does not implement storage semantics itself.
- Core evidence catalog and KLC materialization catalog remain unchanged at Core 0.44.23a7 / KLC 0.61.0a38.
- No second catalog, planner, producer or compatibility path is added.
