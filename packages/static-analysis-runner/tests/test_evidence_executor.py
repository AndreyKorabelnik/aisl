from __future__ import annotations

import inspect
import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from conftest import make_executable
from static_analysis_runner import evidence_executor as executor_module
from static_analysis_runner.cli import app
from static_analysis_runner.evidence_executor import (
    compile_core_evidence_request,
    execute_core_evidence_plan,
)
from static_analysis_runner.io_utils import stable_fingerprint, write_json

runner = CliRunner()


def _fingerprinted(payload: dict, field: str) -> dict:
    payload[field] = stable_fingerprint(payload)
    return payload


def _plan(path: Path, *identities: tuple[str, str]) -> Path:
    payload = {
        "schema_version": "knowledge_resolution_plan/v2",
        "profile": {
            "profile_id": "generic-evidence-profile",
            "scope": {"kind": "repository", "scope_id": "repo-a"},
        },
        "technical_plan": {
            "evidence_requirements": [
                {
                    "artifact_kind": kind,
                    "schema_version": version,
                    "producer_kind": "core",
                    "parameters": {},
                    "required_by": ["knowledge-b", "knowledge-a"],
                }
                for kind, version in identities
            ]
        },
    }
    _fingerprinted(payload, "plan_fingerprint")
    write_json(path, payload)
    return path


def _catalog(path: Path, *identities: tuple[str, str], runtime_published: bool = True) -> Path:
    contracts = []
    for index, (kind, version) in enumerate(identities, start=1):
        contracts.append({
            "artifact_kind": kind,
            "schema_version": version,
            "contract_status": "runtime_published" if runtime_published else "defined_not_published",
            "current_state_assessment": {
                "typed_runtime_artifact_published": runtime_published,
            },
            "runtime_publication": {
                "runtime_contract_id": "core_evidence_runtime/v1",
                "producer_analyzer_id": (
                    "java-type-structure-analyzer"
                    if (kind, version) == ("java-type-structure-evidence", "java-type-structure-evidence/v1")
                    else f"analyzer-{index}"
                ),
                "registration_status": "registered" if runtime_published else "not_registered",
            },
        })
    payload = {
        "schema_version": "core_evidence_contract_catalog/v1",
        "core_version": "0.43.27",
        "contracts": contracts,
    }
    _fingerprinted(payload, "catalog_fingerprint")
    write_json(path, payload)
    return path


def _fake_core(path: Path, *, invalid_fingerprint: bool = False) -> Path:
    invalid_literal = "True" if invalid_fingerprint else "False"
    return make_executable(
        path,
        f'''
import hashlib, json, pathlib, sys

def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':')).encode('utf-8')

def fingerprint(value):
    return hashlib.sha256(canonical(value)).hexdigest()

args=sys.argv[1:]
if args == ['version']:
    print('0.43.27')
    raise SystemExit(0)
if not args or args[0] != 'evidence-execute':
    raise SystemExit(2)
request_path=pathlib.Path(args[args.index('--request')+1])
out=pathlib.Path(args[args.index('--output')+1])
repo_id=args[args.index('--repo-id')+1]
request=json.loads(request_path.read_text(encoding='utf-8'))
out.mkdir(parents=True, exist_ok=True)
executions=[]
registrations=[]
for index, requirement in enumerate(request['evidence_requirements'], start=1):
    kind=requirement['artifact_kind']
    version=requirement['schema_version']
    is_java_type_structure=(kind == 'java-type-structure-evidence' and version == 'java-type-structure-evidence/v1')
    analyzer_id='java-type-structure-analyzer' if is_java_type_structure else f'analyzer-{{index}}'
    payload=(
      {{
        'source_units':[],
        'type_declarations':[],
        'field_declarations':[],
        'inheritance_declarations':[],
        'annotation_declarations':[],
        'type_reference_observations':[],
        'enum_constant_declarations':[],
      }}
      if is_java_type_structure
      else {{'records':[{{'index':index}}]}}
    )
    artifact={{
      'contract_version':'core_evidence_artifact_contract/v1',
      'artifact_kind':kind,
      'schema_version':version,
      'producer':{{'component':'code-analyzer-core','analyzer_id':analyzer_id,'analyzer_version':'0.43.27'}},
      'source_snapshot':{{'source_id':repo_id,'revision':None,'fingerprint':'snapshot-'+repo_id,'scope':'repository','file_count':1}},
      'foundation':{{'used':False,'contract_version':None,'fingerprint':None,'sections':[]}},
      'parameters':requirement.get('parameters') or {{}},
      'coverage':{{'coverage_status':'complete','observed_record_count':1}},
      'diagnostics':[],
      'provenance':{{'execution_runtime':'core_evidence_runtime/v1','semantic_routing':'artifact_kind_plus_schema_version'}},
      'payload':payload,
    }}
    content_fp=fingerprint(artifact)
    artifact['content_fingerprint']='invalid' if ({invalid_literal} and index == 1) else content_fp
    artifact['artifact_id']='artifact_'+fingerprint({{'kind':kind,'version':version,'content':artifact['content_fingerprint']}})[:24]
    relative=f'evidence/artifact-{{index}}.json'
    artifact_path=out/relative
    artifact_path.parent.mkdir(parents=True, exist_ok=True)
    artifact_path.write_text(json.dumps(artifact, ensure_ascii=False, sort_keys=True, indent=2)+'\\n', encoding='utf-8')
    execution_id=f'execution-{{index}}'
    executions.append({{
      'analyzer_execution_id':execution_id,
      'analyzer_id':analyzer_id,
      'analyzer_version':'0.43.27',
      'semantic_outputs':[{{'artifact_kind':kind,'schema_version':version}}],
      'source_snapshot_ids':[repo_id],
      'source_snapshot_fingerprints':['snapshot-'+repo_id],
      'parameters':requirement.get('parameters') or {{}},
      'required_by':requirement.get('required_by') or [],
      'status':'completed',
      'artifact_ids':[artifact['artifact_id']],
    }})
    registrations.append({{
      'artifact_id':artifact['artifact_id'],
      'artifact_kind':kind,
      'schema_version':version,
      'contract_version':'core_evidence_artifact_contract/v1',
      'producer_analyzer_execution_id':execution_id,
      'content_fingerprint':artifact['content_fingerprint'],
      'status':'completed',
      'coverage':artifact['coverage'],
      'diagnostics':{{'count':0,'severity_counts':{{}},'code_counts':{{}}}},
      'provenance':{{'source_snapshot':artifact['source_snapshot'],'foundation':artifact['foundation'],'producer':artifact['producer'],'core_artifact_provenance':artifact['provenance'],'required_by':requirement.get('required_by') or []}},
      'location':{{'kind':'file','path':relative,'sha256':hashlib.sha256(artifact_path.read_bytes()).hexdigest(),'bytes':artifact_path.stat().st_size}},
    }})
result={{
  'schema_version':'core_evidence_execution_result/v1',
  'runtime_contract_id':'core_evidence_runtime/v1',
  'producer':{{'component':'code-analyzer-core','version':'0.43.27'}},
  'request_fingerprint':request['request_fingerprint'],
  'source':{{'source_kind':'repository','source_id':repo_id}},
  'source_snapshots':[{{'source_id':repo_id,'fingerprint':'snapshot-'+repo_id}}],
  'analyzer_executions':executions,
  'evidence_artifacts':registrations,
  'status':'completed',
  'diagnostics':[],
  'execution_id':'fake-execution',
}}
result['result_fingerprint']=fingerprint(result)
(out/'core-evidence-execution-result.json').write_text(json.dumps(result, ensure_ascii=False, sort_keys=True, indent=2)+'\\n', encoding='utf-8')
''',
    )


def test_compiler_is_generic_for_multiple_artifact_families(tmp_path: Path) -> None:
    identities = (("alpha-evidence", "alpha-evidence/v1"), ("beta-evidence", "beta-evidence/v2"))
    plan = json.loads(_plan(tmp_path / "plan.json", *identities).read_text())
    catalog = json.loads(_catalog(tmp_path / "catalog.json", *identities).read_text())

    request = compile_core_evidence_request(
        resolution_plan=plan,
        core_evidence_catalog=catalog,
        source_id="repo-a",
    )

    assert request["schema_version"] == "core_evidence_execution_request/v1"
    assert [(item["artifact_kind"], item["schema_version"]) for item in request["evidence_requirements"]] == list(identities)
    assert request["orchestration"]["semantic_routing"] == "artifact_kind_plus_schema_version"
    assert "legacy_fallback" not in request["orchestration"]


def test_executor_registers_every_core_result_without_family_specific_code(tmp_path: Path) -> None:
    identities = (("alpha-evidence", "alpha-evidence/v1"), ("beta-evidence", "beta-evidence/v2"))
    repository = tmp_path / "repo"
    repository.mkdir()
    (repository / "source.txt").write_text("source", encoding="utf-8")

    manifest = execute_core_evidence_plan(
        repository=repository,
        resolution_plan=_plan(tmp_path / "plan.json", *identities),
        core_evidence_catalog=_catalog(tmp_path / "catalog.json", *identities),
        output=tmp_path / "out",
        core_command=str(_fake_core(tmp_path / "fake-core")),
        replace=True,
    )

    assert manifest["status"] == "completed"
    assert len(manifest["analyzer_executions"]) == 2
    assert {(item["artifact_kind"], item["schema_version"]) for item in manifest["evidence_artifacts"]} == set(identities)
    assert all(item["semantic_identity"] == {"artifact_kind": item["artifact_kind"], "schema_version": item["schema_version"]} for item in manifest["evidence_artifacts"])
    assert "legacy_fallback" not in manifest["semantic_policy"]
    assert "dual_write" not in manifest["semantic_policy"]
    assert (tmp_path / "out/repository_analysis_run_manifest.json").is_file()


def test_invalid_artifact_fingerprint_fails_explicitly(tmp_path: Path) -> None:
    identity = ("alpha-evidence", "alpha-evidence/v1")
    repository = tmp_path / "repo"
    repository.mkdir()
    with pytest.raises(RuntimeError, match="content_fingerprint is invalid"):
        execute_core_evidence_plan(
            repository=repository,
            resolution_plan=_plan(tmp_path / "plan.json", identity),
            core_evidence_catalog=_catalog(tmp_path / "catalog.json", identity),
            output=tmp_path / "out",
            core_command=str(_fake_core(tmp_path / "fake-core", invalid_fingerprint=True)),
            replace=True,
        )
    summary = json.loads((tmp_path / "out/repository_analysis_run_summary.json").read_text())
    assert summary["status"] == "failed"


def test_unpublished_or_missing_contract_fails_before_core_execution(tmp_path: Path) -> None:
    identity = ("alpha-evidence", "alpha-evidence/v1")
    plan = json.loads(_plan(tmp_path / "plan.json", identity).read_text())
    unpublished = json.loads(_catalog(tmp_path / "catalog.json", identity, runtime_published=False).read_text())
    with pytest.raises(ValueError, match="not runtime-published"):
        compile_core_evidence_request(resolution_plan=plan, core_evidence_catalog=unpublished, source_id="repo-a")

    empty = json.loads(_catalog(tmp_path / "empty.json").read_text())
    with pytest.raises(ValueError, match="not available"):
        compile_core_evidence_request(resolution_plan=plan, core_evidence_catalog=empty, source_id="repo-a")


def test_cli_executes_generic_evidence_plan(tmp_path: Path) -> None:
    identity = ("alpha-evidence", "alpha-evidence/v1")
    repository = tmp_path / "repo"
    repository.mkdir()
    result = runner.invoke(app, [
        "evidence-execute",
        "--repository", str(repository),
        "--resolution-plan", str(_plan(tmp_path / "plan.json", identity)),
        "--core-evidence-catalog", str(_catalog(tmp_path / "catalog.json", identity)),
        "--output", str(tmp_path / "out"),
        "--core-command", str(_fake_core(tmp_path / "fake-core")),
        "--replace",
    ])
    assert result.exit_code == 0, result.output
    summary = json.loads(result.stdout)
    assert summary["status"] == "completed"
    assert summary["evidence_artifact_count"] == 1


def test_executor_source_contains_no_concrete_evidence_or_knowledge_identity() -> None:
    source = inspect.getsource(executor_module)
    assert "java-type-structure" not in source
    assert "code-declared-data-model" not in source
    assert "if artifact_kind ==" not in source
    assert "if knowledge_id" not in source
