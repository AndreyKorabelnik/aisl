# code-analyzer-core 0.40.9

## Iteration 31 — chained invocation receiver lineage

- Preserves the exact value used as the receiver of nested Java method-invocation chains.
- Emits observed `invocation_receiver` edges through chains such as
  `request.getScopes().stream().map(...).collect(...)`.
- Projects JavaBean getter receivers as ordinary source-field occurrences before the
  subsequent stream or helper invocations are processed.
- Enables collection request fields to participate in deterministic downstream
  lineage without matching fields by name or guessing helper return semantics.
- Keeps the transformation steps separate: collection receiver, lambda processing,
  conditional collection mutations, scalar join, builder assignment and boundary
  serialization remain individually evidenced.

No application-, package-, class-, method-, or field-specific rules were added.
