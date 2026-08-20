# CLI reference — static-analysis-runner 0.10.4

## Canonical product route

```text
knowledge-input-inventory
knowledge-execution-plan
knowledge-execute
```

Users select knowledge and scope. Runner resolves typed Core evidence and KLC materializations from official catalogs. Removed Task/Suite selectors are rejected; no compatibility route exists.

## Independent portfolio discovery

`data-model-discovery` performs a lightweight typed-evidence scan of repository candidates. It preserves partial failures and removes temporary clones.

## Diagnostic commands

- `evidence-execute` — execute one Core evidence request.
- `knowledge-materialize` — execute one KLC materialization plan.
- `execution-result-contract` — read-only execution-result contract composition from official owner catalogs.

## Removed commands

The installed CLI does not expose `repository`, `workspace`, `portfolio-topology`, `physical-model` or `materialize-knowledge-layer`.

## Parked topology

The previous HTTP portfolio topology implementation is under `parked_topology/` and is not installed or imported. Continue it only from the Islands parking specification; do not restore Task/Suite into the main runtime.

### Declarative Knowledge Product Catalog

`static-analysis-runner knowledge-catalog` uses the packaged
`knowledge_product_catalog/v1` by default. To compile the same runtime contracts
with an explicitly supplied product catalog, add:

```text
--knowledge-product-catalog /path/to/knowledge-product-catalog.json
```

The supplied catalog must have a valid canonical fingerprint and pass product ID,
scope and dependency validation. Invalid or missing product catalogs fail explicitly;
there is no legacy Python-policy fallback.
