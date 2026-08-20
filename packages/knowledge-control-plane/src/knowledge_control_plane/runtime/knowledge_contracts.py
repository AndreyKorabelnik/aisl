from __future__ import annotations

import hashlib
import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from knowledge_control_plane.api.generic_v1.models import JobCreateRequest, KnowledgeProfileDefinition


@dataclass(frozen=True, slots=True)
class KnowledgeContractPaths:
    core_evidence_catalog: Path
    knowledge_catalog: Path
    materialization_catalog: Path

    def validate(self) -> "KnowledgeContractPaths":
        expected = {
            self.core_evidence_catalog: "core_evidence_contract_catalog/v1",
            self.knowledge_catalog: "knowledge_catalog/v2",
            self.materialization_catalog: "knowledge_materialization_catalog/v3",
        }
        payloads: dict[Path, dict[str, Any]] = {}
        for path, schema in expected.items():
            if not path.is_file():
                raise FileNotFoundError(f"knowledge contract file is unavailable: {path}")
            payload = json.loads(path.read_text(encoding="utf-8"))
            if payload.get("schema_version") != schema:
                raise ValueError(
                    f"unexpected schema in {path}: {payload.get('schema_version')!r}; expected {schema!r}"
                )
            payloads[path] = payload

        core = payloads[self.core_evidence_catalog]
        knowledge = payloads[self.knowledge_catalog]
        materialization = payloads[self.materialization_catalog]
        source = knowledge.get("source") if isinstance(knowledge.get("source"), dict) else {}

        core_fingerprint = str(core.get("catalog_fingerprint") or "")
        materialization_fingerprint = str(materialization.get("catalog_fingerprint") or "")
        if not core_fingerprint or not materialization_fingerprint:
            raise ValueError("runtime knowledge contract bundle must expose catalog fingerprints")
        if source.get("core_evidence_contract_catalog_fingerprint") != core_fingerprint:
            raise ValueError("bundled Knowledge catalog is incompatible with bundled Core evidence catalog")
        if source.get("klc_materialization_catalog_fingerprint") != materialization_fingerprint:
            raise ValueError("bundled Knowledge catalog is incompatible with bundled KLC materialization catalog")

        return self




def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _validate_bundled_manifest(root: Path, paths: KnowledgeContractPaths) -> None:
    manifest_path = root / "bundle-manifest.json"
    if not manifest_path.is_file():
        raise FileNotFoundError(f"runtime contract bundle manifest is unavailable: {manifest_path}")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest.get("schema_version") != "knowledge_control_plane_runtime_contract_bundle/v2":
        raise ValueError(
            "unexpected runtime contract bundle schema: "
            f"{manifest.get('schema_version')!r}; expected 'knowledge_control_plane_runtime_contract_bundle/v2'"
        )

    payloads = {
        "core_evidence": json.loads(paths.core_evidence_catalog.read_text(encoding="utf-8")),
        "knowledge": json.loads(paths.knowledge_catalog.read_text(encoding="utf-8")),
        "materialization": json.loads(paths.materialization_catalog.read_text(encoding="utf-8")),
    }
    path_map = {
        "core_evidence": paths.core_evidence_catalog,
        "knowledge": paths.knowledge_catalog,
        "materialization": paths.materialization_catalog,
    }
    catalogs = manifest.get("catalogs") if isinstance(manifest.get("catalogs"), dict) else {}
    for name, payload in payloads.items():
        entry = catalogs.get(name) if isinstance(catalogs.get(name), dict) else {}
        if entry.get("file") != path_map[name].name:
            raise ValueError(f"runtime contract bundle manifest has unexpected file for {name}")
        if entry.get("schema_version") != payload.get("schema_version"):
            raise ValueError(f"runtime contract bundle manifest schema mismatch for {name}")
        if entry.get("catalog_fingerprint") != payload.get("catalog_fingerprint"):
            raise ValueError(f"runtime contract bundle manifest fingerprint mismatch for {name}")
        if entry.get("sha256") != _sha256(path_map[name]):
            raise ValueError(f"runtime contract bundle file checksum mismatch for {name}")

    baseline = manifest.get("framework_baseline") if isinstance(manifest.get("framework_baseline"), dict) else {}
    actual_versions = {
        "code_analyzer_core": payloads["core_evidence"].get("core_version"),
        "static_analysis_runner": payloads["knowledge"].get("runner_version"),
        "knowledge_layer_core": payloads["materialization"].get("klc_version"),
    }
    for name, actual in actual_versions.items():
        if baseline.get(name) != actual:
            raise ValueError(
                f"runtime contract bundle baseline mismatch for {name}: "
                f"manifest={baseline.get(name)!r}, catalog={actual!r}"
            )

def _bundled_contract_root() -> Path:
    return Path(__file__).resolve().parents[1] / "resources" / "runtime_contracts"


def discover_knowledge_contract_paths() -> KnowledgeContractPaths:
    """Resolve operational contracts without depending on project validation directories.

    Explicit environment overrides remain available for diagnostics/advanced deployments.
    By default Knowledge Control Plane uses the compact, internally versioned contract bundle shipped
    as normal package data with Knowledge Control Plane itself.
    """
    root = _bundled_contract_root()
    core = Path(os.environ["KNOWLEDGE_CONTROL_PLANE_CORE_EVIDENCE_CATALOG"]).expanduser().resolve() if os.getenv(
        "KNOWLEDGE_CONTROL_PLANE_CORE_EVIDENCE_CATALOG"
    ) else (root / "core-evidence-contract-catalog.json").resolve()
    knowledge = Path(os.environ["KNOWLEDGE_CONTROL_PLANE_KNOWLEDGE_CATALOG"]).expanduser().resolve() if os.getenv(
        "KNOWLEDGE_CONTROL_PLANE_KNOWLEDGE_CATALOG"
    ) else (root / "knowledge-catalog.json").resolve()
    materialization = Path(os.environ["KNOWLEDGE_CONTROL_PLANE_MATERIALIZATION_CATALOG"]).expanduser().resolve() if os.getenv(
        "KNOWLEDGE_CONTROL_PLANE_MATERIALIZATION_CATALOG"
    ) else (root / "knowledge-materialization-catalog.json").resolve()

    paths = KnowledgeContractPaths(
        core_evidence_catalog=core,
        knowledge_catalog=knowledge,
        materialization_catalog=materialization,
    ).validate()
    if not any((
        os.getenv("KNOWLEDGE_CONTROL_PLANE_CORE_EVIDENCE_CATALOG"),
        os.getenv("KNOWLEDGE_CONTROL_PLANE_KNOWLEDGE_CATALOG"),
        os.getenv("KNOWLEDGE_CONTROL_PLANE_MATERIALIZATION_CATALOG"),
    )):
        _validate_bundled_manifest(root, paths)
    return paths


def serialize_knowledge_profile(
    profile: KnowledgeProfileDefinition,
    *,
    scope_id: str,
) -> dict[str, Any]:
    """Serialize one Control-Plane profile into the canonical Runner profile contract."""
    return {
        "schema_version": "knowledge_profile/v2",
        "profile_id": profile.profile_id,
        "title": profile.name,
        "scope": {
            "kind": profile.execution_scope.value,
            "scope_id": scope_id,
        },
        "knowledge": [
            {"knowledge_id": knowledge_id}
            for knowledge_id in profile.knowledge_ids
        ],
        "presentation": {
            "include_coverage": True,
            "include_evidence": True,
            "include_gaps": True,
            "include_technical_details": True,
        },
    }


def build_knowledge_profile_payload(
    *,
    request: JobCreateRequest,
    profile: KnowledgeProfileDefinition,
) -> dict[str, Any]:
    return serialize_knowledge_profile(profile, scope_id=request.target.system_id)
