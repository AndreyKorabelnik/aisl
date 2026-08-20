from __future__ import annotations

from typing import Any
from ....contracts import REPORT_DATASET_SCHEMA, ReportRequest
from ....files import canonical_json, sha256_text


def _parameters(focus: tuple[str, ...]) -> dict[str, list[str]]:
    result: dict[str, list[str]] = {}
    for raw in focus:
        key, sep, value = str(raw).partition("=")
        if not sep or not key.strip() or not value.strip():
            raise ValueError("sql-change-analysis focus entries must use key=value")
        result.setdefault(key.strip(), []).append(value.strip())
    return result


def build_dataset(request: ReportRequest) -> dict[str, Any]:
    source = request.knowledge_source
    if source is None:
        raise ValueError("sql change analysis requires a resolved Knowledge API revision")
    required = {"common.sql-field-calculation", "common.sql-target-resolution", "common.sql-attribute-insertion-context", "common.sql-target-column-lineage"}
    missing = sorted(required - set(source.capabilities))
    if missing:
        raise ValueError(f"sql change analysis is missing capabilities: {missing}")
    params = _parameters(request.focus)
    target_relation = (params.get("target_relation") or [""])[0]
    target_column = (params.get("target_column") or [""])[0]
    if not target_relation or not target_column:
        raise ValueError("sql change analysis requires focus target_relation=... and target_column=...")
    repo_id = (params.get("repo_id") or [None])[0]
    base = f"/api/knowledge/v1/systems/{source.system_id}/sql"
    common = {"revision_id": source.revision_id, "repo_id": repo_id}
    calculation = source.client.get_json(base+"/field-calculation", params={**common,"target_relation":target_relation,"target_column":target_column})
    lineage = source.client.get_json(base+"/target-column-lineage", params={**common,"target_relation":target_relation,"target_column":target_column,"include_gaps":True,"max_gaps":500,"offset":0,"limit":500})
    candidates = source.client.get_json(base+"/target-candidates", params={**common,"source_relation":params.get("source_relation", []),"source_column":params.get("source_column", []),"business_entity":params.get("business_entity", []),"limit":20})
    insertion = None
    if params.get("source_relation"):
        insertion = source.client.post_json(base+"/attribute-insertion-context", {"target_relation":target_relation,"repo_id":repo_id,"source_relation_hints":params.get("source_relation", []),"source_column_hints":params.get("source_column", []),"max_results":20}, params={"revision_id":source.revision_id})
    dataset: dict[str, Any] = {
      "schema_version":REPORT_DATASET_SCHEMA,"profile_id":request.profile_id,"request":request.to_dataset_dict(),
      "scope":{"kind":str((source.revision.get("execution") or {}).get("scope_kind") or "repository"),"id":source.system_id,"repository_ids":[repo_id] if repo_id else []},
      "audience_policy":{"language":"ru","fact_boundary":"Only published SQL facts and returned statuses may be stated as facts."},
      "report_blueprint":{"required_sections":["Краткий вывод","Расчёт и происхождение поля","Кандидаты таблицы назначения","Контекст добавления атрибута","Target column lineage","Ограничения и доказательства"]},
      "coverage":{"calculation":calculation.get("coverage_status"),"lineage_gap_count":lineage.get("gap_count",0)},
      "sections":{"summary":{"target_relation":target_relation,"target_column":target_column,"revision_id":source.revision_id},"field_calculation":calculation,"target_candidates":candidates,"attribute_insertion_context":insertion,"target_column_lineage":lineage,"technical_appendix":{"artifact_id":(source.selected_artifact or {}).get("artifact_id"),"capabilities":list(source.capabilities)}},
      "evidence_index":{},
      "interpretation_policy":{"candidate_ranking":"Return ranking and reasons; do not silently replace the selected target.","origins":"Preserve every terminal origin.","lineage_gaps":"Partial and unresolved branches remain explicit."},
    }
    dataset["dataset_fingerprint"] = sha256_text(canonical_json(dataset))
    return dataset
