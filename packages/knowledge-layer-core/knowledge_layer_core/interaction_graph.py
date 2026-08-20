from __future__ import annotations

import json
import re
from collections import defaultdict, deque
from dataclasses import dataclass
from typing import Any, Iterable, Mapping
from urllib.parse import urlsplit

from .bulk import bulk_insert
from .metrics import canonical_json
from prepared_knowledge_runtime.normalization import stable_id


INTERACTION_GRAPH_SCHEMA_VERSION = "workspace_system_interaction/v5"

_LOOPBACK_HOSTS = {"localhost", "0.0.0.0", "::", "::1"}


@dataclass(frozen=True, slots=True)
class _InterfaceRecord:
    record_occurrence_id: str
    repo_id: str
    interface_id: str
    payload: dict[str, Any]


@dataclass(frozen=True, slots=True)
class _RepositoryIdentity:
    repo_id: str
    system_id: str | None
    project_id: str | None
    configured_service_aliases: tuple[str, ...]
    matching_aliases: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class _HttpBoundary:
    record: _InterfaceRecord
    direction: str
    boundary_kind: str
    http_method: str
    normalized_paths: tuple[str, ...]
    authorities: tuple[str, ...]
    service_identities: tuple[str, ...]
    property_identities: tuple[str, ...]
    base_url_property_keys: tuple[str, ...]
    contract_fingerprint: str | None
    system_id: str | None
    project_id: str | None
    configured_service_aliases: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class _TargetRoute:
    repo_id: str
    http_method: str
    normalized_path: str
    representative: _HttpBoundary
    candidate_interface_ids: tuple[str, ...]
    authorities: tuple[str, ...]
    service_identities: tuple[str, ...]
    property_identities: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class _TargetIndexes:
    routes: tuple[_TargetRoute, ...]
    by_method_path: Mapping[tuple[str, str], tuple[_TargetRoute, ...]]
    by_authority_method_path: Mapping[tuple[str, str, str], tuple[_TargetRoute, ...]]
    by_service_method_path: Mapping[tuple[str, str, str], tuple[_TargetRoute, ...]]
    by_property_method_path: Mapping[tuple[str, str, str], tuple[_TargetRoute, ...]]


def _mapping(value: Any) -> dict[str, Any]:
    if isinstance(value, Mapping):
        return dict(value)
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
        except json.JSONDecodeError:
            return {}
        return dict(parsed) if isinstance(parsed, Mapping) else {}
    return {}


def _values(payload: Mapping[str, Any], key: str) -> list[str]:
    value = payload.get(key)
    if value is None:
        return []
    if isinstance(value, (list, tuple, set)):
        return [str(item) for item in value if str(item).strip()]
    return [str(value)] if str(value).strip() else []


def _stable_values(values: Iterable[str]) -> tuple[str, ...]:
    return tuple(dict.fromkeys(value for value in values if value))


def _normalize_path_fragment(value: object) -> tuple[str, ...]:
    text = str(value or "").strip()
    if not text:
        return ()
    candidates: list[str] = []
    if "://" in text:
        try:
            candidates.append(urlsplit(text).path)
        except ValueError:
            pass
    if text.startswith("/"):
        candidates.append(text)
    candidates.extend(re.findall(r"(?<![:A-Za-z0-9_])/[A-Za-z0-9_./{}-]+", text))
    normalized: list[str] = []
    for candidate in candidates:
        value_without_query = candidate.split("?", 1)[0].split("#", 1)[0]
        collapsed = re.sub(r"/+", "/", value_without_query)
        if len(collapsed) > 1:
            collapsed = collapsed.rstrip("/")
        # HTTP path matching is case-sensitive. Normalization may collapse
        # redundant separators/trailing slash, but must preserve observed case.
        if collapsed and collapsed.casefold() not in {"/localhost"}:
            normalized.append(collapsed)
    return _stable_values(normalized)


def _interface_paths(payload: Mapping[str, Any], *, inbound: bool) -> tuple[str, ...]:
    raw: list[str] = []
    raw.extend(_values(payload, "endpoint_or_topic_raw"))
    raw.extend(_values(payload, "endpoint_or_topic_resolved"))
    if inbound:
        full_paths = _values(payload, "full_path_variants")
        if full_paths:
            raw.extend(full_paths)
        else:
            base_paths = _values(payload, "registration_base_path_variants")
            method_paths = _values(payload, "method_path_variants")
            if base_paths and method_paths:
                raw.extend(
                    f"{base.rstrip('/')}/{method.lstrip('/')}"
                    for base in base_paths
                    for method in method_paths
                )
            elif method_paths:
                raw.extend(method_paths)
    else:
        for key in (
            "endpoint_path_observed_values",
            "endpoint_path_variants",
            "endpoint_url_variants",
            "full_path_variants",
        ):
            raw.extend(_values(payload, key))
    paths: list[str] = []
    for value in raw:
        paths.extend(_normalize_path_fragment(value))
    return _stable_values(paths)


def _normalize_authority(value: object) -> tuple[str, ...]:
    text = str(value or "").strip()
    if not text:
        return ()
    parsed = None
    if "://" in text:
        try:
            parsed = urlsplit(text)
        except ValueError:
            parsed = None
    elif text.startswith("//"):
        try:
            parsed = urlsplit(f"http:{text}")
        except ValueError:
            parsed = None
    elif "/" not in text and " " not in text and "+" not in text and not text.startswith("${"):
        try:
            parsed = urlsplit(f"http://{text}")
        except ValueError:
            parsed = None
    if parsed is None or not parsed.hostname:
        return ()
    host = parsed.hostname.casefold().rstrip(".")
    authority = parsed.netloc.casefold().split("@", 1)[-1].rstrip(".")
    return _stable_values((authority, host))


def _authority_host(value: object) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    try:
        if "://" in text:
            parsed = urlsplit(text)
        elif text.startswith("//"):
            parsed = urlsplit(f"http:{text}")
        else:
            parsed = urlsplit(f"http://{text}")
    except ValueError:
        return ""
    return str(parsed.hostname or "").casefold().rstrip(".")


def _is_environment_authority(value: object) -> bool:
    host = _authority_host(value)
    return bool(host and (host in _LOOPBACK_HOSTS or host.endswith(".localhost")))


def _normalize_identity(value: object) -> tuple[str, ...]:
    text = str(value or "").strip()
    if not text or text.startswith("${") or " + " in text:
        return ()
    authority_tokens = _normalize_authority(text)
    if authority_tokens:
        base = authority_tokens[-1]
    else:
        base = text.casefold().strip("/.")
        if "/" in base:
            base = base.split("/", 1)[0]
        if ":" in base and base.count(":") == 1:
            base = base.split(":", 1)[0]
    canonical = re.sub(r"[^a-z0-9-]+", "-", base.replace("_", "-")).strip("-")
    if not canonical:
        return ()
    variants = [canonical]
    if "." in base:
        first = re.sub(r"[^a-z0-9-]+", "-", base.split(".", 1)[0].replace("_", "-")).strip("-")
        if first:
            variants.append(first)
    return _stable_values(variants)


def _property_identity(value: object) -> tuple[str, ...]:
    text = str(value or "").strip().casefold()
    if not text:
        return ()
    text = re.sub(r"\$\{|\}", "", text)
    suffixes = (
        ".base-url", ".base_url", ".baseurl", ".url", ".uri", ".host",
        "-base-url", "_base_url", ".endpoint",
    )
    for suffix in suffixes:
        if text.endswith(suffix):
            text = text[: -len(suffix)]
            break
    if "." in text:
        text = text.rsplit(".", 1)[-1]
    return _normalize_identity(text)


def _http_method(payload: Mapping[str, Any]) -> str:
    return str(payload.get("http_method") or "").strip().upper()


def _operation_quality(payload: Mapping[str, Any]) -> tuple[int, int, int, str]:
    operation = str(payload.get("operation") or "").strip()
    qualified = int("." in operation)
    generic_http_label = int(bool(re.match(r"^(GET|POST|PUT|DELETE|PATCH)\s", operation, re.I)))
    contract_size = len(payload.get("request_contract_signature") or ())
    return qualified, -generic_http_label, contract_size, operation


def _wire_fields(payload: Mapping[str, Any], key: str) -> set[str]:
    fields: set[str] = set()
    for item in payload.get(key) or ():
        if not isinstance(item, Mapping):
            continue
        raw = item.get("attribute_path") or item.get("wire_name") or item.get("attribute_name")
        if raw is None:
            continue
        value = re.sub(r"\[\]", "", str(raw)).strip(".").casefold()
        if value:
            fields.add(value)
    return fields


def _contract_fingerprint(payload: Mapping[str, Any]) -> str | None:
    fields = sorted(_wire_fields(payload, "request_contract_signature"))
    payload_type = str(payload.get("request_payload_type") or payload.get("payload_schema_ref") or "").strip().casefold()
    if not fields and not payload_type:
        return None
    return stable_id("http_request_contract", payload_type, *fields)


def _contract_match(outbound: Mapping[str, Any], inbound: Mapping[str, Any]) -> dict[str, Any]:
    outbound_fields = _wire_fields(outbound, "request_contract_signature")
    inbound_fields = _wire_fields(inbound, "request_contract_signature")
    overlap = sorted(outbound_fields & inbound_fields)
    union = outbound_fields | inbound_fields
    similarity = (len(overlap) / len(union)) if union else 0.0
    outbound_type = str(outbound.get("request_payload_type") or outbound.get("payload_schema_ref") or "").strip()
    inbound_type = str(inbound.get("request_payload_type") or inbound.get("payload_schema_ref") or "").strip()
    type_match = bool(outbound_type and inbound_type and outbound_type.casefold() == inbound_type.casefold())
    return {
        "request_field_overlap": overlap,
        "request_field_overlap_count": len(overlap),
        "request_field_similarity": round(similarity, 6),
        "request_payload_type_match": type_match,
        "outbound_request_payload_type": outbound_type or None,
        "inbound_request_payload_type": inbound_type or None,
    }


def _load_interfaces(connection: Any) -> list[_InterfaceRecord]:
    rows = connection.execute(
        """SELECT record_occurrence_id, repo_id, coalesce(local_record_id, ''), payload_json
           FROM interaction_boundary_evidence_record
           ORDER BY repo_id, occurrence_ordinal, record_occurrence_id"""
    ).fetchall()
    records: list[_InterfaceRecord] = []
    for record_occurrence_id, repo_id, local_record_id, payload_json in rows:
        payload = _mapping(payload_json)
        interface_id = str(payload.get("interface_id") or local_record_id or record_occurrence_id)
        records.append(
            _InterfaceRecord(
                record_occurrence_id=str(record_occurrence_id),
                repo_id=str(repo_id),
                interface_id=interface_id,
                payload=payload,
            )
        )
    return records


def _repository_identities(connection: Any) -> dict[str, _RepositoryIdentity]:
    metadata: dict[str, dict[str, Any]] = {}

    def item(repo_id: object) -> dict[str, Any]:
        repo = str(repo_id)
        return metadata.setdefault(
            repo,
            {
                "repo_id": repo,
                "system_id": None,
                "project_id": None,
                "configured_service_aliases": [],
                "matching_aliases": list(_normalize_identity(repo)),
            },
        )

    try:
        typed_rows = connection.execute(
            "SELECT repo_id, system_id, project_id, configured_service_aliases_json FROM interaction_repository_identity ORDER BY repo_id"
        ).fetchall()
    except Exception:
        typed_rows = []
    for repo_id, system_id, project_id, aliases_json in typed_rows:
        current = item(repo_id)
        current["system_id"] = str(system_id) if system_id is not None else None
        current["project_id"] = str(project_id) if project_id is not None else None
        configured = None
        if isinstance(aliases_json, str):
            try:
                configured = json.loads(aliases_json)
            except json.JSONDecodeError:
                configured = []
        elif isinstance(aliases_json, (list, tuple)):
            configured = aliases_json
        else:
            configured = []
        current["configured_service_aliases"].extend(str(value) for value in configured if str(value).strip())
        current["matching_aliases"].extend(_normalize_identity(system_id))
        for value in configured:
            current["matching_aliases"].extend(_normalize_identity(value))

    try:
        rows = connection.execute(
            "SELECT repo_id, system_name, project_code FROM workspace_repository ORDER BY repo_id"
        ).fetchall()
    except Exception:
        rows = []
    for repo_id, system_name, project_code in rows:
        current = item(repo_id)
        if system_name and current["system_id"] is None:
            current["system_id"] = str(system_name)
        if project_code and current["project_id"] is None:
            current["project_id"] = str(project_code)
        current["matching_aliases"].extend(_normalize_identity(system_name))

    return {
        repo_id: _RepositoryIdentity(
            repo_id=repo_id,
            system_id=(str(values["system_id"]) if values["system_id"] is not None else None),
            project_id=(str(values["project_id"]) if values["project_id"] is not None else None),
            configured_service_aliases=_stable_values(
                str(value).strip() for value in values["configured_service_aliases"]
            ),
            matching_aliases=_stable_values(values["matching_aliases"]),
        )
        for repo_id, values in metadata.items()
    }


def _repository_identity(
    repo_id: str, repository_identities: Mapping[str, _RepositoryIdentity]
) -> _RepositoryIdentity:
    return repository_identities.get(
        repo_id,
        _RepositoryIdentity(
            repo_id=repo_id,
            system_id=None,
            project_id=None,
            configured_service_aliases=(),
            matching_aliases=_normalize_identity(repo_id),
        ),
    )


def _boundary_authorities(payload: Mapping[str, Any]) -> tuple[str, ...]:
    values: list[str] = []
    for key in (
        "authority", "authorities", "hostname", "hostnames",
        "base_url_observed_values", "endpoint_url_variants",
        "endpoint_or_topic_resolved",
    ):
        for raw in _values(payload, key):
            values.extend(_normalize_authority(raw))
    return _stable_values(values)


def _boundary_service_identities(
    record: _InterfaceRecord,
    *,
    authorities: tuple[str, ...],
    repository_identity: _RepositoryIdentity,
) -> tuple[str, ...]:
    values: list[str] = []
    payload = record.payload
    for key in (
        "service_identity", "service_identities", "service_alias", "service_aliases",
        "target_service", "service_name", "hostname", "hostnames", "authority", "authorities",
    ):
        for raw in _values(payload, key):
            values.extend(_normalize_identity(raw))
    for authority in authorities:
        values.extend(_normalize_identity(authority))
    if payload.get("direction") == "inbound":
        values.extend(repository_identity.matching_aliases)
    return _stable_values(values)


def _boundary_property_identities(payload: Mapping[str, Any]) -> tuple[str, ...]:
    values: list[str] = []
    for key in ("base_url_property_key", "base_url_property_keys", "endpoint_or_topic_property_key"):
        for raw in _values(payload, key):
            values.extend(_property_identity(raw))
    return _stable_values(values)


def _http_boundaries(
    interfaces: Iterable[_InterfaceRecord],
    *,
    repository_identities: Mapping[str, _RepositoryIdentity],
) -> tuple[_HttpBoundary, ...]:
    boundaries: list[_HttpBoundary] = []
    for record in interfaces:
        payload = record.payload
        direction = str(payload.get("direction") or "").strip()
        boundary_kind = str(payload.get("boundary_kind") or "").strip()
        if (direction, boundary_kind) not in {
            ("inbound", "rest_request"),
            ("outbound", "http_outbound"),
        }:
            continue
        authorities = _boundary_authorities(payload)
        repository_identity = _repository_identity(record.repo_id, repository_identities)
        boundaries.append(
            _HttpBoundary(
                record=record,
                direction=direction,
                boundary_kind=boundary_kind,
                http_method=_http_method(payload),
                normalized_paths=_interface_paths(payload, inbound=direction == "inbound"),
                authorities=authorities,
                service_identities=_boundary_service_identities(
                    record,
                    authorities=authorities,
                    repository_identity=repository_identity,
                ),
                property_identities=_boundary_property_identities(payload),
                base_url_property_keys=_stable_values(
                    value
                    for key in ("base_url_property_key", "base_url_property_keys")
                    for value in _values(payload, key)
                ),
                contract_fingerprint=_contract_fingerprint(payload),
                system_id=repository_identity.system_id,
                project_id=repository_identity.project_id,
                configured_service_aliases=repository_identity.configured_service_aliases,
            )
        )
    return tuple(boundaries)


def _load_typed_local_call_graph(
    interfaces: Iterable[_InterfaceRecord],
) -> tuple[dict[str, dict[str, set[str]]], dict[tuple[str, str, str], tuple[str, ...]]]:
    """Build local execution reachability from typed boundary evidence.

    Core already publishes local_call_chain_candidates on interaction-boundary
    observations.  The system-interactions materialization must compose those
    typed facts directly instead of depending on the canonical typed boundary evidence surface.
    """
    adjacency: dict[str, dict[str, set[str]]] = defaultdict(lambda: defaultdict(set))
    evidence_records: dict[tuple[str, str, str], list[str]] = defaultdict(list)

    def add_edge(record: _InterfaceRecord, caller: object, callee: object) -> None:
        caller_name = str(caller or "").strip()
        callee_name = str(callee or "").strip()
        if not caller_name or not callee_name or caller_name == callee_name:
            return
        adjacency[record.repo_id][caller_name].add(callee_name)
        key = (record.repo_id, caller_name, callee_name)
        if record.record_occurrence_id not in evidence_records[key]:
            evidence_records[key].append(record.record_occurrence_id)

    for record in interfaces:
        payload = record.payload
        for candidate in payload.get("local_call_chain_candidates") or ():
            if not isinstance(candidate, Mapping):
                continue
            add_edge(record, candidate.get("caller_operation"), candidate.get("called_operation"))

        # Helper-composed outbound observations are concrete call sites of one
        # shared HTTP helper.  Keep the scenario as execution context and add
        # only the evidence-backed scenario -> helper step.
        if str(payload.get("composition_basis") or "") == "helper_method_template_and_concrete_call_site":
            add_edge(record, payload.get("scenario_operation"), payload.get("helper_operation"))

    return (
        {repo: dict(items) for repo, items in adjacency.items()},
        {key: tuple(values) for key, values in evidence_records.items()},
    )


def _compose_shared_outbound_boundaries(
    boundaries: Iterable[_HttpBoundary],
) -> tuple[_HttpBoundary, ...]:
    """Compose repeated helper call-site observations into one technical boundary.

    Grouping is deliberately evidence-driven: only Core observations explicitly
    marked as helper_method_template_and_concrete_call_site are candidates, and
    they must share helper, client, addressing/path and request/response contract
    identity.  Scenario-specific observations are retained in provenance and are
    later exposed as execution contexts.
    """
    passthrough: list[_HttpBoundary] = []
    groups: dict[tuple[Any, ...], list[_HttpBoundary]] = defaultdict(list)

    for boundary in boundaries:
        payload = boundary.record.payload
        helper = str(payload.get("helper_operation") or "").strip()
        client = str(payload.get("client_bean_name") or "").strip()
        composition_basis = str(payload.get("composition_basis") or "").strip()
        if (
            boundary.direction != "outbound"
            or composition_basis != "helper_method_template_and_concrete_call_site"
            or not helper
            or not client
        ):
            passthrough.append(boundary)
            continue

        key = (
            boundary.record.repo_id,
            helper,
            client,
            boundary.http_method,
            boundary.normalized_paths,
            boundary.authorities,
            boundary.property_identities,
            boundary.base_url_property_keys,
            str(payload.get("endpoint_or_topic_raw") or ""),
            str(payload.get("endpoint_or_topic_resolved") or ""),
            str(payload.get("request_payload_type") or ""),
            canonical_json(payload.get("request_contract_signature") or []),
            str(payload.get("response_payload_type") or ""),
            canonical_json(payload.get("response_contract_signature") or []),
        )
        groups[key].append(boundary)

    composed: list[_HttpBoundary] = []
    for key, members in sorted(groups.items(), key=lambda item: repr(item[0])):
        if len(members) == 1:
            composed.append(members[0])
            continue
        ordered = sorted(members, key=lambda item: item.record.interface_id)
        representative = ordered[0]
        payload = dict(representative.record.payload)
        observation_ids = [item.record.interface_id for item in ordered]
        record_ids = [item.record.record_occurrence_id for item in ordered]
        scenarios = _stable_values(
            str(item.record.payload.get("scenario_operation") or item.record.payload.get("operation") or "").strip()
            for item in ordered
        )
        payload.update(
            {
                "operation": str(payload.get("helper_operation") or payload.get("operation") or ""),
                "scenario_operations": list(scenarios),
                "observed_interface_ids": observation_ids,
                "observed_interface_record_ids": record_ids,
                "grouped_outbound_observation_count": len(ordered),
                "boundary_composition_basis": "shared_helper_client_address_and_contract",
                "grouped_outbound_observations": [
                    {
                        "interface_id": item.record.interface_id,
                        "record_occurrence_id": item.record.record_occurrence_id,
                        "operation": item.record.payload.get("operation"),
                        "scenario_operation": item.record.payload.get("scenario_operation"),
                        "local_caller_operations": item.record.payload.get("local_caller_operations") or [],
                    }
                    for item in ordered
                ],
            }
        )
        synthetic_interface_id = stable_id(
            "composed_http_outbound_boundary",
            representative.record.repo_id,
            str(payload.get("helper_operation") or ""),
            str(payload.get("client_bean_name") or ""),
            representative.http_method,
            *representative.normalized_paths,
            *observation_ids,
        )
        record = _InterfaceRecord(
            record_occurrence_id=representative.record.record_occurrence_id,
            repo_id=representative.record.repo_id,
            interface_id=synthetic_interface_id,
            payload=payload,
        )
        composed.append(
            _HttpBoundary(
                record=record,
                direction=representative.direction,
                boundary_kind=representative.boundary_kind,
                http_method=representative.http_method,
                normalized_paths=representative.normalized_paths,
                authorities=representative.authorities,
                service_identities=representative.service_identities,
                property_identities=representative.property_identities,
                base_url_property_keys=representative.base_url_property_keys,
                contract_fingerprint=representative.contract_fingerprint,
                system_id=representative.system_id,
                project_id=representative.project_id,
                configured_service_aliases=representative.configured_service_aliases,
            )
        )

    return tuple(sorted([*passthrough, *composed], key=lambda item: (item.record.repo_id, item.direction, item.record.interface_id)))


def _shortest_call_path(adjacency: Mapping[str, set[str]], source: str, target: str, *, max_depth: int = 20) -> list[str] | None:
    if not source or not target:
        return None
    queue = deque([(source, [source])])
    visited: set[str] = set()
    while queue:
        node, path = queue.popleft()
        if node in visited:
            continue
        visited.add(node)
        if node == target:
            return path
        if len(path) >= max_depth:
            continue
        for next_node in sorted(adjacency.get(node, ())):
            queue.append((next_node, [*path, next_node]))
    return None


def _freeze_index(index: Mapping[Any, list[_TargetRoute]]) -> dict[Any, tuple[_TargetRoute, ...]]:
    return {
        key: tuple(sorted(value, key=lambda route: (route.repo_id, route.normalized_path, route.representative.record.interface_id)))
        for key, value in index.items()
    }


def _target_indexes(boundaries: Iterable[_HttpBoundary]) -> _TargetIndexes:
    grouped: dict[tuple[str, str, str], list[_HttpBoundary]] = defaultdict(list)
    for boundary in boundaries:
        if boundary.direction != "inbound" or boundary.boundary_kind != "rest_request":
            continue
        for path in boundary.normalized_paths:
            grouped[(boundary.record.repo_id, boundary.http_method, path)].append(boundary)

    routes: list[_TargetRoute] = []
    for (repo_id, method, path), candidates in grouped.items():
        ordered = sorted(candidates, key=lambda item: _operation_quality(item.record.payload), reverse=True)
        representative = ordered[0]
        routes.append(
            _TargetRoute(
                repo_id=repo_id,
                http_method=method,
                normalized_path=path,
                representative=representative,
                candidate_interface_ids=tuple(sorted({item.record.interface_id for item in candidates})),
                authorities=_stable_values(value for item in candidates for value in item.authorities),
                service_identities=_stable_values(value for item in candidates for value in item.service_identities),
                property_identities=_stable_values(value for item in candidates for value in item.property_identities),
            )
        )

    by_method_path: dict[tuple[str, str], list[_TargetRoute]] = defaultdict(list)
    by_authority: dict[tuple[str, str, str], list[_TargetRoute]] = defaultdict(list)
    by_service: dict[tuple[str, str, str], list[_TargetRoute]] = defaultdict(list)
    by_property: dict[tuple[str, str, str], list[_TargetRoute]] = defaultdict(list)
    for route in routes:
        by_method_path[(route.http_method, route.normalized_path)].append(route)
        for authority in route.authorities:
            by_authority[(authority, route.http_method, route.normalized_path)].append(route)
        for identity in route.service_identities:
            by_service[(identity, route.http_method, route.normalized_path)].append(route)
        for identity in route.property_identities:
            by_property[(identity, route.http_method, route.normalized_path)].append(route)
    return _TargetIndexes(
        routes=tuple(sorted(routes, key=lambda item: (item.repo_id, item.http_method, item.normalized_path))),
        by_method_path=_freeze_index(by_method_path),
        by_authority_method_path=_freeze_index(by_authority),
        by_service_method_path=_freeze_index(by_service),
        by_property_method_path=_freeze_index(by_property),
    )


def _path_lookup_variants(paths: Iterable[str]) -> tuple[tuple[str, str, int], ...]:
    variants: list[tuple[str, str, int]] = []
    for path in paths:
        variants.append((path, "exact_path", 3))
        segments = [segment for segment in path.split("/") if segment]
        for index in range(1, len(segments)):
            suffix = "/" + "/".join(segments[index:])
            variants.append((suffix, "normalized_path", 2))
    return tuple(dict.fromkeys(variants))


def _index_routes(
    index: Mapping[Any, tuple[_TargetRoute, ...]],
    signals: Iterable[str],
    method: str,
    path_variants: Iterable[tuple[str, str, int]],
    *,
    address_index: bool,
) -> tuple[list[_TargetRoute], int]:
    routes: dict[tuple[str, str, str], _TargetRoute] = {}
    probes = 0
    method_keys = _stable_values((method, "")) if method else ("",)
    signal_values = tuple(signals) if address_index else ("",)
    for signal in signal_values:
        for method_key in method_keys:
            for path, _basis, _rank in path_variants:
                probes += 1
                key = (signal, method_key, path) if address_index else (method_key, path)
                for route in index.get(key, ()):
                    routes[(route.repo_id, route.http_method, route.normalized_path)] = route
    return list(routes.values()), probes


def _target_candidates(outbound: _HttpBoundary, indexes: _TargetIndexes) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    path_variants = _path_lookup_variants(outbound.normalized_paths)
    attempts: list[dict[str, Any]] = []
    pool: list[_TargetRoute] = []
    lookup_basis = "method_path_index"

    lookup_plan = (
        ("authority_index", indexes.by_authority_method_path, outbound.authorities, True),
        ("service_identity_index", indexes.by_service_method_path, outbound.service_identities, True),
        ("base_url_property_index", indexes.by_service_method_path, outbound.property_identities, True),
        ("method_path_index", indexes.by_method_path, ("",), False),
    )
    total_probes = 0
    for basis, index, signals, address_index in lookup_plan:
        if address_index and not tuple(signals):
            continue
        routes, probes = _index_routes(
            index,
            signals,
            outbound.http_method,
            path_variants,
            address_index=address_index,
        )
        total_probes += probes
        routes = [route for route in routes if route.repo_id != outbound.record.repo_id]
        attempts.append({"basis": basis, "candidate_count": len(routes), "probe_count": probes})
        if routes:
            pool = routes
            lookup_basis = basis
            break

    candidates: list[dict[str, Any]] = []
    outbound_environment_authorities = {
        value for value in outbound.authorities if _is_environment_authority(value)
    }
    outbound_authorities = set(outbound.authorities) - outbound_environment_authorities
    environment_identities = {
        identity
        for authority in outbound_environment_authorities
        for identity in _normalize_identity(authority)
    }
    outbound_identities = set(outbound.service_identities) - environment_identities
    outbound_property_identities = set(outbound.property_identities)
    for route in pool:
        exact_paths = sorted(path for path in outbound.normalized_paths if path == route.normalized_path)
        suffix_paths = sorted(
            path for path in outbound.normalized_paths
            if path != route.normalized_path and path.endswith(route.normalized_path)
        )
        if exact_paths:
            path_basis = "exact_path"
            matched_outbound_path = exact_paths[0]
            path_rank = 3
        elif suffix_paths:
            path_basis = "normalized_path"
            matched_outbound_path = suffix_paths[0]
            path_rank = 2
        else:
            continue

        authority_overlap = sorted(outbound_authorities & set(route.authorities))
        service_overlap = sorted(outbound_identities & set(route.service_identities))
        property_overlap = sorted(outbound_property_identities & set(route.service_identities))
        if authority_overlap:
            address_basis = "authority"
            address_rank = 4
        elif service_overlap:
            address_basis = "service_identity"
            address_rank = 3
        elif property_overlap:
            address_basis = "base_url_property"
            address_rank = 2
        else:
            address_basis = "none"
            address_rank = 0

        has_outbound_address = bool(outbound_authorities or outbound_identities)
        has_target_address = bool(route.authorities or route.service_identities)
        address_conflict = bool(has_outbound_address and has_target_address and address_rank == 0)
        contract = _contract_match(outbound.record.payload, route.representative.record.payload)
        if path_basis == "normalized_path" and not (
            address_rank > 0
            or contract["request_field_overlap_count"] > 0
            or contract["request_payload_type_match"]
        ):
            continue
        contract_rank = int(contract["request_field_overlap_count"]) + int(contract["request_payload_type_match"])
        candidates.append(
            {
                "target_route": route,
                "lookup_basis": lookup_basis,
                "path_basis": path_basis,
                "matched_outbound_path": matched_outbound_path,
                "matched_target_path": route.normalized_path,
                "path_rank": path_rank,
                "address_basis": address_basis,
                "address_rank": address_rank,
                "authority_overlap": authority_overlap,
                "service_identity_overlap": service_overlap,
                "property_identity_overlap": property_overlap,
                "address_conflict": address_conflict,
                "contract_rank": contract_rank,
                "contract": contract,
            }
        )
    candidates.sort(
        key=lambda item: (
            item["address_rank"],
            item["path_rank"],
            item["contract_rank"],
            _operation_quality(item["target_route"].representative.record.payload),
            item["target_route"].repo_id,
            item["target_route"].normalized_path,
        ),
        reverse=True,
    )
    lookup = {
        "lookup_basis": lookup_basis,
        "index_probe_count": total_probes,
        "indexed_candidate_count": len(pool),
        "total_target_route_count": len(indexes.routes),
        "attempts": attempts,
        "outbound_authorities": list(outbound.authorities),
        "outbound_environment_authorities": sorted(outbound_environment_authorities),
        "outbound_service_identities": list(outbound.service_identities),
        "outbound_property_identities": list(outbound.property_identities),
        "environment_authority_policy": "non_binding",
    }
    return candidates, lookup


def _candidate_summary(item: Mapping[str, Any]) -> dict[str, Any]:
    route: _TargetRoute = item["target_route"]
    target = route.representative.record
    return {
        "target_repo_id": route.repo_id,
        "target_interface_id": target.interface_id,
        "target_candidate_interface_ids": list(route.candidate_interface_ids),
        "target_operation": target.payload.get("operation"),
        "target_path": route.normalized_path,
        "target_authorities": list(route.authorities),
        "target_service_identities": list(route.service_identities),
        "lookup_basis": item["lookup_basis"],
        "path_basis": item["path_basis"],
        "address_basis": item["address_basis"],
        "authority_overlap": item["authority_overlap"],
        "service_identity_overlap": item["service_identity_overlap"],
        "property_identity_overlap": item["property_identity_overlap"],
        "address_conflict": item["address_conflict"],
        "matched_outbound_path": item["matched_outbound_path"],
        "contract": item["contract"],
    }


def _boundary_inventory_rows(scope_id: str, boundaries: Iterable[_HttpBoundary]) -> list[tuple[Any, ...]]:
    rows: list[tuple[Any, ...]] = []
    for boundary in boundaries:
        record = boundary.record
        boundary_id = stable_id(
            "repository_interaction_boundary",
            scope_id,
            record.repo_id,
            record.interface_id,
            boundary.direction,
            "http",
        )
        provenance = {"interface_record_id": record.record_occurrence_id}
        payload = {
            "schema_version": INTERACTION_GRAPH_SCHEMA_VERSION,
            "boundary_id": boundary_id,
            "repo_id": record.repo_id,
            "system_id": boundary.system_id,
            "project_id": boundary.project_id,
            "configured_service_aliases": list(boundary.configured_service_aliases),
            "interface_id": record.interface_id,
            "direction": boundary.direction,
            "boundary_kind": boundary.boundary_kind,
            "protocol": "http",
            "operation": record.payload.get("operation"),
            "http_method": boundary.http_method or None,
            "normalized_paths": list(boundary.normalized_paths),
            "authorities": list(boundary.authorities),
            "service_identities": list(boundary.service_identities),
            "property_identities": list(boundary.property_identities),
            "base_url_property_keys": list(boundary.base_url_property_keys),
            "contract_fingerprint": boundary.contract_fingerprint,
            "provenance": provenance,
        }
        rows.append(
            (
                boundary_id,
                scope_id,
                record.repo_id,
                boundary.system_id,
                boundary.project_id,
                canonical_json(list(boundary.configured_service_aliases)),
                record.interface_id,
                boundary.direction,
                boundary.boundary_kind,
                "http",
                str(record.payload.get("operation") or "") or None,
                boundary.http_method or None,
                canonical_json(list(boundary.normalized_paths)),
                canonical_json(list(boundary.authorities)),
                canonical_json(list(boundary.service_identities)),
                canonical_json(list(boundary.property_identities)),
                canonical_json(list(boundary.base_url_property_keys)),
                boundary.contract_fingerprint,
                canonical_json(provenance),
                canonical_json(payload),
            )
        )
    return rows


def materialize_system_interactions(connection: Any, *, scope_id: str) -> dict[str, int]:
    """Materialize indexed HTTP boundary matches and optional local execution contexts."""
    connection.execute("DELETE FROM system_interaction_execution_context WHERE scope_id=?", [scope_id])
    connection.execute("DELETE FROM system_boundary_interaction WHERE scope_id=?", [scope_id])
    connection.execute("DELETE FROM system_interaction WHERE scope_id=?", [scope_id])
    connection.execute("DELETE FROM system_interaction_match_diagnostic WHERE scope_id=?", [scope_id])
    connection.execute("DELETE FROM repository_interaction_boundary WHERE scope_id=?", [scope_id])

    interfaces = _load_interfaces(connection)
    repository_identities = _repository_identities(connection)
    observed_http_boundaries = _http_boundaries(interfaces, repository_identities=repository_identities)
    http_boundaries = _compose_shared_outbound_boundaries(observed_http_boundaries)
    target_indexes = _target_indexes(http_boundaries)
    method_graph, call_records = _load_typed_local_call_graph(interfaces)

    inventory_rows = _boundary_inventory_rows(scope_id, http_boundaries)
    bulk_insert(
        connection,
        "INSERT INTO repository_interaction_boundary VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        inventory_rows,
    )

    inbound_by_repo: dict[str, list[_InterfaceRecord]] = defaultdict(list)
    outbound_boundaries: list[_HttpBoundary] = []
    for boundary in http_boundaries:
        if boundary.direction == "inbound":
            inbound_by_repo[boundary.record.repo_id].append(boundary.record)
        elif boundary.direction == "outbound":
            outbound_boundaries.append(boundary)

    boundary_rows: list[tuple[Any, ...]] = []
    execution_context_rows: list[tuple[Any, ...]] = []
    diagnostic_rows: list[tuple[Any, ...]] = []
    seen_boundary_ids: set[str] = set()
    seen_execution_context_ids: set[str] = set()

    for outbound in sorted(outbound_boundaries, key=lambda item: (item.record.repo_id, item.record.interface_id)):
        outbound_record = outbound.record
        candidates, lookup = _target_candidates(outbound, target_indexes)
        eligible = [item for item in candidates if not item["address_conflict"]]
        diagnostic_status = "unresolved"
        diagnostic_reason = "no_indexed_candidate"
        selected: dict[str, Any] | None = None
        if eligible:
            best = eligible[0]
            best_score = (best["address_rank"], best["path_rank"], best["contract_rank"])
            tied = [
                item for item in eligible
                if (item["address_rank"], item["path_rank"], item["contract_rank"]) == best_score
            ]
            unique_targets = {
                (item["target_route"].repo_id, item["target_route"].representative.record.interface_id)
                for item in tied
            }
            if len(unique_targets) == 1:
                selected = best
                diagnostic_status = "matched"
                diagnostic_reason = best["address_basis"] if best["address_rank"] else "unique_indexed_route"
            else:
                diagnostic_status = "ambiguous"
                diagnostic_reason = "multiple_equally_ranked_targets"
        elif candidates and all(item["address_conflict"] for item in candidates):
            diagnostic_reason = "outbound_address_conflicts_with_all_candidates"

        source_paths: list[tuple[_InterfaceRecord, list[str]]] = []
        if selected is not None:
            graph = method_graph.get(outbound_record.repo_id, {})
            target_operation = str(outbound_record.payload.get("operation") or "").strip()
            for source_interface in sorted(inbound_by_repo.get(outbound_record.repo_id, ()), key=lambda item: item.interface_id):
                source_operation = str(source_interface.payload.get("operation") or "").strip()
                call_path = _shortest_call_path(graph, source_operation, target_operation)
                if call_path:
                    source_paths.append((source_interface, call_path))

        candidate_summaries = [_candidate_summary(item) for item in candidates]
        diagnostic_id = stable_id(
            "system_interaction_match_diagnostic",
            scope_id,
            outbound_record.repo_id,
            outbound_record.interface_id,
        )
        diagnostic_confidence = None
        if selected is not None:
            diagnostic_confidence = "confirmed" if selected["address_rank"] >= 3 else "probable"
        diagnostic_payload = {
            "schema_version": INTERACTION_GRAPH_SCHEMA_VERSION,
            "outbound_interface": outbound_record.payload,
            "outbound_boundary": {
                "authorities": list(outbound.authorities),
                "service_identities": list(outbound.service_identities),
                "property_identities": list(outbound.property_identities),
                "normalized_paths": list(outbound.normalized_paths),
            },
            "candidate_lookup": lookup,
            "candidate_matches": candidate_summaries,
            "match_reason": diagnostic_reason,
            "confidence": diagnostic_confidence,
            "local_execution_status": "resolved" if source_paths else "unresolved",
        }
        diagnostic_rows.append(
            (
                diagnostic_id,
                scope_id,
                outbound_record.repo_id,
                outbound_record.interface_id,
                str(outbound_record.payload.get("operation") or "") or None,
                str(outbound_record.payload.get("protocol") or "http") or "http",
                outbound.http_method or None,
                canonical_json(list(outbound.normalized_paths)),
                diagnostic_status,
                diagnostic_confidence,
                canonical_json(candidate_summaries),
                canonical_json(diagnostic_payload),
            )
        )

        if selected is None:
            continue

        route: _TargetRoute = selected["target_route"]
        target_boundary = route.representative
        target = target_boundary.record
        contract = selected["contract"]
        confidence = "confirmed" if selected["address_rank"] >= 3 else "probable"
        local_execution_status = "resolved" if source_paths else "unresolved"
        protocol = str(outbound_record.payload.get("protocol") or "http") or "http"
        system_interaction_id = stable_id(
            "system_interaction",
            scope_id,
            outbound_record.repo_id,
            route.repo_id,
            protocol,
        )
        boundary_id = stable_id(
            "system_boundary_interaction",
            scope_id,
            outbound_record.repo_id,
            outbound_record.interface_id,
            route.repo_id,
            target.interface_id,
            route.normalized_path,
        )
        if boundary_id in seen_boundary_ids:
            continue
        seen_boundary_ids.add(boundary_id)

        match_basis = {
            "candidate_lookup": lookup,
            "http_method": outbound.http_method,
            "lookup_basis": selected["lookup_basis"],
            "path_basis": selected["path_basis"],
            "address_basis": selected["address_basis"],
            "outbound_authorities": list(outbound.authorities),
            "outbound_environment_authorities": lookup["outbound_environment_authorities"],
            "outbound_service_identities": list(outbound.service_identities),
            "outbound_property_identities": list(outbound.property_identities),
            "target_authorities": list(route.authorities),
            "target_service_identities": list(route.service_identities),
            "authority_overlap": selected["authority_overlap"],
            "service_identity_overlap": selected["service_identity_overlap"],
            "property_identity_overlap": selected["property_identity_overlap"],
            "outbound_path": selected["matched_outbound_path"],
            "target_path": selected["matched_target_path"],
            "contract": contract,
        }
        outbound_record_ids = _stable_values(
            [outbound_record.record_occurrence_id, *_values(outbound_record.payload, "observed_interface_record_ids")]
        )
        outbound_interface_ids = _stable_values(
            [outbound_record.interface_id, *_values(outbound_record.payload, "observed_interface_ids")]
        )
        provenance = {
            "outbound_interface_record_id": outbound_record.record_occurrence_id,
            "outbound_interface_record_ids": list(outbound_record_ids),
            "outbound_interface_ids": list(outbound_interface_ids),
            "target_ingress_record_id": target.record_occurrence_id,
            "target_candidate_interface_ids": list(route.candidate_interface_ids),
        }
        payload = {
            "schema_version": INTERACTION_GRAPH_SCHEMA_VERSION,
            "boundary_interaction_id": boundary_id,
            "outbound_interface": outbound_record.payload,
            "target_ingress_interface": target.payload,
            "match_status": "matched",
            "confidence": confidence,
            "local_execution_status": local_execution_status,
            "match_basis": match_basis,
            "provenance": provenance,
        }
        boundary_rows.append(
            (
                boundary_id,
                system_interaction_id,
                scope_id,
                outbound_record.repo_id,
                outbound_record.interface_id,
                str(outbound_record.payload.get("operation") or "") or None,
                outbound.http_method or None,
                selected["matched_outbound_path"],
                route.repo_id,
                target.interface_id,
                str(target.payload.get("operation") or "") or None,
                selected["matched_target_path"],
                protocol,
                "matched",
                confidence,
                local_execution_status,
                canonical_json(match_basis),
                canonical_json(provenance),
                canonical_json(payload),
            )
        )

        for source_interface, call_path in source_paths:
            execution_context_id = stable_id(
                "system_interaction_execution_context",
                boundary_id,
                source_interface.interface_id,
                *call_path,
            )
            if execution_context_id in seen_execution_context_ids:
                continue
            seen_execution_context_ids.add(execution_context_id)
            call_record_ids = _stable_values(
                record_id
                for caller, callee in zip(call_path, call_path[1:])
                for record_id in call_records.get((outbound_record.repo_id, caller, callee), ())
            )
            context_provenance = {
                "source_ingress_record_id": source_interface.record_occurrence_id,
                "outbound_interface_record_id": outbound_record.record_occurrence_id,
                "outbound_interface_record_ids": list(
                    _stable_values(
                        [outbound_record.record_occurrence_id, *_values(outbound_record.payload, "observed_interface_record_ids")]
                    )
                ),
                "call_chain_evidence_record_ids": list(call_record_ids),
                "call_chain_basis": "typed_interaction_boundary_local_call_chain_candidates",
            }
            context_payload = {
                "schema_version": INTERACTION_GRAPH_SCHEMA_VERSION,
                "execution_context_id": execution_context_id,
                "boundary_interaction_id": boundary_id,
                "trigger_kind": "rest_request",
                "source_ingress_interface": source_interface.payload,
                "outbound_interface": outbound_record.payload,
                "call_chain": call_path,
                "provenance": context_provenance,
            }
            execution_context_rows.append(
                (
                    execution_context_id,
                    boundary_id,
                    system_interaction_id,
                    scope_id,
                    outbound_record.repo_id,
                    source_interface.interface_id,
                    str(source_interface.payload.get("operation") or "") or None,
                    next(iter(_interface_paths(source_interface.payload, inbound=True)), None),
                    outbound_record.interface_id,
                    str(outbound_record.payload.get("operation") or "") or None,
                    "rest_request",
                    "resolved",
                    len(call_path) - 1,
                    canonical_json(call_path),
                    canonical_json(context_provenance),
                    canonical_json(context_payload),
                )
            )

    bulk_insert(
        connection,
        """INSERT INTO system_boundary_interaction VALUES (
               ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?
           )""",
        boundary_rows,
    )
    bulk_insert(
        connection,
        """INSERT INTO system_interaction_execution_context VALUES (
               ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?
           )""",
        execution_context_rows,
    )
    bulk_insert(
        connection,
        """INSERT INTO system_interaction_match_diagnostic VALUES (
               ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?
           )""",
        diagnostic_rows,
    )

    grouped: dict[tuple[str, str, str, str], list[tuple[Any, ...]]] = defaultdict(list)
    for row in boundary_rows:
        grouped[(str(row[1]), str(row[3]), str(row[8]), str(row[12]))].append(row)
    execution_context_counts: dict[str, int] = defaultdict(int)
    for row in execution_context_rows:
        execution_context_counts[str(row[2])] += 1

    interaction_rows: list[tuple[Any, ...]] = []
    for (interaction_id, source_repo_id, target_repo_id, protocol), rows in sorted(grouped.items()):
        confidences = sorted({str(row[14]) for row in rows})
        confidence = "confirmed" if confidences == ["confirmed"] else "probable"
        boundary_ids = sorted(str(row[0]) for row in rows)
        payload = {
            "schema_version": INTERACTION_GRAPH_SCHEMA_VERSION,
            "source_repo_id": source_repo_id,
            "target_repo_id": target_repo_id,
            "protocol": protocol,
            "boundary_interaction_ids": boundary_ids,
            "operation_count": len(rows),
            "execution_context_count": execution_context_counts.get(interaction_id, 0),
            "match_status": "matched",
            "confidence": confidence,
        }
        interaction_rows.append(
            (
                interaction_id,
                scope_id,
                source_repo_id,
                target_repo_id,
                protocol,
                len(rows),
                execution_context_counts.get(interaction_id, 0),
                "matched",
                confidence,
                canonical_json(boundary_ids),
                canonical_json(payload),
            )
        )
    bulk_insert(
        connection,
        "INSERT INTO system_interaction VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        interaction_rows,
    )
    return {
        "repository_interaction_boundary": len(inventory_rows),
        "system_interaction": len(interaction_rows),
        "system_boundary_interaction": len(boundary_rows),
        "system_interaction_execution_context": len(execution_context_rows),
        "system_interaction_match_diagnostic": len(diagnostic_rows),
    }
