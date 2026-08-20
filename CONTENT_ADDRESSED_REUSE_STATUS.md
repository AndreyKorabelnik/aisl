# Content-addressed producer reuse — Block C completed

Status: **Block A + Block B + Block C implemented and accepted for the current typed producer DAG.**

## Active architecture

The canonical execution path remains unchanged:

`Sources -> Core/physical-model producers -> Runner DAG -> KLC materializations -> Prepared Knowledge`

Content-addressed reuse now applies at the normal immutable node boundaries of that path:

- PDM / physical-model preparation;
- Core evidence analyzer nodes, independently per analyzer and source snapshot;
- KLC materialization DAG nodes, independently per materialization and effective input set.

There is no whole-job cache, copied final Knowledge Product, second Runner, second materializer, dual-read/write path, or alternate source of truth. A miss, invalidation, corruption, or `--force-rebuild` executes the same canonical producer/materializer that would run without reuse.

The same filesystem-backed `ProducerArtifactStore` introduced in Blocks A/B is reused for KLC. Block C did not add a second cache implementation.

## KLC reuse identity

A KLC node reuse key is built from semantic/contract identity rather than job-local output identity:

- exact `knowledge-layer-core` version, including prerelease suffix;
- materialization id and scope id;
- KLC request schema version;
- materialization contract fingerprint;
- generic KLC runtime contract fingerprint;
- semantic materialization parameters;
- effective evidence inputs by artifact kind/schema/content fingerprint;
- effective upstream knowledge inputs by model/schema and the upstream materialization's stable producer reuse key.

Build-local paths, job ids, timestamps, execution ids, and raw downstream KLC fingerprints are deliberately not key material. This is required because KLC result/manifest fingerprints include build-local provenance and are not stable identity across equivalent runs.

## Integrity and provenance discipline

Reuse is not accepted from key presence alone.

For each KLC cache entry the store records SHA-256 and size for the complete immutable materialization payload, including DuckDB bytes and result/manifest files. A hit is revalidated before use. Missing, malformed, mismatched, or corrupted payloads become an explicit `cache_invalid` decision, are quarantined with a diagnostic, and are rebuilt canonically.

On a KLC cache hit the immutable knowledge bytes are restored into the current execution root. The cached build receipt itself is not mutated. Runner emits a fresh execution-local `materialization-result.json` whose output/artifact locations point at the current run and whose `result_fingerprint` is recomputed. This prevents a reused execution from retaining stale absolute paths to the original build run.

`--force-rebuild` bypasses valid Core and KLC hits for the current execution. For an already valid immutable content-addressed entry with the same semantic key, the existing cache entry is preserved rather than overwritten; force is an execution bypass, not mutable cache replacement.

## Real acceptance — `extend-data-model-attribute-v1`

Inputs: same UCP Java sources, `datamart_profile_fl` as SQL-A, `custom_b2c_insurance` as SQL-B, and the same PDM. DuckDB: 4 GB / 1 thread.

### Cold SQL-A build

- PDM preparation: BUILD (`cache_miss`).
- Runner producer DAG: **13 BUILD / 0 REUSE**.
  - 4 UCP Core analyzer nodes BUILD;
  - SQL-A Core analyzer BUILD;
  - 8 KLC materializations BUILD.
- Runner elapsed: **219.53 s**.
- status: completed, exit 0.

### Exact SQL-A repeat

PDM preparation was independently confirmed as REUSE. In the Runner DAG:

- 4 UCP Core nodes: REUSE;
- SQL-A Core node: REUSE;
- all 8 KLC materializations: REUSE;
- Core analyzer executions: 0;
- KLC worker executions: 0;
- producer summary: **0 BUILD / 13 REUSE**;
- final post-provenance-fix elapsed: **7.76 s**;
- status: completed, exit 0.

Measured Runner speedup versus the cold SQL-A build: **~28.3x** (`219.53 / 7.76`).

### SQL-A -> SQL-B selective invalidation

PDM preparation: REUSE.

Runner producer decisions:

- 4 UCP Core nodes: REUSE;
- SQL-B Core analyzer: BUILD;
- `code-declared-data-model`: REUSE;
- `model-storage-semantics`: REUSE;
- `physical-model`: REUSE;
- `logical-storage-mapping`: REUSE;
- `sql-analysis`: BUILD;
- `cross-artifact-data-model-mapping`: BUILD;
- `sql-target-source-mapping`: BUILD;
- `data-model-attribute-extension-context`: BUILD.

Summary: **5 BUILD / 8 REUSE**, status completed, exit 0.

This closes the Block B gap: KLC nodes whose effective inputs did not change are no longer rebuilt; the SQL-dependent descendants do rebuild.

The SQL-B run still took **221.72 s** because the changed SQL Core analysis and the SQL-dependent KLC subtree are genuinely expensive. Block C is therefore a large improvement for exact repeats and a selective improvement for changed-SQL compositions, not a whole-job shortcut.

### Real force-rebuild

Against a populated SQL-A cache:

- all 5 Core analyzer nodes: BUILD with `force_rebuild`;
- all 8 KLC materializations: BUILD with `force_rebuild`;
- producer summary: **13 BUILD / 0 REUSE**;
- elapsed: **215.88 s**;
- status completed, exit 0.

## Block C conclusion

The current typed producer DAG now has one universal content-addressed reuse mechanism from physical-model/Core evidence through KLC materialization. The original Block C acceptance target is met.

Further cache work is not recommended merely for architectural completeness. A possible future optimization is to avoid copying/re-hashing large immutable KLC payloads on every hit through a safe reference/publication model; that would change storage/publication semantics and is parked until measurements justify it.
