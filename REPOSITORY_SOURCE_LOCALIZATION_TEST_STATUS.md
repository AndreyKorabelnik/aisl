# Repository Inventory — Source Localization Test Status

Date: 2026-08-17  
Status: **PASS**

## Changed-runtime regression

- knowledge-layer-core `0.61.0a37`: **262 PASS / 8 SKIP** across four independently completed test groups. The monolithic run timed out part-way and was not counted.
- prepared-knowledge-runtime `0.1.0.post11`: **12/12 PASS**.
- knowledge-api `0.36.0`: **118/118 PASS** across independently completed groups.
- knowledge-control-plane `1.2.0a29`: **95/95 PASS**.
- KCP targeted generated-catalog/baseline gate: **35/35 PASS**.

## Unchanged runtime

`code-analyzer-core` and `static-analysis-runner` are byte-identical to the previous sparse-classification canonical, excluding transient test caches. Their previously authoritative regressions therefore remain applicable to identical code bytes:

- Core `0.44.23a7`: **610/610 PASS**.
- Runner `0.10.27`: **113/113 PASS**.

No new Core/Runner PASS is claimed from an unexecuted suite; this is explicit regression inheritance by byte identity.

## Real acceptance

- fresh UCP KCP → Runner → Core → KLC → Knowledge API publication: **PASS**;
- fresh datamart preflight Repository Inventory publication: **PASS**;
- Java exact-span + file-SHA verification: **PASS**;
- YAML file-level + file-SHA verification: **PASS**;
- official Core SQL `sql-analysis/v1` analyzer output: **475 sql_statement facts**;
- official Inventory SQL family builder + SourceOccurrence normalization: **475/475 statement occurrences PASS**;
- novelty/unknown occurrence linkage: **PASS**;
- localized vs analysis-scope vs unresolved gap behavior: **PASS**;
- Portfolio ID-only aggregation: **PASS**;
- Miner-style occurrence selection through API without source scan: **PASS**.

The full heavy SQL knowledge materialization attempted after Core SQL analysis exceeded the execution window and was terminated. It is explicitly **not counted as PASS** and is not a functional requirement of Source Localization.

## Setup-only events

Several early commands failed because the ad-hoc test environment lacked offline dependencies or console-script entry points. They were rerun with the canonical/offline dependencies or external acceptance-only CLI shims. No shim was added to framework source. Setup failures are not counted as functional failures or PASS.
