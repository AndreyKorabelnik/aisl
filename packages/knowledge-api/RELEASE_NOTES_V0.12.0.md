# knowledge-api 0.12.0

## SQL Source Inventory v1

- Added `GET /systems/{system_id}/sql/source-inventory` for a complete JSON inventory.
- Added `GET /systems/{system_id}/sql/source-inventory.jsonl` for deterministic NDJSON export.
- Added relation and field evidence totals, per-role counts, bounded samples and truncation flags.
- Added `max_evidence_per_role` to the paginated SQL relations endpoint.
- Updated the required Knowledge Layer Core version to `>=0.52.1,<1.0.0`.
- Regenerated canonical OpenAPI.

The endpoints expose deterministic Knowledge Layer facts only. LLM interpretations remain
outside the canonical inventory response.
