# Acceptance — relation usefulness calibration

Status: PASS

## Semantic calibration

Representative real cases cover:

- exact observed JOIN -> confirmed actionability;
- storage/key encoding plus analog SQL -> strongly supported proposed JOIN;
- collection storage -> strongly supported collection navigation with `many` multiplicity;
- polymorphic relation -> ambiguity with concrete targets;
- weaker direct-reference representation -> probable candidate.

## Product identity

Repeated real minimal Runner executions over the same prior-revision dependencies produce identical derived KnowledgeProduct identity.

## Regression

- KLC: 252 passed, 8 skipped.
- Knowledge Integration: 15 passed.
- critical identity subset: 12 passed.

No failing functional tests remain when canonical dependencies are present.
