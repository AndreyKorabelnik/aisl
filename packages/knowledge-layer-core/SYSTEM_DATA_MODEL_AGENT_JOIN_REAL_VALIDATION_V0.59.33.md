# Real validation — agent-ready data-model JOIN semantics — KLC 0.59.33

Real inputs:
- UCP logical model;
- UCP TSA/storage implementation;
- `datamart_profile_fl` SQL;
- EPKAP/PDM physical model.

The validation uses the frozen Manual Gold v0.2 as a quality oracle only; no Gold/application-specific rules are present in runtime code.

## C1 — Individual.birthDate -> BirthDate

- cardinality: one
- join method: `equals`
- confidence: confirmed
- SQL status: `direct_candidate_requires_physical_representation_check`

Important: logical equality is kept separate from the observed datamart physical key extraction; KLC does not claim that a direct physical equality predicate is guaranteed.

## C2 — BirthPlace.country -> Country.name

`Individual.birthPlace -> BirthPlace`:
- join method: `equals`
- confidence: confirmed

`BirthPlace.country -> Country`:
- join method: `resolve_reference_value_to_target_key`
- confidence: confirmed
- SQL status: transformation required
- observed source reference includes `"Country_" + birthPlace.getCountry().getCode()`
- observed target key includes `"Country_" + country.getCode()`
- match basis: `exact_structural_expression_signature`
- SQL anchors for BirthPlace and Country are preserved, including Country `name` usage.

This is sufficient for an SQL-generating consumer to construct a justified candidate without KLC itself generating SQL.

## C3 — Individual.emigrations[] -> Emigration

- cardinality: many
- join method: `derive_source_identity_from_target_key`
- confidence: confirmed
- SQL status: transformation required
- observed parent key includes `"Individual_" + individual.getId()`
- observed child key composes parent key with `.emigrations_...`

Direct comparison of `Individual.id` to the complete child key is therefore not asserted.

## C4 — encoded dictionary reference

`Individual.birthCountry -> Country`:
- join method: `resolve_reference_value_to_target_key`
- confidence: confirmed
- exact structural correspondence exists between encoded reference value and Country target key.

## C5 — polymorphic identifications

- cardinality: many
- polymorphic: true
- join method: `resolve_reference_collection`
- relationship confidence: confirmed
- SQL status: `unresolved_requires_subtype_or_representation`
- observed concrete targets are preserved
- diagnostic explicitly states that no single physical JOIN is selected without subtype/representation evidence.

## C6 — Gender relation vs transformation

`Individual.gender -> Gender`:
- join method: `equals`
- confidence: confirmed

The datamart's observed `split(value, ':')[1]` remains an SQL transformation in the target SQL anchor and is not misclassified as relationship semantics.

## Verdict

C1–C6 join-semantic classes required by Manual Gold v0.2 are represented by the current KLC projection with provenance/confidence/gaps and without SQL generation, fuzzy identity matching, or guessed physical mappings.
