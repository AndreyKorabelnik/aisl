from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any


_SECTION_BY_ITEM_KIND = {
    "source_unit": ("source_units", "source_unit_id"),
    "type_declaration": ("type_declarations", "type_id"),
    "field_declaration": ("field_declarations", "field_id"),
    "inheritance_declaration": ("inheritance_declarations", "inheritance_id"),
    "annotation_declaration": ("annotation_declarations", "annotation_id"),
    "type_reference_observation": ("type_reference_observations", "type_reference_id"),
    "enum_constant_declaration": ("enum_constant_declarations", "enum_constant_id"),
}


def _stable_id(prefix: str, *parts: str) -> str:
    raw = "\x1f".join(parts).encode("utf-8")
    return f"{prefix}_{hashlib.sha256(raw).hexdigest()[:24]}"


class JavaTypeStructureEvidenceQuery:
    """Read-only native reader for Core java-type-structure-evidence/v1."""

    def __init__(self, artifact: str | Path) -> None:
        self.path = Path(artifact).expanduser().resolve()
        payload = json.loads(self.path.read_text(encoding="utf-8"))
        if not isinstance(payload, dict):
            raise ValueError("java type-structure evidence root must be an object")
        if payload.get("artifact_kind") != "java-type-structure-evidence":
            raise ValueError("unexpected Core evidence artifact kind")
        if payload.get("schema_version") != "java-type-structure-evidence/v1":
            raise ValueError("unsupported java type-structure evidence schema")
        self.payload = payload

    def get_aisl_knowledge_item(self, *, item_kind: str, local_id: str) -> dict[str, Any]:
        spec = _SECTION_BY_ITEM_KIND.get(str(item_kind))
        if spec is None:
            return {
                "schema_version": "aisl-item-read-projection/v1",
                "unsupported": True,
                "model_kind": "java-type-structure-evidence",
                "supported_item_kinds": sorted(_SECTION_BY_ITEM_KIND),
            }
        section, id_field = spec
        records = ((self.payload.get("payload") or {}).get(section) or [])
        matches = [dict(row) for row in records if isinstance(row, dict) and str(row.get(id_field) or "") == str(local_id)]
        if not matches:
            return {"schema_version": "aisl-item-read-projection/v1", "not_found": True}
        if len(matches) > 1:
            raise ValueError(f"duplicate observed item identity: {item_kind}/{local_id}")
        item = matches[0]
        source_ref = item.get("source_ref") if isinstance(item.get("source_ref"), dict) else None
        if source_ref is None and item_kind == "source_unit":
            source_ref = {
                "repository_relative_path": item.get("repository_relative_path"),
                "line_start": None,
                "line_end": None,
                "extractor": "java_tree_sitter",
            }
        evidence: list[dict[str, Any]] = []
        fragments: list[dict[str, Any]] = []
        if source_ref and source_ref.get("repository_relative_path"):
            source_id = str((self.payload.get("source_snapshot") or {}).get("source_id") or "unknown")
            rel_path = str(source_ref["repository_relative_path"])
            line_start = source_ref.get("line_start")
            line_end = source_ref.get("line_end")
            locator = f"repo://{source_id}/{rel_path}"
            if line_start:
                locator += f"#L{line_start}"
                if line_end and line_end != line_start:
                    locator += f"-L{line_end}"
            fragment_id = _stable_id("source_fragment", source_id, rel_path, str(line_start or ""), str(line_end or ""))
            evidence_id = _stable_id("evidence", "java-type-structure", item_kind, str(local_id), fragment_id)
            fragments.append({
                "fragment_id": fragment_id,
                "source_id": source_id,
                "fragment_kind": "source_code_location",
                "locator": locator,
                "path": rel_path,
                "line_start": line_start,
                "line_end": line_end,
                "extractor": source_ref.get("extractor"),
            })
            evidence.append({
                "evidence_id": evidence_id,
                "evidence_kind": "observed_source_declaration",
                "source_fragment_ids": [fragment_id],
                "basis": f"java-type-structure-evidence/v1:{section}",
            })
        return {
            "schema_version": "aisl-item-read-projection/v1",
            "model_kind": "java-type-structure-evidence",
            "item_kind": item_kind,
            "local_id": local_id,
            "item": item,
            "evidence": evidence,
            "source_fragments": fragments,
            "issues": [],
            "coverage": dict(self.payload.get("coverage") or {}),
        }
