import json
from pathlib import Path
from copy import deepcopy
import hashlib

from code_analyzer_core.prepared_artifacts.sql_analysis_evidence import build_sql_analysis_evidence
from knowledge_layer_core.materialization_runtime import materialize, registered_materialization_ids


def test_sql_generic_envelope_materializes_without_runner_special_case(tmp_path: Path) -> None:
    repo=tmp_path/"repo"; repo.mkdir(); sql=repo/"load.sql"; sql.write_text("insert into dm.customer select id from src.customer",encoding="utf-8")
    root=tmp_path/"core"
    artifact=build_sql_analysis_evidence(repository=repo,files=[sql],repo_id="sql-repo",output_root=root,parameters={})
    envelope=root/"evidence/sql-analysis-evidence.json"; envelope.parent.mkdir(parents=True,exist_ok=True); envelope.write_text(json.dumps(artifact),encoding="utf-8")
    assert "sql-analysis" in registered_materialization_ids()
    request={"schema_version":"knowledge_materialization_request/v1","materialization_id":"sql-analysis","scope_id":"sql-repo","inputs":{"evidence_artifacts":[{"artifact_id":artifact["artifact_id"],"artifact_kind":"sql-analysis","schema_version":"sql-analysis/v1","content_fingerprint":artifact["content_fingerprint"],"location":{"kind":"file","path":str(envelope)}}],"knowledge_artifacts":[]},"parameters":{}}
    result=materialize(request,tmp_path/"out")
    assert result["status"]=="completed"
    assert "common.sql-analysis" in result["published_capabilities"]
    assert "common.sql-source-inventory-export" in result["published_capabilities"]
