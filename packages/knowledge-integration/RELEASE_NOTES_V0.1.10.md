# knowledge-integration 0.1.10

Bumps `attribute-addition-plan/v1` to profile version 12.

The consumer now distinguishes relationship/storage confidence from KLC `basis.usefulness` actionability. It explicitly handles collection cardinality and polymorphic ambiguity without silently turning `many` into one-to-one SQL or selecting an arbitrary concrete subtype.
