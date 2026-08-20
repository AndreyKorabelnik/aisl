# code-analyzer-core 0.43.15

## Context-safe template dispatch and transformed-field provenance

The FDP interprocedural resolver now preserves the concrete receiver type while
tracing backward through shared Java template methods. Inherited entry calls from
sibling handlers are rejected, preventing provenance from an unrelated REST or
Kafka boundary from being attached to a persistence write.

The resolver also preserves field identity through explicit Java transformations:

- `Collectors.toMap` value projections;
- `Map.get(...)`;
- DTO setters followed by collection accumulation;
- collection mutation followed by service/DAO calls.

On the full AT900 client-profile repository this restores the canonical path:

`PhoneMNPEvent.phone.operator.operatorId → PHONE.OPERATORID`.

The implementation is source-proven and contains no AT900-specific class, field,
method or table conditions.
