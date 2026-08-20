# Portfolio Inventory Block D acceptance

Status: COMPLETE (targeted validation only).

Observed/implemented:

- Portfolio Inventory is a Knowledge API consumer over published `repository-inventory` artifacts; no source analysis is invoked.
- System aggregation selects the latest published Repository Inventory revision per `repo_id` and preserves repository/revision provenance.
- Filters: search, concept + comma-separated statuses, technology, protocol, SQL presence, unresolved peers, source kind.
- Facets are system-count facets, not interface-count facets.
- Interaction graph is an observation graph only. Unresolved peers remain unresolved; exact `system_id` membership is reported without alias guessing or clustering.
- Process-local snapshot cache is keyed by immutable database SHA plus file signature; no persistent portfolio dual-write index exists.
- Multi-repository/multi-system synthetic HTTP acceptance and existing Repository Inventory contract checks passed.

Known limitation:

- Repository membership basis is `latest_published_repository_inventory_per_repo_id`. Historical repo removal/decommissioning cannot be inferred. A future authoritative system/repository membership contract should replace this basis if needed; Portfolio Inventory must not guess removal.
