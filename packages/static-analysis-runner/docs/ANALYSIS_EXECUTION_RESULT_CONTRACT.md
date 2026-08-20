# Analysis execution result contract

`execution-result-contract` publishes the Runner-owned boundary between typed Core evidence and KLC materialization.

The installed runtime records immutable source snapshots, analyzer attempts, typed artifact registrations, materialization executions, diagnostics and fingerprints. Evidence meaning is owned by Core; knowledge composition is owned by KLC.

Task/Suite orchestration has been removed. Its identifiers are forbidden semantic selectors and are not emitted as current runtime routing. Portfolio topology is parked outside the installed package.

The next release step is downstream consumer validation against the consolidated typed runtime.
