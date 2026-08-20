# aisl-reporting 0.9.2

## Business-first system description opening

- Added a mandatory `# О системе` opening for `system-description/v1` when `audience=business`.
- The opening is 4–6 connected plain-language paragraphs focused on role, business value, capabilities, data and interaction model.
- Evidence IDs, source locations, implementation identifiers, endpoint/topic catalogs and detailed gap counts are prohibited in the opening.
- Detailed evidence and limitations remain in the numbered analytical sections and technical appendix.
- Added audience-specific required-heading validation so other audiences are not forced to use the business opening.
- Added regression tests for the opening contract and validation behavior.

No deterministic dataset query or selection logic was changed.
