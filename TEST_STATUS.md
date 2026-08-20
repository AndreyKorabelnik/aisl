# Test Status — Data Model optional storage enrichment

Date: 2026-08-17

- Runner planning/execution-planning: **49/49 PASS**.
- KCP pinned runtime contracts: **35/35 PASS**.
- affected Knowledge API + Knowledge Integration read/Consumer Kit subset: **44/44 PASS**.
- changed-package compile/import smoke and Runner/KCP source-manifest verification: **PASS**.
- fresh real UCP enriched publication: **PASS**, revision `rev-88415df4d14df2ff3827b01c`.
- real `Individual` rich object-context: **PASS**; storage available, ambiguity preserved, physical JOIN not asserted.
- minimal Java/no-storage publication: **PASS** with Core storage evidence `not_applicable` and no invented storage facts.
- full framework regression: **not run** for this focused block.

---

# Test Status — AISL storage mobility

Date: 2026-08-16

- controlled mixed observed+derived publication: **PASS**, revision `rev-a9eb627642530740ceed95fa`.
- producer workspace deletion before relocation: **PASS**.
- complete filesystem Artifact Store root relocation: **PASS**.
- same catalog/revision JSON after relocation: **PASS**.
- observed exact read after relocation: **PASS**.
- derived exact read after relocation: **PASS**.
- Knowledge API 0.33.0: **114/114 PASS**, completed groups `25 + 29 + 19 + 41`.
- Prepared Knowledge Runtime 0.1.0.post9: **10/10 PASS**.
- Knowledge Integration 0.1.15: **19/19 PASS**.
- AISL Contract 0.3.0b7: **47/47 PASS**.
- Knowledge Reporting 0.18.1: **100 PASS, 2 SKIPPED**.
- Knowledge Layer Core 0.61.0a32: **252 PASS, 8 SKIPPED**, completed groups `70/7 skipped + 71/1 skipped + 111`.
- Knowledge Control Plane 1.2.0a23: **95/95 PASS** in clean process.
- a combined KLC+KCP shell invocation timed out after KLC completed; the partial KCP portion is **not counted**. The separate KCP rerun above is authoritative.
- Core/Runner/KLC/KCP/Runtime/Integration/Reporting semantic runtime code: **unchanged** for this block.

---

# Test Status — AISL multi-file published persistence

Date: 2026-08-16

- real Core `sql-analysis/v1` over `datamart_profile_fl`: **PASS as valid partial observed product**; 306 SQL units, 480 files scanned, 475 statements, 70 lineage gaps.
- real package shape: **19 fact shards / 22 physical members**.
- real AISL publication: **PASS**, revision `rev-3156d56a22184e6a609bc36e`.
- source repository + complete Core producer output deleted after publication: **PASS**.
- exact `sql_statement` read after deletion: **PASS**.
- exact `sql_join_edge` read after deletion: **PASS**.
- semantic guard: Core status remains `partial`, 70 lineage gaps remain explicit; **no status promotion**.
- Knowledge API 0.32.0: **112/112 PASS**, completed groups `37 + 24 + 34 + 17`.
- Prepared Knowledge Runtime 0.1.0.post9: **10/10 PASS**.
- Knowledge Integration 0.1.15: **19/19 PASS**.
- AISL Contract 0.3.0b6: **47/47 PASS**.
- Knowledge Reporting 0.18.1: **100 PASS, 2 SKIPPED**.
- Knowledge Layer Core 0.61.0a32: **252 PASS, 8 SKIPPED**, completed groups `70/7 skipped + 38 + 33/1 skipped + 69 + 42`.
- Knowledge Control Plane 1.2.0a23: **95/95 PASS** in clean environment.
- larger/monolithic suites terminated by the external wrapper are **not counted as PASS**; only fully completed split groups above are authoritative.
- Core/Runner/KLC/KCP semantic runtime code: **unchanged**.

---

# Test Status — AISL Persistence Boundary Pilot

Date: 2026-08-16

- fresh real Runner V1/V2 production: **PASS**; each produced one Core observed product and one KLC derived product.
- real R1 publication: **PASS**, revision `rev-ca39be021ceb0824d1b7fc5f`.
- real R2 copy-on-write publication: **PASS**, revision `rev-a1c957654c74d11dc2e6dcf7`.
- delete source repositories + complete Runner output trees after publication: **PASS**.
- observed exact read after deletion: **PASS** for R1 and R2.
- derived exact read after deletion: **PASS** for R1 and R2.
- old R1 remains queryable after R2 and deletion of both producer environments: **PASS**.
- stale exact dependency COW proposal: **REJECTED as required** (`revision_exact_dependency_unresolved`).
- Knowledge API 0.31.0: **108/108 PASS**, complete groups `33 + 24 + 22 + 29`.
- Prepared Knowledge Runtime 0.1.0.post8: **8/8 PASS**.
- Knowledge Integration 0.1.15: **19/19 PASS**.
- AISL Contract 0.3.0b5: **46/46 PASS** + real multi-owner producer projection **PASS**.
- Knowledge Layer Core 0.61.0a32: **252 PASS, 8 SKIPPED**, complete groups `70+71+111`, skipped `7+1`.
- Knowledge Control Plane 1.2.0a23: **95/95 PASS** in clean environment.
- monolithic KLC run hit external timeout and is **not counted**; completed split runs above are authoritative.

---

# Test Status — AISL published persistence pilot

Date: 2026-08-16

- final real Core→Runner→KLC→AISL R1 publication: **PASS**, revision `rev-7295d3fa8a58c987a6026450`.
- destructive consumer-autonomy acceptance after deleting source + Runner output: observed exact read **PASS**, derived exact read **PASS**, revision read **PASS**.
- final real COW R2 publication: **PASS**, revision `rev-059d40e185d30e1f040b00b8`.
- R2 exact dependency C2→A2: **PASS**; old A1/C1 absent from R2 snapshot.
- post-delete R1 + R2 observed/derived reads: **PASS**.
- strict stale exact-dependency negative contract: **PASS (publication rejected)**.
- Knowledge API 0.31.0: **108/108 PASS**, completed split execution `19 + 26 + 17 + 29 + 17`.
- Prepared Knowledge Runtime 0.1.0.post8: **8/8 PASS**.
- Knowledge Integration 0.1.15: **19/19 PASS**.
- AISL Contract 0.3.0b5: **46/46 PASS**.
- Knowledge Layer Core 0.61.0a32: **252 PASS, 8 SKIPPED**, completed split execution `108 + 33 + 69 + 42`; skips `7 + 1`.
- Knowledge Control Plane 1.2.0a23: **95/95 PASS**.
- monolithic/partial suites terminated by external wrapper are **not counted as PASS**.

---

# Test Status — AISL Reference Data real consumer guidance

Date: 2026-08-16

- authoritative real Reference Data production/publication: **PASS**; job `job-2d8e2dd6fada45668205498e59ac5005`, revision `rev-7e8a9ec88020277028ac41cb`.
- first force-run external wrapper expiry: **NOT COUNTED AS PASS**; official Core artifact had completed and was later reused by content identity.
- frozen semantic cases: **22/22** represented — 7/7 strong, 4/4 borderline, 11/11 controls.
- technical semantic-definition checks: **25/25 PASS**.
- interpretation-policy guards: **25/25 PASS**.
- live `reference-data-guidance/v1`: **PASS**; global discovery **-96.7%**, PRODUCT_PRICE **-88.3%**, operatorId **-96.5%** versus broad reads.
- Knowledge API 0.30.16: **104/104 PASS**, authoritative complete split execution `46 + 17 + 26 + 15`.
- Knowledge Integration 0.1.15: **19/19 PASS**.
- Knowledge Layer Core 0.61.0a32: **252 PASS, 8 SKIPPED**, complete split execution `110 + 142`, skipped `7 + 1`.
- Knowledge Control Plane 1.2.0a23: **95/95 PASS** in clean environment.
- compile/import changed modules: **PASS**.
- semantic guard: `semantic_derivation=none`; own-NSI/global authority remain unassigned by runtime.
- post-change real external-LLM behavioral trace: **NOT RUN / separate optional consumer acceptance**.

---

# Test Status — AISL System Description + Foreign Data Persistence

Date: 2026-08-15

- real fresh System Description KCP → Runner → KLC → Knowledge API publication: **PASS**; job `job-50770118bb894834aacedcdd6da37f9b`, revision `rev-db657fc55d3446f57adbdadd`.
- System Description structural Gold dimensions on current canonical: **PASS**; 3 modules, 59 inbound boundaries, 13 integrations, 34 event boundaries, 127 storage targets, 59 scenarios, 26 explicit gaps, 1038 files / 7 payloads complete.
- live `system-description-guidance/v1`: **PASS**; ~421.5 KB common multi-tool context → 54.8 KB (**-87.0%**).
- KCP post-Runner artifact-scan lifecycle fix: **PASS** on fresh real publication; deep producer payload is no longer recursively inventoried by KCP.
- real FDP official content-addressed reuse → KLC → Knowledge API publication: **PASS**; job `job-97d120611929400bb18898da4da79537`, revision `rev-f165cea38d8b1456ad51c978`.
- current FDP structural acceptance: **781 paths / 969 mechanical cases / 8 confirmed exact same-data cases**.
- representative DEVICE_LINK and MNP/OPERATORID semantic acceptance: **PASS**.
- live `foreign-data-persistence-guidance/v1`: **PASS**; DEVICE_LINK **-94.2%**, OPERATORID **-87.5%**, unfiltered **-98.7%**.
- Knowledge API 0.30.15: **102/102 PASS**, complete split execution `46/46 + 56/56`.
- Knowledge Integration 0.1.14: **18/18 PASS**.
- Knowledge Control Plane 1.2.0a23: **95/95 PASS** in clean environment.
- Knowledge Layer Core 0.61.0a32: **252 PASS, 8 SKIPPED**.
- semantic guards: compact projections perform no new semantic derivation; FDP business/legal classification remains unassigned; missing source-system evidence is not guessed.

The initial FDP force-run was interrupted by the external execution wrapper during KLC materialization and is **not** counted as PASS. The authoritative replay reused the completed official Core artifact by content identity and published successfully.

---

# Test Status — AISL System Interactions real consumer guidance

Date: 2026-08-15

- real KCP → Runner → KLC → Knowledge API publication: **PASS**; `job-7633eb94b1e546f6ae74dd250f80b821`, revision `rev-29fbde443c7bd63854ac8b1e`.
- fresh producer result: **3 interactions / 8 execution contexts / 46 field contracts / 17 diagnostics**.
- Knowledge API 0.30.13: **99/99 PASS**, complete split execution `45/45 + 54/54`.
- Knowledge Integration 0.1.12: **16/16 PASS**.
- Knowledge Layer Core 0.61.0a32: **252 PASS, 8 SKIPPED**.
- Knowledge Control Plane 1.2.0a22: **94/94 PASS** in clean environment.
- live revision-pinned `system-interaction-guidance/v1`: **PASS**.
- real compactness vs exact raw detail: userinfo **-94.6%**, phone flags **-84.2%**, update/create **-95.3%**.
- semantic guard: all matched interactions remain **probable**; `/giveSberProfileId` remains unmatched diagnostic.
- external LLM behavioral trace: **NOT RUN / unresolved external acceptance**, producer rerun not required.

A monolithic API suite timed out late and is not counted as PASS; completed split runs are authoritative. An initial KCP full run inherited real-run environment overrides (92 PASS / 2 env-dependent FAIL); the clean rerun passed 94/94 without KCP code changes.

---

# Test Status — AISL consumer ergonomics read projection

Date: 2026-08-15

- Knowledge Integration 0.1.11: **15/15 PASS**.
- Knowledge API 0.30.12: **96/96 PASS**, complete split execution 60/60 + 36/36.
- final focused API + Integration contract set: **30/30 PASS**.
- OpenAPI export/parity: **PASS**.
- deterministic compactness: exact 3240→2687 bytes (**-17.1%**); polymorphic 3571→2170 bytes (**-39.2%**).
- semantic guards: exact stays confirmed; polymorphic technical confidence stays confirmed while usefulness stays ambiguity; truncation/gaps remain explicit.
- real post-change external-agent trace: **NOT RUN / unresolved acceptance item** because the recovery does not contain a live API catalog or captured trace. This is not a producer gap and does not justify re-analysis of sources.

A monolithic API invocation was previously terminated by wrapper timeout late in the suite and is not counted as PASS; the complete split execution above is authoritative.

---

# Test Status — incremental revision snapshot + multi-case attribute extension

Date: 2026-08-15

- AISL Contract 0.3.0b4: **45/45 PASS**.
- Knowledge API 0.30.11: **94/94 PASS**; pytest terminal log reports `94 passed in 32.06s`. The surrounding container command remained alive after pytest completion, so the wrapper timeout is not counted as a functional failure.
- Knowledge Integration 0.1.10: **15/15 PASS**.
- KLC unchanged; latest completed full result: **252 PASS, 8 SKIPPED**.
- real full base publication: **PASS**.
- real incremental copy-on-write publication: **PASS**.
- composed revision: **8 products / 44 capabilities**.
- `attribute-addition-plan/v1` profile v12: **17 tools / one pinned composed revision PASS**.
- multi-case HTTP relation usefulness: **6/6 representative relationship classes PASS**.
- scalar control `BirthPlace.value`: **PASS**, no false relationship context.
- SQL target/insertion representative probes: **PASS**, resolved/partial propagation and diagnostics preserved.

---

# Test Status — AISL attribute-extension JOIN evidence

Date: 2026-08-15

- targeted KLC + Knowledge Integration: **26 PASS**;
- knowledge-layer-core full with canonical parser deps: **250 PASS, 8 SKIPPED**;
- knowledge-integration full: **15 PASS**;
- affected Knowledge API tests: **7 PASS**;
- compile/import changed packages: **PASS**;
- official real Runner `knowledge_execution_result/v2`: **PASS**, 8 products / 44 capabilities;
- official Knowledge API publication: **PASS**, revision `rev-cfb071123bdb5e8b54eb06a1`;
- consumer-only HTTP attribute-extension read: **PASS**; storage observations, exact-vs-analog relevance and diagnostics visible after publication.

A prior one-test KLC failure occurred only in an incomplete environment without `sqlglot`; the same test failed on untouched baseline. With supplied canonical `sqlglot 30.13.0`, the full KLC suite passed.

---

# Test Status — UCP 91 external blind one-shot runner

Date: 2026-08-15

- `run_blind_once.py` compile: **PASS**;
- endpoint/model missing fail-fast: **PASS**; no run directory created;
- auth metadata secret-hygiene static check: **PASS**;
- full one-shot orchestration against local OpenAI-compatible mock: **PASS**;
- official publication inside one-shot: **PASS**, revision `rev-828b3d5897d6bf2f09d6b0c4`;
- Knowledge API readiness: **PASS**;
- 10 batches / 91 inputs structural coverage: **PASS**;
- pre-Gold freeze: **PASS**, `gold_accessed_by_validator=false`;
- frozen-result ZIP creation: **PASS**;
- Knowledge API cleanup: **PASS**, test port closed;
- mock result quality score: **NOT APPLICABLE** — mock performed no semantic retrieval/reasoning and returned all 91 `unresolved`;
- real independent DeepSeek 91 run: **NOT RUN / unresolved** because external endpoint/model/certificates are not configured in this execution environment.

No framework runtime package code changed, so package full suites were not rerun.

---

# Test Status — UCP 91 external blind stand readiness

Date: 2026-08-15

- current Runner plan over existing typed evidence: **0 Core analyzers / 1 KLC materialization PASS**;
- `knowledge_execution_result/v2`: **completed**;
- official Knowledge API publication: **PASS**;
- second empty-catalog deterministic replay: **same revision id PASS**;
- generated consumer kit: **4 tools / pinned revision PASS**;
- Knowledge API foreground serve smoke: **PASS**;
- pre-Gold freeze validator positive structural smoke: **PASS**;
- duplicate-index negative smoke: **PASS (rejected as expected)**;
- OpenAI-compatible reference runner dry-run: **PASS**;
- reference runner generated binding → live Knowledge API tool call: **PASS**;
- independent external LLM 91 run: **NOT RUN / unresolved** because no independent LLM connector is available in this environment.

No framework package runtime code changed, so package full suites were not rerun.

---

# Test Status — UCP 91 AISL reachability block

Date: 2026-08-15

- prepared Gold-positive fact existence: **29/29 PASS**;
- frozen initial bounded lexical diagnostic: **23/29 exact target fields surfaced in top-5**;
- bounded acceptance follow-up/navigation for remaining targets: **6/6 PASS**;
- representative semantic-guard evidence availability: **5/5 PASS**;
- blind input isolation: **91/91 PASS**;
- post-freeze evaluator synthetic test: **PASS**;
- evaluator compile: **PASS**.

No framework package runtime code changed, so package full suites were not rerun. Previous completed package regression results remain the latest package-code results.

---

# Test Status — current canonical baseline

Date: 2026-08-15

## KCP one-shot lifecycle block

- knowledge-control-plane full suite: **94/94 PASS**.
- focused inherited-pipe lifecycle regression: **PASS**.
- timeout/process-group regression: **PASS**.
- real UCP + TSA + PDM one-shot: **PASS**; persisted job `succeeded`.
- official publication: **PASS**; revision `rev-07ee3380d57d95910de989c9`, 5 KnowledgeProducts, 17 capabilities.
- compile/import and final packaged-manifest verification are release gates documented in the recovery package.

The earlier KCP one-shot lifecycle issue from the previous AISL block is resolved by KCP 1.2.0a22 and is no longer an open acceptance gap.

---

# Test Status — Bulk Repository Processing

Date: 2026-08-14

## PASS

Targeted affected regression: **53/53 PASS**.

Covered:
- KLC materialization contracts/runtime;
- Repository Inventory structural-member present/absent behavior;
- conditional-capability planning semantics;
- generic repository source selection;
- temporary-run ownership/stale cleanup;
- sequential batch checkout lifecycle;
- partial repository failure continuation;
- existing data-model-discovery after shared acquisition refactor;
- Runner CLI commands/version;
- KCP version/bundled runtime catalog consistency.

Compile of changed Python packages: PASS.
Import of KLC `0.61.0a27`, Runner `0.10.24`, KCP `1.2.0a16`: PASS.
Pinned runtime bundle discovery/validation: PASS.

Real Core→KLC two-repository smoke: **2/2 PASS**.
Representative uploaded-application batch acceptance: **2/2 PASS**.

## Full Runner suite

A full Runner suite was attempted as an additional check but did not complete within the 120-second execution limit. The process reached at least 70 passing tests (pytest progress dots) before timeout; no failure output was produced before termination. This run is **NOT claimed as PASS**.

Separately, three stale count assertions in `test_knowledge_planning.py` had already been reproduced on the untouched input canonical before this block (expected 17 catalog products, current baseline contains 18). They are pre-existing baseline drift and were not silently reclassified or changed as part of bulk processing.

Full framework regression: NOT RUN; targeted + representative acceptance used for this bounded block.


## High-level Control Plane CLI addendum (1.2.0a17)

- KCP targeted compatibility/batch tests: 19/19 PASS.
- Runner batch/acquisition/CLI targeted tests: 12/12 PASS.
- one-command CLI routing smoke: PASS.
- real local high-level KCP → Runner → clone → Core → KLC smoke: 2/2 PASS; zero retained checkouts.
- KCP full suite: 109 PASS, 5 pre-existing stale substring-count failures reproduced on untouched canonical.
- live Bitbucket acceptance: NOT RUN here; next step on user's machine.


## AISL coverage semantics / real multi-product validation — 2026-08-15

- knowledge-layer-core full suite: **247 PASS, 8 SKIPPED**.
- aisl-contract: **43/43 PASS**.
- real UCP/PDM Runner production: **PASS**.
- official Knowledge API publication: **PASS**.
- consumer-only universal exact code/PDM reads and Agent SDK binding: **PASS**.
- KCP one-shot lifecycle: **NOT PASS / unresolved operational stall after Runner subprocess completion**.
