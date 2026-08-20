from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable
from collections import Counter
import hashlib
import json
import re
import xml.etree.ElementTree as ET

from code_analyzer_core import __version__ as CORE_VERSION

A = "{attribute}"
C = "{collection}"
O = "{object}"
ARTIFACT_SCHEMA_VERSION = "physical-model/v1"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _stable_id(kind: str, *parts: object) -> str:
    raw = "\x1f".join(str(part or "") for part in parts)
    return f"{kind}_{hashlib.sha256(raw.encode('utf-8')).hexdigest()[:20]}"


def _text(element: ET.Element | None, name: str) -> str | None:
    if element is None:
        return None
    value = element.findtext(f"{A}{name}")
    if value is None:
        return None
    value = value.strip()
    return value or None


def _ref(element: ET.Element | None, collection_name: str, object_name: str) -> str | None:
    if element is None:
        return None
    ref = element.find(f"{C}{collection_name}/{O}{object_name}")
    return ref.attrib.get("Ref") if ref is not None else None


def _bool_text(value: str | None) -> bool | None:
    if value is None:
        return None
    normalized = value.strip().lower()
    if normalized in {"1", "true", "yes", "y"}:
        return True
    if normalized in {"0", "false", "no", "n"}:
        return False
    return None


def _int_text(value: str | None) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _package_records(container: ET.Element, parent_names: tuple[str, ...] = (), parent_codes: tuple[str, ...] = ()) -> Iterable[tuple[ET.Element, tuple[str, ...], tuple[str, ...]]]:
    tables = container.find(f"{C}Tables")
    if tables is not None:
        for table in tables.findall(f"{O}Table"):
            if table.attrib.get("Id"):
                yield table, parent_names, parent_codes
    packages = container.find(f"{C}Packages")
    if packages is not None:
        for package in packages.findall(f"{O}Package"):
            if not package.attrib.get("Id"):
                continue
            name = _text(package, "Name") or ""
            code = _text(package, "Code") or name
            yield from _package_records(
                package,
                parent_names + ((name,) if name else ()),
                parent_codes + ((code,) if code else ()),
            )


def _processing_instruction_metadata(path: Path) -> dict[str, str]:
    with path.open("r", encoding="utf-8", errors="replace") as handle:
        prefix = "".join(handle.readline() for _ in range(4))
    match = re.search(r"<\?PowerDesigner\s+(.*?)\?>", prefix, re.DOTALL)
    if not match:
        return {}
    return {key: value for key, value in re.findall(r'(\w+)="([^"]*)"', match.group(1))}


@dataclass(frozen=True)
class PhysicalModelArtifact:
    output_dir: Path
    manifest_path: Path
    metadata_path: Path
    counts: dict[str, int]
    content_fingerprint: str


def build_physical_model_artifact(
    *,
    model_path: Path,
    output_dir: Path,
    source_id: str | None = None,
) -> PhysicalModelArtifact:
    model_path = Path(model_path).expanduser().resolve()
    output_dir = Path(output_dir).expanduser().resolve()
    if not model_path.is_file():
        raise FileNotFoundError(model_path)
    output_dir.mkdir(parents=True, exist_ok=True)
    facts_dir = output_dir / "facts"
    facts_dir.mkdir(parents=True, exist_ok=True)

    source_sha256 = _sha256_file(model_path)
    resolved_source_id = source_id or f"physical_model_{source_sha256[:16]}"
    tree = ET.parse(model_path)
    root = tree.getroot()
    model = root.find(f".//{O}Model[@Id]")
    if model is None:
        raise ValueError("PDM_MODEL_NOT_FOUND")

    pi_metadata = _processing_instruction_metadata(model_path)
    model_name = _text(model, "Name")
    model_code = _text(model, "Code")
    source_metadata = {
        "physical_model_source_id": resolved_source_id,
        "schema_version": ARTIFACT_SCHEMA_VERSION,
        "core_version": CORE_VERSION,
        "source_file": model_path.name,
        "source_sha256": source_sha256,
        "model_object_id": _text(model, "ObjectID"),
        "model_name": model_name,
        "model_code": model_code,
        "model_creation_timestamp": _int_text(_text(model, "CreationDate")),
        "model_modification_timestamp": _int_text(_text(model, "ModificationDate")),
        "powerdesigner_version": pi_metadata.get("version"),
        "powerdesigner_target": pi_metadata.get("Target"),
        "powerdesigner_signature": pi_metadata.get("signature"),
        "extracted_at": _now(),
    }

    tables: list[dict[str, Any]] = []
    columns: list[dict[str, Any]] = []
    keys: list[dict[str, Any]] = []
    relationships: list[dict[str, Any]] = []
    gaps: list[dict[str, Any]] = []

    table_by_pdm_id: dict[str, dict[str, Any]] = {}
    column_by_pdm_id: dict[str, dict[str, Any]] = {}
    key_by_pdm_id: dict[str, dict[str, Any]] = {}
    primary_key_refs: set[str] = set()

    for table, package_names, package_codes in _package_records(model):
        pdm_table_id = table.attrib["Id"]
        table_code = _text(table, "Code")
        table_name = _text(table, "Name")
        table_identity = ".".join((*package_codes, table_code or table_name or pdm_table_id))
        table_id = _stable_id("physical_model_table", resolved_source_id, pdm_table_id)
        table_fact = {
            "physical_model_table_id": table_id,
            "physical_model_source_id": resolved_source_id,
            "pdm_object_id": pdm_table_id,
            "object_uuid": _text(table, "ObjectID"),
            "model_name": model_name,
            "model_code": model_code,
            "package_path": list(package_names),
            "package_code_path": list(package_codes),
            "table_name": table_name,
            "table_code": table_code,
            "logical_identity": table_identity,
            "comment": _text(table, "Comment"),
            "description": _text(table, "Description"),
            "stereotype": _text(table, "Stereotype"),
            "dimensional_type": _text(table, "DimensionalType"),
            "owner_ref": _ref(table, "Owner", "User"),
            "column_count": 0,
            "key_count": 0,
            "source_file": model_path.name,
            "evidence": {"file": model_path.name, "pdm_object_id": pdm_table_id},
        }
        table_by_pdm_id[pdm_table_id] = table_fact
        tables.append(table_fact)

        column_collection = table.find(f"{C}Columns")
        if column_collection is not None:
            for ordinal, column in enumerate(column_collection.findall(f"{O}Column"), 1):
                pdm_column_id = column.attrib.get("Id")
                if not pdm_column_id:
                    continue
                column_code = _text(column, "Code")
                column_name = _text(column, "Name")
                column_id = _stable_id("physical_model_column", resolved_source_id, pdm_column_id)
                column_fact = {
                    "physical_model_column_id": column_id,
                    "physical_model_table_id": table_id,
                    "physical_model_source_id": resolved_source_id,
                    "pdm_object_id": pdm_column_id,
                    "object_uuid": _text(column, "ObjectID"),
                    "ordinal": ordinal,
                    "column_name": column_name,
                    "column_code": column_code,
                    "data_type": _text(column, "DataType"),
                    "length": _int_text(_text(column, "Length")),
                    "precision": _int_text(_text(column, "Precision")),
                    "mandatory": _bool_text(_text(column, "Column.Mandatory")),
                    "default_value": _text(column, "DefaultValue"),
                    "comment": _text(column, "Comment"),
                    "domain_ref": _ref(column, "Domain", "PhysicalDomain"),
                    "source_file": model_path.name,
                    "evidence": {"file": model_path.name, "pdm_object_id": pdm_column_id},
                }
                columns.append(column_fact)
                column_by_pdm_id[pdm_column_id] = column_fact
        table_fact["column_count"] = sum(1 for item in columns if item["physical_model_table_id"] == table_id)

        primary_key_collection = table.find(f"{C}PrimaryKey")
        if primary_key_collection is not None:
            for ref in primary_key_collection.findall(f"{O}Key"):
                if ref.attrib.get("Ref"):
                    primary_key_refs.add(ref.attrib["Ref"])

        key_collection = table.find(f"{C}Keys")
        if key_collection is not None:
            for key in key_collection.findall(f"{O}Key"):
                pdm_key_id = key.attrib.get("Id")
                if not pdm_key_id:
                    continue
                key_columns: list[str] = []
                key_column_codes: list[str] = []
                unresolved_column_refs: list[str] = []
                collection = key.find(f"{C}Key.Columns")
                if collection is not None:
                    for column_ref in collection.findall(f"{O}Column"):
                        ref_id = column_ref.attrib.get("Ref")
                        if not ref_id:
                            continue
                        key_columns.append(ref_id)
                        resolved_column = column_by_pdm_id.get(ref_id)
                        if resolved_column:
                            if resolved_column.get("column_code"):
                                key_column_codes.append(str(resolved_column["column_code"]))
                        else:
                            unresolved_column_refs.append(ref_id)
                key_id = _stable_id("physical_model_key", resolved_source_id, pdm_key_id)
                key_fact = {
                    "physical_model_key_id": key_id,
                    "physical_model_table_id": table_id,
                    "physical_model_source_id": resolved_source_id,
                    "pdm_object_id": pdm_key_id,
                    "object_uuid": _text(key, "ObjectID"),
                    "key_name": _text(key, "Name"),
                    "key_code": _text(key, "Code"),
                    "key_kind": "primary" if pdm_key_id in primary_key_refs else "alternate",
                    "column_pdm_ids": key_columns,
                    "column_codes": key_column_codes,
                    "unresolved_column_refs": unresolved_column_refs,
                    "source_file": model_path.name,
                    "evidence": {"file": model_path.name, "pdm_object_id": pdm_key_id},
                }
                keys.append(key_fact)
                key_by_pdm_id[pdm_key_id] = key_fact
                for missing_ref in unresolved_column_refs:
                    gaps.append({
                        "physical_model_gap_id": _stable_id("physical_model_gap", resolved_source_id, "key_column_unresolved", pdm_key_id, missing_ref),
                        "physical_model_source_id": resolved_source_id,
                        "gap_kind": "key_column_unresolved",
                        "owner_pdm_object_id": pdm_key_id,
                        "unresolved_ref": missing_ref,
                        "message": "Key references a column definition that was not found",
                    })
        table_fact["key_count"] = sum(1 for item in keys if item["physical_model_table_id"] == table_id)

    # Primary key refs are encountered before/while key definitions are built; normalize now.
    for key_fact in keys:
        if key_fact["pdm_object_id"] in primary_key_refs:
            key_fact["key_kind"] = "primary"

    for reference in root.findall(f".//{O}Reference[@Id]"):
        pdm_reference_id = reference.attrib["Id"]
        parent_ref = _ref(reference, "ParentTable", "Table")
        child_ref = _ref(reference, "ChildTable", "Table")
        parent = table_by_pdm_id.get(parent_ref or "")
        child = table_by_pdm_id.get(child_ref or "")
        parent_key_ref = _ref(reference, "ParentKey", "Key")
        joins: list[dict[str, Any]] = []
        unresolved_join_refs: list[str] = []
        joins_collection = reference.find(f"{C}Joins")
        if joins_collection is not None:
            for join in joins_collection.findall(f"{O}ReferenceJoin"):
                parent_column_ref = _ref(join, "Object1", "Column")
                child_column_ref = _ref(join, "Object2", "Column")
                parent_column = column_by_pdm_id.get(parent_column_ref or "")
                child_column = column_by_pdm_id.get(child_column_ref or "")
                joins.append({
                    "pdm_reference_join_id": join.attrib.get("Id"),
                    "parent_column_ref": parent_column_ref,
                    "parent_column_code": parent_column.get("column_code") if parent_column else None,
                    "child_column_ref": child_column_ref,
                    "child_column_code": child_column.get("column_code") if child_column else None,
                })
                if parent_column_ref and not parent_column:
                    unresolved_join_refs.append(parent_column_ref)
                if child_column_ref and not child_column:
                    unresolved_join_refs.append(child_column_ref)
        relationship_fact = {
            "physical_model_relationship_id": _stable_id("physical_model_relationship", resolved_source_id, pdm_reference_id),
            "physical_model_source_id": resolved_source_id,
            "pdm_object_id": pdm_reference_id,
            "object_uuid": _text(reference, "ObjectID"),
            "relationship_name": _text(reference, "Name"),
            "relationship_code": _text(reference, "Code"),
            "cardinality": _text(reference, "Cardinality"),
            "parent_table_ref": parent_ref,
            "parent_table_id": parent.get("physical_model_table_id") if parent else None,
            "parent_table_code": parent.get("table_code") if parent else None,
            "child_table_ref": child_ref,
            "child_table_id": child.get("physical_model_table_id") if child else None,
            "child_table_code": child.get("table_code") if child else None,
            "parent_key_ref": parent_key_ref,
            "parent_key_id": key_by_pdm_id.get(parent_key_ref or "", {}).get("physical_model_key_id"),
            "joins": joins,
            "resolution_status": "resolved" if parent and child and not unresolved_join_refs else "partial",
            "source_file": model_path.name,
            "evidence": {"file": model_path.name, "pdm_object_id": pdm_reference_id},
        }
        relationships.append(relationship_fact)
        for missing_ref in [ref for ref in (parent_ref, child_ref, parent_key_ref, *unresolved_join_refs) if ref and ref not in table_by_pdm_id and ref not in key_by_pdm_id and ref not in column_by_pdm_id]:
            gaps.append({
                "physical_model_gap_id": _stable_id("physical_model_gap", resolved_source_id, "relationship_ref_unresolved", pdm_reference_id, missing_ref),
                "physical_model_source_id": resolved_source_id,
                "gap_kind": "relationship_ref_unresolved",
                "owner_pdm_object_id": pdm_reference_id,
                "unresolved_ref": missing_ref,
                "message": "Relationship references an object definition that was not found",
            })

    fact_sets: list[tuple[str, str, list[dict[str, Any]]]] = [
        ("physical_model_table", "physical_model_table_id", tables),
        ("physical_model_column", "physical_model_column_id", columns),
        ("physical_model_key", "physical_model_key_id", keys),
        ("physical_model_relationship", "physical_model_relationship_id", relationships),
        ("physical_model_gap", "physical_model_gap_id", gaps),
    ]
    manifest_facts: list[dict[str, Any]] = []
    fingerprint = hashlib.sha256()
    for fact_type, id_field, records in fact_sets:
        identifiers = [str(record.get(id_field) or "") for record in records]
        duplicate_ids = sorted(identifier for identifier, count in Counter(identifiers).items() if count > 1)
        if duplicate_ids:
            raise ValueError(f"DUPLICATE_PHYSICAL_MODEL_FACT_IDS: {fact_type}: {duplicate_ids[:10]}")
        path = facts_dir / f"{fact_type}.jsonl"
        with path.open("w", encoding="utf-8", newline="\n") as handle:
            for record in records:
                line = json.dumps(record, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
                handle.write(line + "\n")
                fingerprint.update(fact_type.encode("utf-8"))
                fingerprint.update(b"\0")
                fingerprint.update(line.encode("utf-8"))
                fingerprint.update(b"\n")
        manifest_facts.append({
            "fact_type": fact_type,
            "id_field": id_field,
            "path": f"facts/{path.name}",
            "record_count": len(records),
            "size_bytes": path.stat().st_size,
            "sha256": _sha256_file(path),
        })

    metadata_path = output_dir / "metadata.json"
    metadata_path.write_text(json.dumps(source_metadata, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    counts = {fact_type: len(records) for fact_type, _, records in fact_sets}
    content_fingerprint = fingerprint.hexdigest()
    manifest = {
        "schema_version": ARTIFACT_SCHEMA_VERSION,
        "physical_model_source_id": resolved_source_id,
        "core_version": CORE_VERSION,
        "created_at": _now(),
        "content_fingerprint": content_fingerprint,
        "source": {
            "file": model_path.name,
            "sha256": source_sha256,
            "metadata_path": "metadata.json",
        },
        "counts": counts,
        "facts": manifest_facts,
        "coverage": {
            "status": "complete" if not gaps else "partial",
            "gap_count": len(gaps),
        },
    }
    manifest_path = output_dir / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return PhysicalModelArtifact(
        output_dir=output_dir,
        manifest_path=manifest_path,
        metadata_path=metadata_path,
        counts=counts,
        content_fingerprint=content_fingerprint,
    )
