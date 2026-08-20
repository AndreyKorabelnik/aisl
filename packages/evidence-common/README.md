# evidence-common v0.23.2

Shared helpers for evidence-driven code analysis packages.

## v0.23.2 changes

- Added grouped prompt pack profile discovery.
- Runnable profiles are discovered recursively by `**/profile.yaml`.
- `shared/` is excluded from runnable profile discovery.
- `profile_id` remains the canonical identity; physical groups such as `code/`, `sdd/`, and `support/` are layout-only.
- Duplicate `profile_id` values are a hard error.
- Prompt fragments continue to resolve relative to the concrete `profile.yaml` directory, supporting paths such as `../../shared/<fragment>.md`.
- No legacy flat-layout fallback is implemented.

## Generated profile schema contracts

The generated `@generated/profile_schema_contract` fragment now resolves local `$ref` definitions used by `finding.attributes`, lists conditional required attribute fields by `finding_type`, and renders nested object contracts referenced from attributes. This keeps the prompt contract aligned with strict profile JSON Schemas without duplicating business rules in prompt text.
