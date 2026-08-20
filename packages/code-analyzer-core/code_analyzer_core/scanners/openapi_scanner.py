from __future__ import annotations

from pathlib import Path
from typing import Any
import json

import yaml

from code_analyzer_core.models import EvidenceRef, Fact, FieldInfo, InterfaceInfo, InterfaceKind, Direction, SchemaInfo

HTTP_METHODS = {"get", "put", "post", "delete", "patch", "options", "head", "trace"}


def _source_set_for_path(path: Path) -> str:
    normalized = str(path).replace("\\", "/")
    if "/src/test/" in normalized or normalized.endswith("/src/test"):
        return "test"
    return "main"


def _load_spec(path: Path) -> dict[str, Any] | None:
    try:
        text = path.read_text(encoding="utf-8", errors="ignore")
    except Exception:
        return None
    if "openapi" not in text.lower() and "swagger" not in text.lower() and "paths:" not in text.lower():
        return None
    try:
        if path.suffix.lower() == ".json":
            data = json.loads(text)
        else:
            data = yaml.safe_load(text)
    except Exception:
        return None
    if not isinstance(data, dict):
        return None
    if not (data.get("openapi") or data.get("swagger") or data.get("paths")):
        return None
    return data


def _schema_ref(schema: Any) -> str | None:
    if not isinstance(schema, dict):
        return None
    ref = schema.get("$ref")
    if isinstance(ref, str) and ref:
        return ref.split("/")[-1]
    if schema.get("type") == "array" and isinstance(schema.get("items"), dict):
        nested = _schema_ref(schema.get("items")) or schema.get("items", {}).get("type")
        return f"List<{nested}>" if nested else "array"
    return schema.get("type") if isinstance(schema.get("type"), str) else None


def _schema_for_media(obj: Any) -> str | None:
    if not isinstance(obj, dict):
        return None
    content = obj.get("content")
    if isinstance(content, dict):
        for media in ["application/json", "application/*+json", "*/*"]:
            body = content.get(media)
            if isinstance(body, dict):
                ref = _schema_ref(body.get("schema"))
                if ref:
                    return ref
        for body in content.values():
            if isinstance(body, dict):
                ref = _schema_ref(body.get("schema"))
                if ref:
                    return ref
    return _schema_ref(obj.get("schema"))


def _parameters(params: Any, location: str | None = None) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    if not isinstance(params, list):
        return out
    for p in params:
        if not isinstance(p, dict):
            continue
        where = p.get("in")
        if location and where != location:
            continue
        schema = p.get("schema") if isinstance(p.get("schema"), dict) else {}
        out.append({
            "name": p.get("name"),
            "java_parameter": p.get("name"),
            "java_type": _schema_ref(schema) or schema.get("type"),
            "source": {"path": "PathVariable", "query": "RequestParam", "header": "RequestHeader"}.get(str(where), f"openapi_{where}"),
            "location": where,
            "required": p.get("required"),
            "description": p.get("description"),
        })
    return out


def _field_from_schema_property(name: str, prop: Any, required: set[str]) -> FieldInfo:
    typ = None
    nested = None
    description = None
    annotations: list[str] = []
    if isinstance(prop, dict):
        typ = _schema_ref(prop) or prop.get("type")
        description = prop.get("description")
        fmt = prop.get("format")
        if fmt:
            annotations.append(f"format:{fmt}")
        if name in required:
            annotations.append("required")
        if prop.get("nullable") is True:
            annotations.append("nullable")
        if prop.get("type") == "array" and isinstance(prop.get("items"), dict):
            nested = _schema_ref(prop.get("items")) or prop.get("items", {}).get("type")
    return FieldInfo(name=name, type=typ, nested_type=nested, description=description, annotations=annotations)


def _component_schemas(spec: dict[str, Any], path: Path) -> list[SchemaInfo]:
    schemas: list[SchemaInfo] = []
    components = spec.get("components") if isinstance(spec.get("components"), dict) else {}
    raw_schemas = components.get("schemas") if isinstance(components.get("schemas"), dict) else {}
    for name, schema in raw_schemas.items():
        if not isinstance(schema, dict):
            continue
        required = set(schema.get("required") or []) if isinstance(schema.get("required"), list) else set()
        props = schema.get("properties") if isinstance(schema.get("properties"), dict) else {}
        fields = [_field_from_schema_property(str(fname), fdef, required) for fname, fdef in props.items()]
        schemas.append(SchemaInfo(
            name=str(name),
            source_type="openapi_schema",
            fields=fields,
            evidence=[EvidenceRef(file_path=str(path), line_start=1, extractor="openapi_schema_scanner")],
            comments=[schema.get("description")] if schema.get("description") else [],
        ))
    return schemas


def scan_openapi_files(files: list[Path]) -> tuple[list[Fact], list[SchemaInfo], list[InterfaceInfo], list[str]]:
    facts: list[Fact] = []
    schemas: list[SchemaInfo] = []
    interfaces: list[InterfaceInfo] = []
    warnings: list[str] = []
    candidates = [p for p in files if p.suffix.lower() in {".yaml", ".yml", ".json"}]
    for path in candidates:
        spec = _load_spec(path)
        if not spec:
            continue
        source_set = _source_set_for_path(path)
        is_test_source = source_set == "test"
        evidence = [EvidenceRef(file_path=str(path), line_start=1, extractor="openapi_scanner")]
        facts.append(Fact(
            fact_type="openapi_contract",
            name=str(path.name),
            properties={
                "source_file": str(path),
                "openapi_version": spec.get("openapi") or spec.get("swagger"),
                "title": ((spec.get("info") or {}).get("title") if isinstance(spec.get("info"), dict) else None),
                "source_set": source_set,
                "is_test_source": is_test_source,
                "evidence_maturity_level": "confirmed",
                "evidence_maturity_dimensions": {"api_contract": "confirmed"},
            },
            evidence=evidence,
        ))
        schemas.extend(_component_schemas(spec, path))
        raw_paths = spec.get("paths") if isinstance(spec.get("paths"), dict) else {}
        for endpoint, path_item in raw_paths.items():
            if not isinstance(path_item, dict):
                continue
            path_params = _parameters(path_item.get("parameters"))
            for method, operation in path_item.items():
                if str(method).lower() not in HTTP_METHODS or not isinstance(operation, dict):
                    continue
                op_params = path_params + _parameters(operation.get("parameters"))
                operation_id = operation.get("operationId") or f"{str(method).upper()} {endpoint}"
                request_schema = _schema_for_media(operation.get("requestBody"))
                common_props = {
                    "boundary_role": "rest_request",
                    "source_set": source_set,
                    "is_test_source": is_test_source,
                    "request_parameters": op_params,
                    "openapi_operation_id": operation_id,
                    "openapi_summary": operation.get("summary"),
                    "openapi_description": operation.get("description"),
                    "syntax_provider": "openapi_contract",
                }
                if request_schema or op_params:
                    interfaces.append(InterfaceInfo(
                        name=f"{str(method).upper()} {endpoint} request",
                        direction=Direction.INBOUND,
                        kind=InterfaceKind.REST,
                        schema_ref=request_schema or "method_parameters",
                        operation=str(operation_id),
                        path=str(endpoint),
                        method=str(method).upper(),
                        evidence=evidence,
                        properties=common_props,
                    ))
                responses = operation.get("responses") if isinstance(operation.get("responses"), dict) else {}
                for code, resp in responses.items():
                    response_schema = _schema_for_media(resp)
                    if not response_schema:
                        continue
                    interfaces.append(InterfaceInfo(
                        name=f"{str(method).upper()} {endpoint} response {code}",
                        direction=Direction.OUTBOUND,
                        kind=InterfaceKind.REST,
                        schema_ref=response_schema,
                        operation=str(operation_id),
                        path=str(endpoint),
                        method=str(method).upper(),
                        evidence=evidence,
                        properties={**common_props, "boundary_role": "rest_response", "response_status": str(code)},
                    ))
    return facts, schemas, interfaces, warnings
