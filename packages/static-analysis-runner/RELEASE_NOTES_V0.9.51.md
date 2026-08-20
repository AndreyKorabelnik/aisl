# static-analysis-runner 0.9.51 — generic execution phase ordering

The second evidence-family proof exposed a generic topological-order defect: an independent KLC materialization could become ready before all Core evidence analyzers had run.

Runner now deterministically orders all ready Core analyzer nodes before KLC materialization nodes while preserving every declared dependency edge. The rule uses generic node kinds only. No knowledge-specific or evidence-specific dispatch was added.
