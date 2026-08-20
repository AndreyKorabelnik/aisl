# code-analyzer-core 0.43.14

## Source-proven Java inheritance dispatch for FDP provenance

The interprocedural persistence index now recovers two Java call shapes that the
regular conservative call graph intentionally leaves unresolved:

- a concrete receiver invokes a method declared by its superclass;
- a template method invokes an overridable method implemented by a concrete subclass.

Synthetic edges are emitted only when source declarations prove the exact method
name and arity. They remain provenance candidates and do not create persistence,
storage or business facts by themselves.

This restores the execution bridge used by AT900's DAL template:

`PhoneOperatorHandler.handle(...) → AbstractDalResultHandler.handle(...) → doHandleByDal(...) → PhoneOperatorHandler.handleByDal(...)`.

No AT900-specific class or method names are present in the resolver.
