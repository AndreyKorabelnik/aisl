# KCP one-shot lifecycle — acceptance

Date: 2026-08-15
Status: ACCEPTED

## Real acceptance input

Formalized sources from the existing real UCP/PDM validation set:

- UCP API repository;
- UCP TSA v4 repository;
- real B2C PDM file;
- scenario `build-effective-data-model-v1`;
- forced rebuild to exercise Core → Runner → KLC rather than cache-only completion.

No synthetic mapping or semantic evidence was added.

## Result

KCP job `job-a81b0391ddc944a08fac298a47781934` reached terminal persisted status `succeeded`.

Observed lifecycle:

`checkout → prepare_inputs → runner_plan → runner_execution → publication → succeeded`

Critical post-Runner transition:

- Runner execution result completed;
- KCP logged `Runner process completed; scanning output artifacts`;
- 47 Runner-output artifacts registered in 0.3 s;
- `runner_execution` succeeded;
- publication completed in 0.3 s;
- total knowledge execution duration 52.7 s.

Published AISL revision:

- system: `aisl-blocka-ucp-pdm`;
- revision: `rev-07ee3380d57d95910de989c9`;
- products: 5;
- capabilities: 17;
- Knowledge API active revision points to this revision.

The semantic product coverage remains equivalent to the prior real acceptance: code-declared partial with explicit gaps, physical parser coverage complete, and logical/physical mapping `no_mapping_evidence`. The lifecycle fix did not manufacture mappings or alter knowledge semantics.

## Acceptance conclusion

**Observed fact:** the previously problematic KCP one-shot lifecycle now completes through official publication on the representative real multi-product run.

**Strongly supported diagnosis:** inherited subprocess output handles were capable of preventing KCP from observing completion under the prior executor contract; the synthetic regression reproduces that failure mechanism and the generic executor fix removes it.

This block does not claim that every possible external process-tree behavior has been proven; remaining failures must continue to surface as diagnostics/timeouts rather than silent success.
