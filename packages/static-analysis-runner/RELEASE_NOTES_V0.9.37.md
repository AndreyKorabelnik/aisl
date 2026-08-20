# static-analysis-runner 0.9.37

## Read-only analysis mechanism catalog

Added `static-analysis-runner mechanism-catalog`.

The command resolves and exports the current relationship between Analysis UI pipeline profiles, Runner suites/tasks, Core profiles and inherited stages, the shared foundation, Core output declarations, and Knowledge Layer task-based import/capability routing.

The catalog also detects identical non-foundation stage invocations repeated by multiple task processes in the same suite. These are explicitly reported as review candidates, not automatically cacheable stages.

No execution, suite, task, Core profile or Knowledge Layer contract was changed.
