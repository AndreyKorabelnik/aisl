# Analysis UI 2.0.0a34

Iteration 110 completes the real prepared-context chat regression across three pinned Knowledge API revisions: UCP source model, SQL datamart and optional PDM.

The standard chat instructions now require deterministic hand-off of `recommended_target_relation` to the insertion-context tool. The minimum Knowledge Assistant dependency is 0.14.1. No separate chat UI or repository mutation workflow is introduced.
