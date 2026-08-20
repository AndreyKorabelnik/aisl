from __future__ import annotations

from typing import Any

from ....contracts import REPORT_DATASET_SCHEMA, ReportRequest
from ....files import canonical_json, sha256_text


def build_dataset(request: ReportRequest) -> dict[str, Any]:
    source = request.knowledge_source
    if source is None:
        raise ValueError("observed storage report requires a resolved Knowledge API revision")
    base = f"/api/knowledge/v1/systems/{source.system_id}/storage-usage"
    params = {"revision_id": source.revision_id, "offset": 0, "limit": 500}
    accesses = source.client.get_json(base + "/accesses", params=params)
    gaps = source.client.get_json(base + "/gaps", params=params)
    items = list(accesses.get("items") or ())
    read_items = [item for item in items if item.get("access_kind") == "read"]
    write_items = [item for item in items if item.get("access_kind") == "write"]
    summary = dict(accesses.get("summary") or {})
    dataset: dict[str, Any] = {
        "schema_version": REPORT_DATASET_SCHEMA,
        "profile_id": request.profile_id,
        "request": request.to_dataset_dict(),
        "scope": {
            "kind": str((source.revision.get("execution") or {}).get("scope_kind") or "repository"),
            "id": source.system_id,
            "repository_ids": sorted({str(item.get("repo_id")) for item in items if item.get("repo_id")}),
        },
        "audience_policy": {
            "language": "ru",
            "fact_boundary": "Only observed storage accesses and explicit gaps may be stated as facts.",
        },
        "report_blueprint": {
            "required_sections": [
                "Краткий вывод",
                "Наблюдаемые чтения",
                "Наблюдаемые записи",
                "Неразрешённые обращения и ограничения",
                "Технические доказательства и provenance",
            ]
        },
        "coverage": summary,
        "sections": {
            "summary": summary,
            "reads": read_items,
            "writes": write_items,
            "gaps": list(gaps.get("items") or ()),
            "technical_appendix": {
                "revision_id": source.revision_id,
                "artifact_id": (source.selected_artifact or {}).get("artifact_id"),
                "capabilities": list(source.capabilities),
            },
        },
        "evidence_index": {},
        "interpretation_policy": {
            "storage_target_expression": "An observed expression is not promoted to a resolved physical table.",
            "target_resolution_status": "Unresolved targets remain explicit gaps.",
            "read_write": "Read/write classification comes from Core evidence and is not inferred by Reporting.",
        },
    }
    dataset["dataset_fingerprint"] = sha256_text(canonical_json(dataset))
    return dataset
