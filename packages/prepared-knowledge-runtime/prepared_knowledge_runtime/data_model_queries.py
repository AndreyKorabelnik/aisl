from __future__ import annotations

from collections import Counter
import re
from pathlib import Path
from typing import Any, Iterable, Mapping

from .consumer_contracts import EvidenceRef, Page, QueryRequest, QueryResult, ScopeRef
from .normalization import stable_id
from .query import KnowledgeLayerQuery
from .workspace_query import WorkspaceKnowledgeQuery


def _source_path(value: Any) -> str:
    raw = str(value or "").replace("\\", "/")
    if "/selected/" in raw:
        suffix = raw.split("/selected/", 1)[1]
        parts = suffix.split("/", 1)
        return parts[1] if len(parts) == 2 else parts[0]
    if "/src/" in raw:
        prefix, suffix = raw.split("/src/", 1)
        component = prefix.rstrip("/").split("/")[-1]
        return f"{component}/src/{suffix}" if component else f"src/{suffix}"
    return raw


def _annotation_tokens(annotation: str) -> set[str]:
    separated = re.sub(r"(?<=[a-z0-9])(?=[A-Z])", " ", str(annotation or ""))
    return {token for token in re.split(r"[^a-zA-Z0-9]+", separated.casefold()) if token}


def _classification(annotations: Iterable[str]) -> str:
    """Normalize annotation-name semantics without project-specific annotation constants.

    The original annotation names remain the source facts. The returned role is a
    transparent naming-convention projection and is never a business classification.
    """
    token_sets = [_annotation_tokens(annotation) for annotation in annotations]
    if any({"root", "entity"}.issubset(tokens) for tokens in token_sets):
        return "root_entity"
    if any("dictionary" in tokens for tokens in token_sets):
        return "dictionary"
    if any("entity" in tokens for tokens in token_sets):
        return "entity"
    return "annotated_type" if token_sets else "unclassified"


class DataModelQueryService:
    """Stable data-model facade for report builders and assistant tools.

    It wraps the canonical KLC query surface; consumers never issue arbitrary SQL or
    depend on DuckDB relation layouts.
    """

    def __init__(self, artifact: str | Path, *, manifest: str | Path | Mapping[str, Any] | None = None) -> None:
        base = (
            KnowledgeLayerQuery.from_database(artifact, manifest=manifest)
            if manifest is not None
            else KnowledgeLayerQuery(artifact)
        )
        manifest_payload = base.manifest()
        capabilities = tuple(base.capabilities())
        repo_ids = tuple(str(v) for v in (manifest_payload.get("repository_ids") or ()))
        kind = str(manifest_payload.get("scope_type") or ("repository" if len(repo_ids) == 1 else "workspace"))
        relations = set(base.relation_names())
        self._framework_model_available = kind == "workspace" and "v_model_object_fields" in relations
        if self._framework_model_available:
            self.query = (
                WorkspaceKnowledgeQuery.from_database(artifact, manifest=manifest)
                if manifest is not None
                else WorkspaceKnowledgeQuery(artifact)
            )
        else:
            self.query = base
        self.scope = ScopeRef(
            kind=kind, scope_id=str(manifest_payload.get("scope_id") or Path(artifact).stem), repository_ids=repo_ids
        )

    @staticmethod
    def _result(
        request: QueryRequest,
        items: list[dict[str, Any]],
        *,
        total: int | None = None,
        summary: Mapping[str, Any] | None = None,
        evidence: Iterable[EvidenceRef] = (),
    ) -> QueryResult:
        ev = {item.evidence_id: item for item in evidence}
        count = len(items) if total is None else int(total)
        return QueryResult(
            request=request,
            items=tuple(items),
            summary=dict(summary or {}),
            evidence=tuple(ev[key] for key in sorted(ev)),
            page=Page(total_count=count, returned_count=len(items), truncated=len(items) < count),
        )

    @staticmethod
    def _path_evidence(
        *, repo_id: str, owner_id: str, path: Any, line_start: Any = None, line_end: Any = None,
        extractor: str | None = None, maturity: str = "confirmed",
    ) -> EvidenceRef | None:
        normalized = _source_path(path)
        if not normalized:
            return None
        start = int(line_start) if line_start is not None else None
        end = int(line_end) if line_end is not None else start
        return EvidenceRef(
            evidence_id=stable_id("evidence", repo_id, owner_id, normalized, start, end),
            repo_id=repo_id or "unknown",
            path=normalized,
            line_start=start,
            line_end=end,
            extractor=extractor,
            maturity=maturity,
        )

    def _collect_code_types(self, *, token: str = "", max_items: int = 10000) -> list[dict[str, Any]]:
        items: list[dict[str, Any]] = []
        page_token = ""
        while len(items) < max_items:
            page = self.query.code_types(token=token, max_results=min(500, max_items - len(items)), page_token=page_token)
            items.extend(dict(item) for item in page.get("items") or ())
            page_token = str(page.get("next_token") or "")
            if not page_token:
                break
        return items

    def search_objects(
        self,
        *,
        token: str = "",
        object_kinds: tuple[str, ...] = ("root_entity", "dictionary", "entity"),
        max_results: int = 100,
    ) -> QueryResult:
        rows = self._collect_code_types(token=token)
        items: list[dict[str, Any]] = []
        evidence: list[EvidenceRef] = []
        kinds = set(object_kinds)
        for row in rows:
            annotations = tuple(str(v) for v in (row.get("annotations_json") or ()))
            kind = _classification(annotations)
            if kinds and kind not in kinds:
                continue
            object_id = str(row.get("java_type_occurrence_id") or "")
            ev = self._path_evidence(
                repo_id=str(row.get("repo_id") or "unknown"), owner_id=object_id,
                path=row.get("source_path"), maturity="confirmed",
            )
            evidence_ids = [ev.evidence_id] if ev else []
            if ev:
                evidence.append(ev)
            items.append({
                "object_id": object_id,
                "repo_id": row.get("repo_id"),
                "fqcn": row.get("fqcn"),
                "name": row.get("simple_name"),
                "package_name": row.get("package_name"),
                "object_kind": kind,
                "object_kind_basis": "annotation_name_pattern/v1",
                "annotations": list(annotations),
                "display_name": row.get("display_name"),
                "description": row.get("description"),
                "extends": row.get("extends_reference"),
                "is_abstract": bool(row.get("is_abstract")),
                "direct_field_count": int(row.get("direct_field_count") or 0),
                "evidence_ids": evidence_ids,
            })
        items.sort(key=lambda x: (x["object_kind"], str(x.get("fqcn")), str(x.get("object_id"))))
        total = len(items)
        items = items[:max_results]
        counts = Counter(str(item["object_kind"]) for item in items)
        request = QueryRequest("search_data_objects", self.scope, filters={"token": token, "object_kinds": list(object_kinds)}, max_results=max_results)
        return self._result(request, items, total=total, summary={"object_count": total, "returned_kind_counts": dict(sorted(counts.items()))}, evidence=evidence)

    def get_object(self, object_id: str) -> QueryResult:
        neighborhood = self.query.get_type_neighborhood(object_id, max_results=100)
        definitions = list(neighborhood.get("definitions") or ())
        if not definitions:
            request = QueryRequest("get_data_object", self.scope, filters={"object_id": object_id}, max_results=1)
            return self._result(request, [], total=0)
        row = dict(definitions[0])
        payload = row.get("payload_json") if isinstance(row.get("payload_json"), dict) else {}
        annotations = tuple(str(v) for v in (row.get("annotations_json") or payload.get("annotations") or ()))
        evidence: list[EvidenceRef] = []
        evidence_ids: list[str] = []
        refs = payload.get("evidence_refs") or ()
        for index, ref in enumerate(refs):
            ev = self._path_evidence(
                repo_id=str(row.get("repo_id") or "unknown"), owner_id=f"{object_id}:{index}",
                path=ref.get("file") or ref.get("file_path") or row.get("source_path"),
                line_start=ref.get("line_start") or payload.get("line_start"),
                line_end=ref.get("line_end") or payload.get("line_end"),
                extractor=ref.get("extractor"), maturity=str(payload.get("evidence_maturity_level") or "confirmed"),
            )
            if ev:
                evidence.append(ev); evidence_ids.append(ev.evidence_id)
        item = {
            "object_id": object_id,
            "repo_id": row.get("repo_id"),
            "fqcn": row.get("fqcn"),
            "name": row.get("simple_name"),
            "package_name": row.get("package_name"),
            "object_kind": _classification(annotations),
            "object_kind_basis": "annotation_name_pattern/v1",
            "annotations": list(annotations),
            "display_name": payload.get("display_name"),
            "description": payload.get("description"),
            "documentation_summary": payload.get("documentation_summary"),
            "extends": row.get("extends_reference"),
            "implements": row.get("implements_json") or [],
            "definition_repositories": neighborhood.get("definition_repositories") or [],
            "related_repositories": neighborhood.get("repositories") or [],
            "related_source_owner_count": len(neighborhood.get("related_source_owners") or ()),
            "evidence_ids": evidence_ids,
        }
        request = QueryRequest("get_data_object", self.scope, filters={"object_id": object_id}, max_results=1)
        return self._result(request, [item], summary={"found": True}, evidence=evidence)

    def _effective_field_rows(self, object_id: str, inherited: bool | None) -> dict[str, Any]:
        if self._framework_model_available:
            return self.query.model_object_fields(object_id=object_id, inherited=inherited)
        owner = object_id
        if object_id:
            neighborhood = self.query.get_type_neighborhood(object_id, max_results=10)
            definitions = list(neighborhood.get("definitions") or ())
            if definitions:
                owner = str(definitions[0].get("fqcn") or object_id)
        rows: list[dict[str, Any]] = []
        page_token = ""
        while True:
            page = self.query.effective_entity_fields(
                entity_id=owner or None,
                inherited=inherited,
                max_results=500,
                page_token=page_token,
            )
            rows.extend(dict(item) for item in page.get("items") or ())
            page_token = str(page.get("next_token") or "")
            if not page_token:
                break
        type_ids = {
            str(item.get("fqcn") or ""): str(item.get("java_type_occurrence_id") or "")
            for item in self._collect_code_types(max_items=10000)
        }
        normalized: list[dict[str, Any]] = []
        for row in rows:
            fqcn = str(row.get("effective_owner_fqcn") or "")
            normalized.append({
                **row,
                "java_type_occurrence_id": type_ids.get(fqcn),
                "object_fqcn": fqcn,
                "display_name": None,
                "description": None,
                "key_member_id": None,
                "key_position": None,
                "key_role_name": None,
            })
        return {"items": normalized, "total_count": len(normalized)}

    def get_fields(self, object_id: str, *, inherited: bool | None = None) -> QueryResult:
        raw = self._effective_field_rows(object_id, inherited)
        rows = [dict(item) for item in (raw.get("items") or ())]
        by_owner: dict[str, dict[str, dict[str, Any]]] = {}
        for owner in sorted({str(row.get("declaration_owner_fqcn") or "") for row in rows if row.get("declaration_owner_fqcn")}):
            page = self.query.code_fields(owner_fqcn=owner, max_results=500)
            by_owner[owner] = {str(item.get("field_name")): dict(item) for item in (page.get("items") or ())}
        items: list[dict[str, Any]] = []
        evidence: list[EvidenceRef] = []
        for row in rows:
            source = by_owner.get(str(row.get("declaration_owner_fqcn") or ""), {}).get(str(row.get("field_name") or ""), {})
            field_id = str(row.get("effective_field_occurrence_id") or source.get("code_field_occurrence_id") or "")
            ev = self._path_evidence(
                repo_id=str(row.get("repo_id") or source.get("repo_id") or "unknown"), owner_id=field_id,
                path=source.get("source_path"), line_start=source.get("line_start"),
                maturity=str(source.get("evidence_maturity_level") or "confirmed"),
            )
            if ev:
                evidence.append(ev)
            storage_observations: list[dict[str, Any]] = []
            for observation in row.get("storage_observations") or ():
                item = dict(observation)
                observation_evidence_ids: list[str] = []
                observation_evidence_refs: list[dict[str, Any]] = []
                for ref in item.pop("evidence", ()) or ():
                    ref_item = dict(ref)
                    observation_id = str(ref_item.get("observation_id") or item.get("call_observation_id") or field_id)
                    storage_ev = self._path_evidence(
                        repo_id=str(ref_item.get("repo_id") or row.get("repo_id") or "unknown"),
                        owner_id=observation_id,
                        path=ref_item.get("file"),
                        line_start=ref_item.get("line_start"),
                        line_end=ref_item.get("line_end"),
                        extractor=str(ref_item.get("extractor")) if ref_item.get("extractor") else None,
                        maturity="observed",
                    )
                    if storage_ev:
                        evidence.append(storage_ev)
                        observation_evidence_ids.append(storage_ev.evidence_id)
                        observation_evidence_refs.append({
                            "evidence_id": storage_ev.evidence_id,
                            "repo_id": storage_ev.repo_id,
                            "path": storage_ev.path,
                            "line_start": storage_ev.line_start,
                            "line_end": storage_ev.line_end,
                            "extractor": storage_ev.extractor,
                            "maturity": storage_ev.maturity,
                            "role": ref_item.get("role"),
                        })
                item["evidence_ids"] = sorted(set(observation_evidence_ids))
                item["evidence_refs"] = sorted(
                    observation_evidence_refs,
                    key=lambda value: (
                        str(value.get("path") or ""),
                        int(value.get("line_start") or 0),
                        str(value.get("role") or ""),
                        str(value.get("evidence_id") or ""),
                    ),
                )
                storage_observations.append(item)
            items.append({
                "field_id": field_id,
                "object_id": row.get("java_type_occurrence_id") or row.get("key_observation_id"),
                "object_fqcn": row.get("object_fqcn"),
                "repo_id": row.get("repo_id") or source.get("repo_id"),
                "name": row.get("field_name"),
                "declared_type": row.get("declared_type"),
                "effective_type": row.get("effective_type"),
                "container_kind": row.get("container_kind"),
                "element_type": row.get("element_type"),
                "display_name": row.get("display_name"),
                "description": row.get("description"),
                "declaration_owner_fqcn": row.get("declaration_owner_fqcn"),
                "inherited": bool(row.get("inherited")),
                "inheritance_depth": int(row.get("inheritance_depth") or 0),
                "key_member": bool(row.get("key_member_id")),
                "key_position": row.get("key_position"),
                "key_role_name": row.get("key_role_name"),
                "model_exclusion_observed": bool(row.get("model_exclusion_observed")),
                "storage_observation_count": int(row.get("storage_observation_count") or len(storage_observations)),
                "storage_observations": storage_observations,
                "storage_observations_truncated": bool(row.get("storage_observations_truncated")),
                "evidence_ids": [ev.evidence_id] if ev else [],
            })
        items.sort(key=lambda x: (int(x.get("inheritance_depth") or 0), str(x.get("name"))))
        request = QueryRequest("get_data_object_fields", self.scope, filters={"object_id": object_id, "inherited": inherited}, max_results=max(1, len(items)))
        return self._result(request, items, total=int(raw.get("total_count") or len(items)), summary={"field_count": len(items), "inherited_count": sum(1 for item in items if item["inherited"]), "collection_count": sum(1 for item in items if item.get("container_kind") == "collection")}, evidence=evidence)

    def list_fields(self, *, inherited: bool | None = None) -> QueryResult:
        """Return all effective model fields in one typed query.

        This is intended for complete artifact builders and avoids one database
        round-trip per model object. It preserves the same field/evidence shape as
        ``get_fields`` and does not expose relation layouts or arbitrary SQL.
        """
        result = self.get_fields("", inherited=inherited)
        request = QueryRequest(
            "list_data_model_fields",
            self.scope,
            filters={"inherited": inherited},
            max_results=max(1, len(result.items)),
        )
        return QueryResult(
            request=request,
            items=result.items,
            summary=result.summary,
            evidence=result.evidence,
            gaps=result.gaps,
            page=result.page,
        )

    def get_keys(self, object_id: str) -> QueryResult:
        raw = self.query.model_object_keys(object_id=object_id)
        items: list[dict[str, Any]] = []
        evidence: list[EvidenceRef] = []
        for row in raw.get("items") or ():
            key_id = str(row.get("key_observation_id") or "")
            ev = self._path_evidence(
                repo_id=str(row.get("repo_id") or "unknown"), owner_id=key_id,
                path=row.get("source_path"), line_start=row.get("line_start"), line_end=row.get("line_end"),
                maturity="confirmed",
            )
            if ev:
                evidence.append(ev)
            members = [{
                "position": member.get("position"), "role_name": member.get("role_name"),
                "field_name": member.get("field_name"), "field_owner_fqcn": member.get("field_owner_fqcn"),
                "field_resolution_kind": member.get("field_resolution_kind"), "inheritance_depth": member.get("inheritance_depth"),
            } for member in row.get("members") or ()]
            items.append({
                "key_id": key_id, "repo_id": row.get("repo_id"), "object_fqcn": row.get("object_fqcn"),
                "annotation_name": row.get("annotation_name"), "observation_basis": row.get("observation_basis"),
                "members": members, "member_count": len(members), "evidence_ids": [ev.evidence_id] if ev else [],
            })
        request = QueryRequest("get_data_object_keys", self.scope, filters={"object_id": object_id}, max_results=max(1, len(items)))
        return self._result(request, items, total=int(raw.get("total_count") or len(items)), summary={"key_count": len(items)}, evidence=evidence)

    def _observation_evidence_many(self, observation_ids: Iterable[str]) -> dict[str, EvidenceRef]:
        ids = sorted({str(value) for value in observation_ids if str(value).strip()})
        if not ids:
            return {}
        raw = self.query.source_observation_evidence_batch(ids)
        result: dict[str, EvidenceRef] = {}
        for row in raw.get("items") or ():
            ev = self._path_evidence(
                repo_id=str(row.get("repo_id") or "unknown"),
                owner_id=str(row.get("source_observation_occurrence_id") or row.get("local_observation_id") or ""),
                path=row.get("source_path"),
                line_start=row.get("line_start"),
                line_end=row.get("line_end"),
                extractor=str(row.get("extractor") or "") or None,
                maturity="observed",
            )
            if not ev:
                continue
            occurrence_id = str(row.get("source_observation_occurrence_id") or "")
            local_id = str(row.get("local_observation_id") or "")
            if occurrence_id:
                result.setdefault(occurrence_id, ev)
            if local_id:
                result.setdefault(local_id, ev)
        return result

    @staticmethod
    def _canonical_relationship(row: Mapping[str, Any]) -> dict[str, Any]:
        """Project evidence into the canonical consumer relationship contract.

        The projection keeps logical identity and physical storage evidence separate.
        It deliberately does not interpret alias normalization, separators or SQL.
        """

        def unique_text(values: Iterable[Any]) -> list[str]:
            result: list[str] = []
            for value in values:
                text = str(value or "").strip()
                if text and text not in result:
                    result.append(text)
            return result

        logical = row.get("target_logical_identity") if isinstance(row.get("target_logical_identity"), Mapping) else {}
        identity_fields = unique_text(logical.get("identity_fields") or ())
        version_fields = unique_text(logical.get("version_fields") or ())
        collocation_fields = unique_text(logical.get("collocation_fields") or ())

        raw_storage = [dict(item) for item in (row.get("storage_references") or ()) if isinstance(item, Mapping)]
        lineages = [dict(item) for item in (row.get("key_lineages") or ()) if isinstance(item, Mapping)]
        aliases = sorted(unique_text([
            *(item.get("target_alias") for item in raw_storage),
            *(item.get("target_alias") for item in lineages),
        ]))
        storage_fields = sorted(unique_text([
            *(item.get("target_storage_key_field") for item in raw_storage),
            *(item.get("target_storage_key_field") for item in lineages),
        ]))
        storage_expressions = unique_text([
            *(item.get("target_storage_key_expression") for item in raw_storage),
            *(item.get("target_key_expression_template") for item in lineages),
            *(item.get("composed_target_key_expression") for item in lineages),
        ])
        storage_evidence: list[dict[str, Any]] = []
        for item in raw_storage:
            storage_evidence.append({
                "storage_reference_id": item.get("storage_reference_id"),
                "target_alias": item.get("target_alias"),
                "field": item.get("target_storage_key_field"),
                "expression": item.get("target_storage_key_expression"),
                "expression_tree": item.get("target_storage_key_expression_tree_json") or {},
                "input_symbols": item.get("target_storage_key_input_symbols_json") or [],
                "parameter_bindings": item.get("binding_path_json") or [],
                "reference_operation": item.get("reference_operation"),
                "value_origin": item.get("value_origin"),
                "value_binding_resolution": item.get("reference_value_binding_resolution"),
                "source_operation": item.get("source_operation"),
                "target_converter_operation": item.get("target_converter_operation"),
                "physical_encoding": item.get("physical_encoding") or "downstream_interpretation_required",
                "provenance": {
                    "repo_id": item.get("source_repo_id"),
                    "source_observation_id": item.get("source_observation_occurrence_id"),
                    "target_storage_record_observation_id": item.get("target_storage_record_observation_occurrence_id"),
                    "path": _source_path(item.get("reference_source_path")),
                    "line_start": item.get("reference_line_start"),
                    "line_end": item.get("reference_line_end"),
                    "observation_basis": item.get("observation_basis"),
                },
            })
        for item in lineages:
            storage_evidence.append({
                "storage_lineage_id": item.get("key_lineage_id"),
                "target_alias": item.get("target_alias"),
                "field": item.get("target_storage_key_field"),
                "expression": item.get("target_key_expression_template"),
                "composed_expression": item.get("composed_target_key_expression"),
                "input_symbols": item.get("target_key_template_input_symbols_json") or [],
                "parameter_bindings": item.get("binding_path_json") or [],
                "reference_operation": item.get("reference_operation"),
                "value_origin": "collection_target_storage_key_lineage",
                "source_operation": item.get("source_operation"),
                "target_converter_operation": item.get("target_key_operation"),
                "physical_encoding": "downstream_interpretation_required",
                "provenance": {
                    "repo_id": item.get("lineage_repo_id"),
                    "source_observation_id": item.get("source_observation_occurrence_id"),
                    "path": _source_path(item.get("source_path")),
                    "line_start": item.get("line_start"),
                    "line_end": item.get("line_end"),
                    "observation_basis": item.get("observation_basis"),
                },
            })

        correspondences = [dict(item) for item in (row.get("reference_value_key_correspondences") or ()) if isinstance(item, Mapping)]
        source_expressions = unique_text(
            item.get("expression_text")
            for item in (row.get("key_expressions") or ())
            if isinstance(item, Mapping) and item.get("endpoint_role") == "source"
        )
        target_expressions = unique_text(
            item.get("expression_text")
            for item in (row.get("key_expressions") or ())
            if isinstance(item, Mapping) and item.get("endpoint_role") == "target"
        )

        if raw_storage:
            join = {
                "method": "storage_reference_requires_encoding",
                "source": {"field": row.get("source_field_name")},
                "target": {"kind": "storage_key", "fields": storage_fields},
                "requires_encoding_interpretation": True,
                "physical_join_confirmed": False,
            }
        elif lineages:
            join = {
                "method": "storage_collection_requires_encoding",
                "source": {"field": row.get("source_field_name")},
                "target": {
                    "kind": "storage_key_collection",
                    "fields": storage_fields,
                    "expressions": storage_expressions,
                },
                "collection_membership_semantics": "downstream_interpretation_required",
                "requires_encoding_interpretation": True,
                "physical_join_confirmed": False,
            }
        elif correspondences:
            first = correspondences[0]
            join = {
                "method": "logical_key_correspondence",
                "source": {
                    "field": row.get("source_field_name"),
                    "expression": first.get("composed_reference_value_expression") or first.get("reference_value_expression"),
                },
                "target": {
                    "kind": "logical_identity",
                    "fields": unique_text(first.get("target_key_fields_json") or ()),
                    "expression": first.get("target_key_expression"),
                },
                "match_basis": first.get("match_basis"),
                "requires_encoding_interpretation": False,
                "physical_join_confirmed": False,
            }
        elif target_expressions:
            first = {}
            join = {
                "method": "derived_key_evidence",
                "source": {"field": row.get("source_field_name"), "expressions": source_expressions},
                "target": {
                    "kind": "derived_key",
                    "expressions": target_expressions,
                    "composed_expression": first.get("composed_target_key_expression"),
                },
                "parent_key_passed": bool(first.get("source_key_passed_into_target_key")),
                "requires_encoding_interpretation": True,
                "physical_join_confirmed": False,
            }
        else:
            join = {
                "method": "not_established",
                "source": {"field": row.get("source_field_name")},
                "target": {"kind": "unresolved"},
                "requires_encoding_interpretation": True,
                "physical_join_confirmed": False,
            }

        reference_operations = unique_text([
            *(item.get("reference_operation") for item in raw_storage),
            *(item.get("reference_operation") for item in lineages),
        ])
        value_origins = unique_text([
            *(item.get("value_origin") for item in raw_storage),
            *("collection_target_storage_key_lineage" for _ in lineages),
        ])
        physical_statuses = unique_text([
            *(item.get("physical_encoding") for item in raw_storage),
            *("downstream_interpretation_required" for _ in lineages),
        ])
        physical_status = physical_statuses[0] if len(physical_statuses) == 1 else (
            "conflicting" if physical_statuses else "not_observed"
        )

        return {
            "relationship_id": str(row.get("relationship_id") or ""),
            "relationship_kind": row.get("relation_kind"),
            "source": {
                "repo_id": row.get("source_repo_id"),
                "object_id": row.get("source_java_type_occurrence_id"),
                "object_fqcn": row.get("source_object_fqcn"),
                "field": row.get("source_field_name"),
                "inherited": bool(row.get("source_field_inherited")),
                "cardinality": row.get("cardinality"),
            },
            "target": {
                "repo_id": row.get("target_repo_id"),
                "object_id": row.get("target_java_type_occurrence_id"),
                "type_fqcn": row.get("target_type_fqcn"),
                "aliases": aliases,
                "logical_identity": {
                    "status": "observed" if (identity_fields or version_fields or collocation_fields) else "not_observed",
                    "fields": identity_fields,
                    "version_fields": version_fields,
                    "collocation_fields": collocation_fields,
                    "classification_basis": logical.get("classification_basis") or "not_observed",
                },
                "storage_key": {
                    "status": "observed" if (raw_storage or lineages) else "not_observed",
                    "fields": storage_fields,
                    "expressions": storage_expressions,
                    "evidence": storage_evidence,
                },
            },
            "polymorphic_targets": unique_text(
                item.get("target_type_fqcn") if isinstance(item, Mapping) else item
                for item in (row.get("polymorphic_targets") or ())
            ),
            "reference": {
                "assignment_operations": reference_operations,
                "value_origins": value_origins,
                "encoding_inputs": {
                    "type_component": {"source": "target_alias", "values": aliases},
                    "key_component": {"source": "target_storage_key", "fields": storage_fields},
                },
                "physical_encoding": {"status": physical_status},
            },
            "join": join,
        }

    def _get_effective_relationships(
        self, *, source_object_id: str = "", target_object_id: str = "", relation_kind: str | None = None
    ) -> QueryResult:
        source_token = source_object_id
        target_token = target_object_id
        for value, target_name in ((source_object_id, "source"), (target_object_id, "target")):
            if not value:
                continue
            neighborhood = self.query.get_type_neighborhood(value, max_results=10)
            definitions = list(neighborhood.get("definitions") or ())
            resolved = str(definitions[0].get("fqcn") or value) if definitions else value
            if target_name == "source":
                source_token = resolved
            else:
                target_token = resolved
        rows: list[dict[str, Any]] = []
        page_token = ""
        while True:
            page = self.query.effective_entity_associations(
                entity_id=source_token or None,
                target_entity_id=target_token or None,
                max_results=500,
                page_token=page_token,
            )
            rows.extend(dict(item) for item in page.get("items") or ())
            page_token = str(page.get("next_token") or "")
            if not page_token:
                break
        type_ids = {
            str(item.get("fqcn") or ""): str(item.get("java_type_occurrence_id") or "")
            for item in self._collect_code_types(max_items=10000)
        }
        items: list[dict[str, Any]] = []
        for row in rows:
            source_fqcn = str(row.get("effective_owner_fqcn") or "")
            target_fqcn = str(row.get("target_observed_fqcn") or row.get("target_type_reference") or "")
            observed_kind = "effective_association"
            if relation_kind and relation_kind != observed_kind:
                continue
            canonical = self._canonical_relationship({
                "relationship_id": row.get("effective_association_occurrence_id"),
                "source_repo_id": row.get("repo_id"),
                "source_java_type_occurrence_id": type_ids.get(source_fqcn),
                "source_object_fqcn": source_fqcn,
                "source_field_name": row.get("source_field"),
                "source_field_inherited": bool(row.get("inherited")),
                "target_repo_id": row.get("repo_id"),
                "target_java_type_occurrence_id": type_ids.get(target_fqcn),
                "target_type_fqcn": target_fqcn,
                "relation_kind": observed_kind,
                "cardinality": "many" if row.get("container_kind") == "collection" else "one",
            })
            canonical["evidence_ids"] = []
            items.append(canonical)
        items.sort(key=lambda x: (str((x.get("source") or {}).get("field")), str((x.get("target") or {}).get("type_fqcn")), str(x.get("relationship_id"))))
        request = QueryRequest(
            "get_data_object_relationships",
            self.scope,
            filters={"source_object_id": source_object_id, "target_object_id": target_object_id, "relation_kind": relation_kind},
            max_results=max(1, len(items)),
        )
        return self._result(
            request,
            items,
            total=len(items),
            summary={"relationship_count": len(items), "relation_kind_counts": dict(Counter(str(item.get("relationship_kind")) for item in items))},
        )

    def get_relationships(
        self, *, source_object_id: str = "", target_object_id: str = "", relation_kind: str | None = None
    ) -> QueryResult:
        if not self._framework_model_available:
            return self._get_effective_relationships(
                source_object_id=source_object_id,
                target_object_id=target_object_id,
                relation_kind=relation_kind,
            )
        raw = self.query.model_relationships(source_object_id=source_object_id, target_object_id=target_object_id, relation_kind=relation_kind)
        items: list[dict[str, Any]] = []
        evidence: list[EvidenceRef] = []
        relationship_observation_ids: dict[str, list[str]] = {}
        all_observation_ids: list[str] = []
        for row in raw.get("items") or ():
            relationship_id = str(row.get("relationship_id") or "")
            observation_ids: list[str] = []
            observation_ids.extend(str(v) for v in (row.get("converter_operation_observation_ids_json") or ()))
            for entry in row.get("key_lineages") or ():
                if entry.get("source_observation_occurrence_id"):
                    observation_ids.append(str(entry["source_observation_occurrence_id"]))
            for entry in row.get("reference_value_key_correspondences") or ():
                for key in ("reference_value_observation_occurrence_id", "target_key_observation_occurrence_id"):
                    if entry.get(key):
                        observation_ids.append(str(entry[key]))
            for entry in row.get("storage_references") or ():
                for key in ("source_observation_occurrence_id", "target_storage_record_observation_occurrence_id"):
                    if entry.get(key):
                        observation_ids.append(str(entry[key]))
            unique_ids = sorted(set(observation_ids))
            relationship_observation_ids[relationship_id] = unique_ids
            all_observation_ids.extend(unique_ids)
        evidence_by_observation = self._observation_evidence_many(all_observation_ids)
        for row in raw.get("items") or ():
            relationship_id = str(row.get("relationship_id") or "")
            refs: list[EvidenceRef] = []
            for observation_id in relationship_observation_ids.get(relationship_id, ()):
                ev = evidence_by_observation.get(observation_id)
                if ev and ev.evidence_id not in {item.evidence_id for item in refs}:
                    refs.append(ev)
                if len(refs) >= 4:
                    break
            evidence.extend(refs)
            item = self._canonical_relationship(row)
            item["evidence_ids"] = [ref.evidence_id for ref in refs]
            items.append(item)
        items.sort(key=lambda x: (str((x.get("source") or {}).get("field")), str((x.get("target") or {}).get("type_fqcn")), str(x.get("relationship_id"))))
        request = QueryRequest("get_data_object_relationships", self.scope, filters={"source_object_id": source_object_id, "target_object_id": target_object_id, "relation_kind": relation_kind}, max_results=max(1, len(items)))
        counts = Counter(str(item.get("relationship_kind")) for item in items)
        return self._result(request, items, total=int(raw.get("total_count") or len(items)), summary={"relationship_count": len(items), "relation_kind_counts": dict(sorted(counts.items()))}, evidence=evidence)

    def get_cross_repository_correspondences(self, *, token: str = "", max_results: int = 100) -> QueryResult:
        def collect(method: Any, **kwargs: Any) -> tuple[list[dict[str, Any]], int]:
            items: list[dict[str, Any]] = []
            page_token = ""
            total = 0
            while len(items) < max_results:
                page = method(
                    token=token,
                    match_scope="cross_repository",
                    max_results=min(500, max_results - len(items)),
                    page_token=page_token,
                    **kwargs,
                )
                total = int(page.get("total_count") or 0)
                items.extend(dict(row) for row in (page.get("items") or ()))
                page_token = str(page.get("next_token") or "")
                if not page_token:
                    break
            return items, total

        configuration_items, configuration_total = collect(self.query.configuration_type_correspondences)
        if hasattr(self.query, "type_reference_resolutions"):
            resolution_items, resolution_total = collect(self.query.type_reference_resolutions)
        else:
            resolution_items, resolution_total = [], 0
        rows: list[tuple[str, Mapping[str, Any]]] = []
        rows.extend(("configuration_type", row) for row in configuration_items)
        rows.extend(("type_reference", row) for row in resolution_items)
        observation_ids = [
            str(row.get("source_observation_occurrence_id") or "") for _, row in rows
            if row.get("source_observation_occurrence_id")
        ]
        evidence_by_observation = self._observation_evidence_many(observation_ids)
        items: list[dict[str, Any]] = []
        evidence: list[EvidenceRef] = []
        for kind, row in rows:
            source_repo_id = row.get("source_repo_id")
            target_repo_id = row.get("target_repo_id")
            if not source_repo_id or not target_repo_id or source_repo_id == target_repo_id:
                continue
            observation_id = str(row.get("source_observation_occurrence_id") or "")
            ev = evidence_by_observation.get(observation_id)
            if ev:
                evidence.append(ev)
            if kind == "configuration_type":
                item = {
                    "correspondence_id": row.get("observation_id"),
                    "kind": kind,
                    "source_repo_id": source_repo_id,
                    "target_repo_id": target_repo_id,
                    "configuration_path": row.get("configuration_path"),
                    "referenced_fqcn": row.get("referenced_fqcn"),
                    "target_object_id": row.get("target_java_type_occurrence_id"),
                    "match_scope": row.get("match_scope"),
                    "match_basis": row.get("match_basis"),
                    "evidence_ids": [ev.evidence_id] if ev else [],
                }
            else:
                item = {
                    "correspondence_id": row.get("resolution_candidate_id"),
                    "kind": kind,
                    "source_repo_id": source_repo_id,
                    "target_repo_id": target_repo_id,
                    "owner_fqcn": row.get("owner_fqcn"),
                    "referenced_type": row.get("referenced_type"),
                    "candidate_fqcn": row.get("candidate_fqcn"),
                    "target_object_id": row.get("target_java_type_occurrence_id"),
                    "match_scope": row.get("match_scope"),
                    "match_basis": row.get("match_basis"),
                    "evidence_ids": [ev.evidence_id] if ev else [],
                }
            items.append(item)
        items.sort(key=lambda item: (
            str(item.get("kind")),
            str(item.get("source_repo_id")),
            str(item.get("target_repo_id")),
            str(item.get("candidate_fqcn") or item.get("referenced_fqcn")),
            str(item.get("correspondence_id")),
        ))
        items = items[:max_results]
        total = configuration_total + resolution_total
        request = QueryRequest(
            "get_cross_repository_correspondences", self.scope,
            filters={"token": token, "match_scope": "cross_repository"}, max_results=max_results,
        )
        counts = Counter(str(item.get("kind")) for item in items)
        return self._result(
            request, items, total=total,
            summary={
                "correspondence_count": total,
                "returned_count": len(items),
                "returned_kind_counts": dict(sorted(counts.items())),
                "selection_scope": "cross_repository_only",
            },
            evidence=evidence,
        )


    def get_join_guidance(self, *, source_object_id: str, target_object_id: str = "", target_name: str = "") -> QueryResult:
        relationships = self.get_relationships(source_object_id=source_object_id, target_object_id=target_object_id)
        items = [dict(item) for item in relationships.items]
        if target_name:
            needle = target_name.casefold()
            items = [item for item in items if needle in str((item.get("target") or {}).get("type_fqcn") or "").casefold() or needle == str((item.get("source") or {}).get("field") or "").casefold()]
        request = QueryRequest("get_join_guidance", self.scope, filters={"source_object_id": source_object_id, "target_object_id": target_object_id, "target_name": target_name}, max_results=max(1, len(items)))
        evidence_ids = {eid for item in items for eid in item.get("evidence_ids") or ()}
        refs = [ref for ref in relationships.evidence if ref.evidence_id in evidence_ids]
        return self._result(request, items, summary={"relationship_count": len(items), "physical_join_confirmed": all(bool((item.get("join") or {}).get("physical_join_confirmed")) for item in items) if items else False}, evidence=refs)
