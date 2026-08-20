# static-analysis-runner 0.10.6

Hardens isolated KLC materialization workers after restoring cross-repository value-flow planning.

- Keeps the 0.10.5 typed planning for `cross-repository-attribute-lineage`.
- After a KLC worker has durably written its typed result and flushed stdout/stderr, the disposable worker process exits directly instead of waiting on interpreter-shutdown finalizers.
- This avoids the observed long tail where DuckDB finalizers could keep a completed materialization worker alive.
- No materialization-specific dispatch, Suite/Task semantics, topology dependency, fallback or dual-write is introduced.
