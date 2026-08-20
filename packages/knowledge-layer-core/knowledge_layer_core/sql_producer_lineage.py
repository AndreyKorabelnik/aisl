from __future__ import annotations

from collections import defaultdict
from typing import Any, Callable, Mapping, Sequence


class ObservedMaterializationIndex:
    """Resolve only observed relation producers across workflow dependencies.

    Same-workflow producers are authoritative. Otherwise only producers on the
    nearest observed upstream workflow dependency frontier are returned. The
    index never guesses from relation names, semantic roles, or staging naming.
    """

    def __init__(
        self,
        *,
        materializations: Sequence[Mapping[str, Any]],
        workflow_dependencies: Sequence[tuple[str, str, str]],
        root_scopes_by_query: Mapping[str, Sequence[str]],
        scope_output_contracts: Mapping[str, Mapping[str, Any]],
    ) -> None:
        self._by_context_table: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
        self._by_table: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for raw in materializations:
            producer = dict(raw)
            workflow = str(producer.get("workflow") or "")
            table = str(producer.get("table") or "").strip().lower()
            if workflow and table:
                self._by_context_table[(workflow, table)].append(producer)
                self._by_table[table].append(producer)
        for values in self._by_context_table.values():
            values.sort(key=lambda item: str(item.get("id") or ""))
        for values in self._by_table.values():
            values.sort(key=lambda item: (str(item.get("workflow") or ""), str(item.get("id") or "")))

        self._upstream_edges: dict[str, list[tuple[str, str]]] = defaultdict(list)
        for producer_workflow, consumer_workflow, dependency_id in workflow_dependencies:
            self._upstream_edges[str(consumer_workflow)].append((str(producer_workflow), str(dependency_id)))
        for values in self._upstream_edges.values():
            values.sort()

        self._root_scopes_by_query = {
            str(query_id): tuple(str(scope_id) for scope_id in scope_ids)
            for query_id, scope_ids in root_scopes_by_query.items()
        }
        self._scope_output_contracts = scope_output_contracts
        self._upstream_paths_cache: dict[str, dict[str, tuple[str, ...]]] = {}
        self._producer_cache: dict[tuple[str, str], list[tuple[dict[str, Any], tuple[str, ...]]]] = {}
        # Diagnostics are attached to the producer whose usable output contract
        # was derived.  This keeps partial branch evidence visible without
        # changing the long-standing output_contract return contract.
        self._output_contract_diagnostics: dict[str, tuple[dict[str, Any], ...]] = {}
        # Output contracts are deterministic for one pinned observed materialization
        # graph. Cache only top-level resolutions (seen == ()) so recursive cycle
        # detection remains path-sensitive while repeated callers reuse the same
        # already-derived contract and diagnostics.
        self._top_level_output_contract_cache: dict[str, tuple[set[str] | None, str]] = {}

    def upstream_workflow_paths(self, consumer_workflow: str) -> dict[str, tuple[str, ...]]:
        cached = self._upstream_paths_cache.get(consumer_workflow)
        if cached is not None:
            return cached
        paths: dict[str, tuple[str, ...]] = {consumer_workflow: tuple()}
        queue: list[str] = [consumer_workflow]
        while queue:
            current = queue.pop(0)
            current_path = paths[current]
            if len(current_path) >= 16:
                continue
            for producer, dependency_id in self._upstream_edges.get(current, ()):
                candidate = (*current_path, dependency_id)
                existing = paths.get(producer)
                if existing is None or len(candidate) < len(existing):
                    paths[producer] = candidate
                    queue.append(producer)
        self._upstream_paths_cache[consumer_workflow] = paths
        return paths

    def producers(self, workflow_context: str, logical_name: str) -> list[tuple[dict[str, Any], tuple[str, ...]]]:
        cache_key = (workflow_context, logical_name.strip().lower())
        cached = self._producer_cache.get(cache_key)
        if cached is not None:
            return cached
        direct = self._by_context_table.get(cache_key, ())
        if direct:
            result = [(producer, tuple()) for producer in direct]
            self._producer_cache[cache_key] = result
            return result

        candidates: list[tuple[dict[str, Any], tuple[str, ...]]] = []
        for producer_workflow, dependency_path in self.upstream_workflow_paths(workflow_context).items():
            if producer_workflow == workflow_context:
                continue
            for producer in self._by_context_table.get((producer_workflow, cache_key[1]), ()):
                candidates.append((producer, dependency_path))
        if candidates:
            min_hops = min(len(path) for _producer, path in candidates)
            result = [(producer, path) for producer, path in candidates if len(path) == min_hops]
            result.sort(key=lambda item: (len(item[1]), str(item[0].get("id") or "")))
            self._producer_cache[cache_key] = result
            return result

        # Useful partial fallback: an exact logical table identity can safely cross a
        # workflow boundary when the pinned repository contains exactly one observed
        # producer for that identity. This is not a guessed workflow dependency; the
        # producer is marked explicitly so downstream mappings remain derived/partial
        # and retain the resolution basis in provenance. Multiple exact producers stay
        # ambiguous and are never selected here.
        global_exact = list(self._by_table.get(cache_key[1], ()))
        if len(global_exact) == 1:
            producer = dict(global_exact[0])
            producer["_producer_resolution_status"] = "strongly_supported"
            producer["_producer_resolution_basis"] = "repository_unique_exact_table_producer"
            producer["_producer_resolution_consumer_workflow"] = workflow_context
            producer["_producer_resolution_producer_workflow"] = str(producer.get("workflow") or "")
            result = [(producer, tuple())]
            self._producer_cache[cache_key] = result
            return result

        self._producer_cache[cache_key] = []
        return []

    def exact_table_candidates(self, logical_name: str) -> list[dict[str, Any]]:
        """Return all exact observed producers for one logical table identity.

        This is diagnostic-only for ambiguous/unresolved frontiers. It never ranks or
        selects among multiple producers.
        """
        return [dict(item) for item in self._by_table.get(logical_name.strip().lower(), ())]

    def output_contract(self, producer: Mapping[str, Any], seen: tuple[str, ...] = ()) -> tuple[set[str] | None, str]:
        producer_id = str(producer.get("id") or "")
        if not producer_id or producer_id in seen:
            return None, "materialization_cycle_or_missing_id"
        cacheable = not seen
        if cacheable:
            cached = self._top_level_output_contract_cache.get(producer_id)
            if cached is not None:
                contract, basis = cached
                return (set(contract) if contract is not None else None), basis

        def finish(contract: set[str] | None, basis: str) -> tuple[set[str] | None, str]:
            if cacheable:
                stored = set(contract) if contract is not None else None
                self._top_level_output_contract_cache[producer_id] = (stored, basis)
            return contract, basis

        kind = str(producer.get("kind") or "script_call")
        next_seen = (*seen, producer_id)
        if kind == "script_call":
            query_id = str(producer.get("query_id") or "")
            roots = self._root_scopes_by_query.get(query_id, ())
            if not roots:
                return finish(None, "materialization_root_scope_missing")
            contracts: list[set[str]] = []
            for scope_id in roots:
                contract = self._scope_output_contracts.get(scope_id) or {}
                if contract.get("output_contract_status") != "complete":
                    return finish(None, "materialization_output_contract_incomplete")
                contracts.append({str(x).strip().lower() for x in contract.get("output_columns") or ()})
            first = contracts[0]
            if any(contract != first for contract in contracts[1:]):
                return finish(None, "materialization_root_scope_output_contract_mismatch")
            basis = (
                "script_materialization_root_output_contract"
                if len(roots) == 1
                else "script_materialization_set_branch_output_contract"
            )
            return finish(first, basis)
        if kind == "sql_write":
            provenance = producer.get("provenance") or {}
            materialized_status = str(provenance.get("materialized_output_contract_status") or "")
            materialized_columns = {
                str(x).strip().lower()
                for x in provenance.get("materialized_output_columns") or ()
                if str(x).strip()
            }
            if materialized_status == "complete" and materialized_columns:
                basis = str(provenance.get("materialized_output_contract_basis") or "repository_materialized_relation_contract")
                return finish(materialized_columns, f"sql_write_materialized_target_contract:{basis}")
            scopes = tuple(str(x) for x in producer.get("source_scopes") or () if x)
            if not scopes:
                return finish(None, "sql_write_source_scope_missing")
            contracts: list[set[str]] = []
            for scope_id in scopes:
                contract = self._scope_output_contracts.get(scope_id) or {}
                if contract.get("output_contract_status") != "complete":
                    return finish(None, "sql_write_source_contract_incomplete")
                contracts.append({str(x).strip().lower() for x in contract.get("output_columns") or ()})
            return finish(set().union(*contracts), "sql_write_source_scope_output_contract")
        if kind == "workflow_copy":
            source_table = str(producer.get("source_table") or "").strip().lower()
            if not source_table:
                return finish(None, "workflow_copy_source_table_missing")
            source_producers = self.producers(str(producer.get("workflow") or ""), source_table)
            if not source_producers:
                return finish(None, "workflow_copy_source_producer_missing")
            complete: list[set[str]] = []
            incomplete: list[dict[str, Any]] = []
            for source_producer, dependency_path in source_producers:
                contract, source_basis = self.output_contract(source_producer, next_seen)
                if contract is None:
                    incomplete.append({
                        "gap_kind": "workflow_copy_source_branch_incomplete",
                        "source_producer_id": str(source_producer.get("id") or ""),
                        "source_producer_kind": str(source_producer.get("kind") or ""),
                        "source_producer_workflow": str(source_producer.get("workflow") or ""),
                        "source_table": source_table,
                        "dependency_path": list(dependency_path),
                        "resolution_basis": source_basis,
                    })
                    continue
                complete.append(set(contract))
            if not complete:
                if producer_id:
                    self._output_contract_diagnostics[producer_id] = tuple(incomplete)
                return finish(None, "workflow_copy_source_contract_incomplete")
            first = complete[0]
            if any(contract != first for contract in complete[1:]):
                if producer_id:
                    self._output_contract_diagnostics[producer_id] = tuple(incomplete)
                return finish(None, "workflow_copy_source_contract_ambiguous")
            if producer_id:
                self._output_contract_diagnostics[producer_id] = tuple(incomplete)
            basis = (
                "workflow_copy_partial_consistent_source_materialization_contract"
                if incomplete
                else "workflow_copy_source_materialization_contract"
            )
            return finish(set(first), basis)
        if kind == "config_transform":
            source_table = str(producer.get("source_table") or "").strip().lower()
            if not source_table:
                return finish(None, "config_transform_source_table_missing")
            source_producers = self.producers(str(producer.get("workflow") or ""), source_table)
            if not source_producers:
                return finish(None, "config_transform_source_producer_missing")
            contracts: list[set[str]] = []
            for source_producer, _dependency_path in source_producers:
                contract, _basis = self.output_contract(source_producer, next_seen)
                if contract is None:
                    return finish(None, "config_transform_source_contract_incomplete")
                contracts.append(contract)
            if contracts:
                base = set().union(*contracts)
                mappings = (producer.get("provenance") or {}).get("column_mappings") or {}
                base.update(str(key).strip().lower() for key in mappings if key)
                return finish(base, "config_transform_source_materialization_contract")
            return finish(None, "config_transform_source_contract_missing")
        return finish(None, "unsupported_materialization_kind")

    def output_contract_diagnostics(self, producer: Mapping[str, Any]) -> tuple[dict[str, Any], ...]:
        """Return localized diagnostics produced while resolving one output contract.

        Calling this method never invents a contract.  If the contract has not yet
        been evaluated, it is evaluated once so callers can publish branch-local
        gaps alongside a useful partial contract.
        """
        producer_id = str(producer.get("id") or "")
        if producer_id and producer_id not in self._output_contract_diagnostics:
            self.output_contract(producer)
        return self._output_contract_diagnostics.get(producer_id, tuple())


class SqlProducerColumnTraversal:
    """Compose SQL column origins through observed physical relation producers.

    This is deliberately data-driven: physical relations are traversed only when
    the supplied materialization index has observed producers for their logical
    identity. A physical relation without such a producer is a terminal origin.
    """

    def __init__(
        self,
        *,
        usages: Mapping[str, Mapping[str, Any]],
        relations: Mapping[str, Mapping[str, Any]],
        relations_by_scope: Mapping[str, Sequence[str]],
        projections: Mapping[str, Mapping[str, Any]],
        projections_by_scope: Mapping[str, Sequence[str]],
        root_scopes_by_query: Mapping[str, Sequence[str]],
        materializations: ObservedMaterializationIndex,
    ) -> None:
        self.usages = usages
        self.relations = relations
        self.relations_by_scope = relations_by_scope
        self.projections = projections
        self.projections_by_scope = projections_by_scope
        self.root_scopes_by_query = root_scopes_by_query
        self.materializations = materializations
        # Top-level target lineage repeatedly asks for the same terminal usage.
        # The traversal is deterministic for one pinned SQL artifact and observed
        # materialization graph, so cache only calls that start with empty path
        # state. Recursive/path-sensitive calls remain uncached so provenance
        # paths are never conflated.
        self._top_level_usage_origin_cache: dict[tuple[str, str], list[dict[str, Any]]] = {}

    @staticmethod
    def _relation_path_step(relation: Mapping[str, Any]) -> dict[str, Any]:
        return {
            "relation_id": str(relation.get("id") or ""),
            "relation_name": str(relation.get("name") or ""),
            "relation_kind": str(relation.get("kind") or ""),
            "usage_role": str(relation.get("usage_role") or ""),
            "query_id": str(relation.get("query_id") or ""),
            "scope_id": str(relation.get("scope_id") or ""),
            "scope_ordinal": int(relation.get("scope_ordinal") or 0),
            "file": str(relation.get("file") or ""),
        }

    @classmethod
    def _prepend_relation_path(cls, origins: Sequence[Mapping[str, Any]], relation: Mapping[str, Any]) -> list[dict[str, Any]]:
        step=cls._relation_path_step(relation)
        result=[]
        for origin in origins:
            copied=dict(origin)
            copied["relation_path"]=[step, *(list(origin.get("relation_path") or []))]
            result.append(copied)
        return result

    def scope_column_origins(
        self,
        workflow_context: str,
        scope_id: str,
        column_name: str,
        trail: tuple[str, ...] = (),
        materialization_path: tuple[str, ...] = (),
        workflow_dependency_path: tuple[str, ...] = (),
    ) -> list[dict[str, Any]]:
        marker = "scope:" + scope_id + ":" + column_name.lower()
        if len(trail) > 80 or marker in trail:
            return []
        next_trail = (*trail, marker)
        explicit = [
            self.projections[pid]
            for pid in self.projections_by_scope.get(scope_id, ())
            if not self.projections[pid].get("wildcard")
            and str(self.projections[pid].get("output") or "").strip().lower() == column_name.strip().lower()
        ]
        if explicit:
            out: list[dict[str, Any]] = []
            for projection in explicit:
                out.extend(self.projection_origins(workflow_context, projection, next_trail, materialization_path, workflow_dependency_path))
            return out

        wildcards = [
            self.projections[pid]
            for pid in self.projections_by_scope.get(scope_id, ())
            if self.projections[pid].get("wildcard")
        ]
        out: list[dict[str, Any]] = []
        for wildcard in wildcards:
            if wildcard.get("source_usages"):
                for usage_id in wildcard.get("source_usages") or ():
                    usage = self.usages.get(str(usage_id))
                    if (
                        usage
                        and usage.get("relation_id")
                        and str(usage.get("usage_role") or "").strip().lower() == "projection"
                    ):
                        out.extend(self.relation_column_origins(
                            workflow_context,
                            str(usage["relation_id"]),
                            column_name,
                            (*next_trail, "projection:" + str(wildcard["id"])),
                            materialization_path,
                            workflow_dependency_path,
                        ))
            else:
                relation_ids = self.relations_by_scope.get(scope_id, ())
                if len(relation_ids) == 1:
                    out.extend(self.relation_column_origins(
                        workflow_context,
                        str(relation_ids[0]),
                        column_name,
                        (*next_trail, "projection:" + str(wildcard["id"])),
                        materialization_path,
                        workflow_dependency_path,
                    ))
        return out

    def materialized_table_column_origins(
        self,
        workflow_context: str,
        logical_name: str,
        column_name: str,
        trail: tuple[str, ...] = (),
        materialization_path: tuple[str, ...] = (),
        workflow_dependency_path: tuple[str, ...] = (),
    ) -> list[dict[str, Any]]:
        out: list[dict[str, Any]] = []
        for producer, dependency_path in self.materializations.producers(workflow_context, logical_name):
            producer_id = str(producer.get("id") or "")
            if not producer_id or producer_id in materialization_path:
                continue
            next_materialization_path = (*materialization_path, producer_id)
            next_dependency_path = (*workflow_dependency_path, *dependency_path)
            kind = str(producer.get("kind") or "script_call")
            producer_origins: list[dict[str, Any]] = []
            if kind == "sql_write":
                for source_scope in producer.get("source_scopes") or ():
                    producer_origins.extend(self.scope_column_origins(
                        str(producer.get("workflow") or workflow_context),
                        str(source_scope),
                        column_name,
                        trail,
                        next_materialization_path,
                        next_dependency_path,
                    ))
            elif kind in {"workflow_copy", "config_transform"}:
                source_table = str(producer.get("source_table") or "").strip().lower()
                source_column = column_name
                if kind == "config_transform":
                    mappings = (producer.get("provenance") or {}).get("column_mappings") or {}
                    source_column = str(mappings.get(column_name.strip().lower()) or column_name)
                if source_table:
                    producer_origins.extend(self.materialized_table_column_origins(
                        str(producer.get("workflow") or workflow_context),
                        source_table,
                        source_column,
                        trail,
                        next_materialization_path,
                        next_dependency_path,
                    ))
            elif kind == "script_call":
                roots = self.root_scopes_by_query.get(str(producer.get("query_id") or ""), ())
                if roots:
                    if len(roots) > 1:
                        contract, _basis = self.materializations.output_contract(producer)
                        if contract is None or column_name.strip().lower() not in contract:
                            roots = ()
                    for root_scope in roots:
                        producer_origins.extend(self.scope_column_origins(
                            str(producer.get("workflow") or workflow_context),
                            str(root_scope),
                            column_name,
                            trail,
                            next_materialization_path,
                            next_dependency_path,
                        ))

            resolution_basis = str(producer.get("_producer_resolution_basis") or "")
            if resolution_basis:
                resolution = {
                    "status": str(producer.get("_producer_resolution_status") or "strongly_supported"),
                    "basis": resolution_basis,
                    "logical_table": logical_name.strip().lower(),
                    "consumer_workflow": str(producer.get("_producer_resolution_consumer_workflow") or workflow_context),
                    "producer_workflow": str(producer.get("_producer_resolution_producer_workflow") or producer.get("workflow") or ""),
                    "producer_id": producer_id,
                }
                annotated: list[dict[str, Any]] = []
                for origin in producer_origins:
                    copied = dict(origin)
                    copied["producer_resolution_path"] = [
                        resolution,
                        *(list(origin.get("producer_resolution_path") or [])),
                    ]
                    annotated.append(copied)
                producer_origins = annotated
            out.extend(producer_origins)
        return out

    def relation_column_origins(
        self,
        workflow_context: str,
        relation_id: str,
        column_name: str,
        trail: tuple[str, ...] = (),
        materialization_path: tuple[str, ...] = (),
        workflow_dependency_path: tuple[str, ...] = (),
    ) -> list[dict[str, Any]]:
        relation = self.relations.get(relation_id)
        if not relation:
            return []
        marker = "relation:" + relation_id + ":" + column_name.lower()
        if marker in trail or len(trail) > 80:
            return []
        next_trail = (*trail, marker)
        if relation.get("kind") in {"cte", "derived"}:
            out: list[dict[str, Any]] = []
            for source_scope in relation.get("source_scopes") or ():
                out.extend(self.scope_column_origins(
                    workflow_context,
                    str(source_scope),
                    column_name,
                    next_trail,
                    materialization_path,
                    workflow_dependency_path,
                ))
            return self._prepend_relation_path(out, relation)
        if relation.get("kind") in {"physical", "physical_template"}:
            logical_name = (
                str(relation.get("logical") or "")
                or str(relation.get("name") or "").split(".")[-1]
            ).strip().lower()
            selected_producers = self.materializations.producers(workflow_context, logical_name)
            out = self.materialized_table_column_origins(
                workflow_context,
                logical_name,
                column_name,
                next_trail,
                materialization_path,
                workflow_dependency_path,
            )
            if out:
                return self._prepend_relation_path(out, relation)
            exact_candidates = self.materializations.exact_table_candidates(logical_name)
            if selected_producers:
                producer_resolution_status = "unresolved"
                producer_resolution_basis = "observed_exact_table_producer_column_lineage_unresolved"
            elif len(exact_candidates) > 1:
                producer_resolution_status = "ambiguous"
                producer_resolution_basis = "multiple_repository_exact_table_producers_without_observed_workflow_path"
            elif len(exact_candidates) == 1:
                producer_resolution_status = "unresolved"
                producer_resolution_basis = "repository_unique_exact_table_producer_unusable_or_cycle"
            else:
                producer_resolution_status = "unresolved"
                producer_resolution_basis = "no_observed_exact_table_producer"
            return [{
                "usage_id": None,
                "relation_id": relation_id,
                "column": column_name,
                "source_file": relation.get("file") or "",
                "projection_path": [item for item in next_trail if item.startswith("projection:")],
                "materialization_path": list(materialization_path),
                "workflow_dependency_path": list(workflow_dependency_path),
                "terminal_workflow_context": workflow_context,
                "terminal_semantic_role": relation.get("semantic_role"),
                "terminal_classification_status": relation.get("semantic_classification_status"),
                "terminal_classification_basis": relation.get("semantic_classification_basis"),
                "producer_resolution_status": producer_resolution_status,
                "producer_resolution_basis": producer_resolution_basis,
                "producer_resolution_candidates": [
                    {"producer_id": str(item.get("id") or ""), "workflow": str(item.get("workflow") or ""), "kind": str(item.get("kind") or ""), "table": str(item.get("table") or "")}
                    for item in exact_candidates
                ],
                "relation_path": [self._relation_path_step(relation)],
            }]
        return []

    def usage_origins(
        self,
        workflow_context: str,
        usage_id: str,
        trail: tuple[str, ...] = (),
        materialization_path: tuple[str, ...] = (),
        workflow_dependency_path: tuple[str, ...] = (),
    ) -> list[dict[str, Any]]:
        cache_key: tuple[str, str] | None = None
        if not trail and not materialization_path and not workflow_dependency_path:
            cache_key = (workflow_context, usage_id)
            cached = self._top_level_usage_origin_cache.get(cache_key)
            if cached is not None:
                return cached

        def finish(result: list[dict[str, Any]]) -> list[dict[str, Any]]:
            if cache_key is not None:
                self._top_level_usage_origin_cache[cache_key] = result
            return result

        usage = self.usages.get(usage_id)
        if not usage:
            return finish([])
        relation_id = usage.get("relation_id")
        if not relation_id:
            return finish([{
                "frontier_usage_id": usage_id,
                "frontier_workflow_context": workflow_context,
                "frontier_column": str(usage.get("column") or ""),
                "frontier_trail": list(trail),
                "projection_path": [item for item in trail if item.startswith("projection:")],
                "materialization_path": list(materialization_path),
                "workflow_dependency_path": list(workflow_dependency_path),
            }])
        relation = self.relations.get(str(relation_id))
        if not relation:
            return finish([])
        if relation.get("kind") in {"physical", "physical_template"}:
            logical_name = (
                str(relation.get("logical") or "")
                or str(relation.get("name") or "").split(".")[-1]
            ).strip().lower()
            producers = self.materializations.producers(workflow_context, logical_name)
            if not producers:
                exact_candidates = self.materializations.exact_table_candidates(logical_name)
                terminal = {
                    "usage_id": usage_id,
                    "relation_id": relation.get("id"),
                    "column": usage.get("column"),
                    "source_file": usage.get("file") or relation.get("file") or "",
                    "projection_path": [item for item in trail if item.startswith("projection:")],
                    "materialization_path": list(materialization_path),
                    "workflow_dependency_path": list(workflow_dependency_path),
                    "terminal_workflow_context": workflow_context,
                    "terminal_semantic_role": relation.get("semantic_role"),
                    "terminal_classification_status": relation.get("semantic_classification_status"),
                    "terminal_classification_basis": relation.get("semantic_classification_basis"),
                    "relation_path": [self._relation_path_step(relation)],
                }
                if len(exact_candidates) > 1:
                    terminal["producer_resolution_status"] = "ambiguous"
                    terminal["producer_resolution_basis"] = "multiple_repository_exact_table_producers_without_observed_workflow_path"
                    terminal["producer_resolution_candidates"] = [
                        {"producer_id": str(item.get("id") or ""), "workflow": str(item.get("workflow") or ""), "kind": str(item.get("kind") or ""), "table": str(item.get("table") or "")}
                        for item in exact_candidates
                    ]
                return finish([terminal])
        return finish(self.relation_column_origins(
            workflow_context,
            str(relation_id),
            str(usage.get("column") or ""),
            trail,
            materialization_path,
            workflow_dependency_path,
        ))

    def projection_origins(
        self,
        workflow_context: str,
        projection: Mapping[str, Any],
        trail: tuple[str, ...] = (),
        materialization_path: tuple[str, ...] = (),
        workflow_dependency_path: tuple[str, ...] = (),
    ) -> list[dict[str, Any]]:
        marker = "projection:" + str(projection.get("id") or "")
        if marker in trail or len(trail) > 80:
            return []
        next_trail = (*trail, marker)
        out: list[dict[str, Any]] = []
        for usage_id in projection.get("source_usages") or ():
            usage = self.usages.get(str(usage_id))
            # Column-origin traversal is a value-flow surface. Window partition/order
            # and other control usages remain available in typed SQL knowledge, but
            # they must not be promoted to value origins of the projected column.
            if not usage or str(usage.get("usage_role") or "").strip().lower() != "projection":
                continue
            out.extend(self.usage_origins(
                workflow_context,
                str(usage_id),
                next_trail,
                materialization_path,
                workflow_dependency_path,
            ))
        return out
