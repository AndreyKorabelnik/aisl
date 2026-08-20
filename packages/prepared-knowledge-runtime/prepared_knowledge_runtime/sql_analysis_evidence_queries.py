from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Mapping


def _stable_id(prefix: str, *parts: str) -> str:
    raw = "\x1f".join(parts).encode("utf-8")
    return f"{prefix}_{hashlib.sha256(raw).hexdigest()[:24]}"


class SqlAnalysisEvidenceQuery:
    """Read-only native reader for one published Core ``sql-analysis/v1`` package.

    Physical members are supplied by AISL roles rather than rediscovered through
    producer-local sibling paths, so CAS relocation does not affect product reads.
    """

    def __init__(
        self,
        *,
        manifest_path: str | Path,
        coverage_path: str | Path,
        fact_paths: Mapping[str, str | Path],
    ) -> None:
        self.manifest_path = Path(manifest_path).expanduser().resolve()
        self.coverage_path = Path(coverage_path).expanduser().resolve()
        manifest = json.loads(self.manifest_path.read_text(encoding="utf-8"))
        if not isinstance(manifest, dict):
            raise ValueError("sql-analysis manifest root must be an object")
        if manifest.get("artifact") != "sql_analysis" or manifest.get("schema_version") != "sql-analysis/v1":
            raise ValueError("unsupported sql-analysis observed product manifest")
        self.manifest = manifest
        coverage = json.loads(self.coverage_path.read_text(encoding="utf-8"))
        if not isinstance(coverage, dict) or coverage.get("schema_version") != "sql-analysis/v1":
            raise ValueError("unsupported sql-analysis coverage artifact")
        self.coverage = coverage
        self.fact_specs: dict[str, dict[str, Any]] = {}
        self.fact_paths: dict[str, Path] = {}
        for raw in manifest.get("facts") or ():
            if not isinstance(raw, dict):
                continue
            fact_type = str(raw.get("fact_type") or "")
            id_field = str(raw.get("id_field") or "")
            if not fact_type or not id_field or fact_type in self.fact_specs:
                raise ValueError("sql-analysis manifest contains invalid fact identities")
            supplied = fact_paths.get(fact_type)
            if supplied is None:
                raise ValueError(f"published sql-analysis package is missing fact shard: {fact_type}")
            path = Path(supplied).expanduser().resolve()
            if not path.is_file():
                raise ValueError(f"published sql-analysis fact shard is unavailable: {fact_type}")
            self.fact_specs[fact_type] = dict(raw)
            self.fact_paths[fact_type] = path

    def get_aisl_knowledge_item(self, *, item_kind: str, local_id: str) -> dict[str, Any]:
        fact_type = str(item_kind)
        spec = self.fact_specs.get(fact_type)
        if spec is None:
            return {
                "schema_version": "aisl-item-read-projection/v1",
                "unsupported": True,
                "model_kind": "sql-analysis",
                "supported_item_kinds": sorted(self.fact_specs),
            }
        id_field = str(spec["id_field"])
        matches: list[dict[str, Any]] = []
        with self.fact_paths[fact_type].open("r", encoding="utf-8") as handle:
            for line in handle:
                if not line.strip():
                    continue
                row = json.loads(line)
                if not isinstance(row, dict):
                    raise ValueError(f"sql-analysis shard {fact_type} contains a non-object row")
                if str(row.get(id_field) or "") == str(local_id):
                    matches.append(row)
                    if len(matches) > 1:
                        raise ValueError(f"duplicate observed SQL item identity: {fact_type}/{local_id}")
        if not matches:
            return {"schema_version": "aisl-item-read-projection/v1", "not_found": True}
        item = matches[0]
        source_id = str(item.get("repo_id") or (self.manifest.get("repository") or {}).get("repo_id") or "unknown")
        fragments: list[dict[str, Any]] = []
        evidence: list[dict[str, Any]] = []
        seen_fragments: set[str] = set()
        for ordinal, raw_evidence in enumerate(item.get("evidence") or (), start=1):
            if not isinstance(raw_evidence, dict):
                continue
            path = str(raw_evidence.get("relative_file") or raw_evidence.get("file") or item.get("file") or "").strip()
            if not path:
                continue
            line_start_raw = raw_evidence.get("line_start") or item.get("line_start")
            line_end_raw = raw_evidence.get("line_end") or item.get("line_end") or line_start_raw
            line_start = int(line_start_raw) if line_start_raw else None
            line_end = int(line_end_raw) if line_end_raw else None
            locator = f"repo://{source_id}/{path}"
            if line_start:
                locator += f"#L{line_start}"
                if line_end and line_end != line_start:
                    locator += f"-L{line_end}"
            fragment_id = _stable_id("source_fragment", source_id, path, str(line_start or ""), str(line_end or ""))
            if fragment_id not in seen_fragments:
                fragments.append({
                    "fragment_id": fragment_id,
                    "source_id": source_id,
                    "fragment_kind": "sql_source_location",
                    "locator": locator,
                    "path": path,
                    "line_start": line_start,
                    "line_end": line_end,
                    "extractor": raw_evidence.get("extractor"),
                })
                seen_fragments.add(fragment_id)
            evidence.append({
                "evidence_id": _stable_id("evidence", "sql-analysis", fact_type, str(local_id), fragment_id, str(ordinal)),
                "evidence_kind": "observed_sql_fact",
                "source_fragment_ids": [fragment_id],
                "basis": f"sql-analysis/v1:{fact_type}",
            })
        return {
            "schema_version": "aisl-item-read-projection/v1",
            "model_kind": "sql-analysis",
            "item_kind": fact_type,
            "local_id": local_id,
            "item": item,
            "evidence": evidence,
            "source_fragments": fragments,
            "issues": [],
            "coverage": self.coverage,
        }
