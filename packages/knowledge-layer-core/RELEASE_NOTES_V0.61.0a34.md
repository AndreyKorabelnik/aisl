# Knowledge Layer Core 0.61.0a34

Repository Inventory v3 release.

- adds explicit preflight/post-analysis evaluation phase;
- separates coverage gaps, structural discovery/novelty and concept inference;
- preserves the existing six concept detector semantics;
- publishes first-class repository coverage-gap rows;
- does not promote generic novelty to unclassified concept candidates.

Regression: 252 passed, 8 skipped. Real concept parity: 12/12 exact across gateway + datamart.
