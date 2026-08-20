# code-analyzer-core 0.43.16

## Physical owner-aware JOOQ reads and builder-to-response lineage

Multi-table JOOQ projections are now split by the source-declared owner of every
selected field. A field such as `PHONE.OPERATORID` is no longer attributed to the
first table in the `FROM` clause.

Confirmed storage-to-access lineage now supports fluent DTO builder projections:

`r.getValue(TABLE.FIELD) → Dto.builder().field(...)`.

Return propagation also treats `this.method(...)` and `super.method(...)` as the
same source call when the returned expression omits the explicit receiver. This
covers template wrappers and executor/future wrappers without interpreting
arbitrary asynchronous execution.

On the full AT900 repository the resulting confirmed path is:

`PHONE.OPERATORID → MbClientProfileExtendedResponse.profiles.operatorId → POST /mbClientProfileExtended`.

Together with 0.43.15 this completes the Core-level MNP path from Kafka input to
physical storage and from physical storage to one concrete external REST response.
