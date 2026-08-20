from __future__ import annotations

from collections import Counter
from pathlib import Path
import re
from typing import Any, Iterable

from code_analyzer_core.models import EvidenceRef, Fact
from code_analyzer_core.scanners.java_syntax import JavaAnnotation, JavaClass, parse_java_workspace

SCHEMA_VERSION = "data_model_candidate_profile/v1"

_MODEL_PATH_SEGMENTS = {
    "model", "models", "domain", "domains", "entity", "entities",
    "schema", "schemas", "metamodel", "meta-model", "dictionary",
    "dictionaries", "ldm", "pdm",
}
_EXECUTABLE_ANNOTATIONS = {
    "RestController", "Controller", "Service", "Component", "Repository",
    "Configuration", "SpringBootApplication", "KafkaListener",
}
_STRONG_MODEL_ANNOTATIONS = {
    "Entity", "Table", "Document", "Embeddable", "MappedSuperclass",
    "Aggregate", "AggregateRoot", "ValueObject",
}
_RELATION_ANNOTATIONS = {
    "OneToOne", "OneToMany", "ManyToOne", "ManyToMany", "Embedded",
    "EmbeddedId", "ElementCollection", "JoinColumn", "JoinColumns",
}
_SCHEMA_BINDING_ANNOTATIONS = {
    "XmlType", "XmlRootElement", "XmlAccessorType", "XmlRegistry", "XmlEnum",
    "AvroGenerated", "ProtoField", "JsonTypeInfo", "JsonSubTypes",
}
_MODEL_TOOLING_TOKENS = (
    "datamodel", "metamodel", "modelparser", "modelreader", "modelwriter",
    "modelgenerator", "modelcompiler", "modelclass", "modelproperty",
    "schemagenerator", "schemacompiler", "codegenerator",
)
_DECLARATIVE_SCHEMA_SUFFIXES = {".avsc", ".proto", ".xsd", ".graphql", ".graphqls"}
_MIGRATION_PATH_TOKENS = ("liquibase", "flyway", "migration", "migrations", "changelog")
_CREATE_TABLE_RE = re.compile(r"\bcreate\s+table\b", re.IGNORECASE)
_SEGMENT_SPLIT_RE = re.compile(r"[/.\\_-]+")


def _relative(path: Path, root: Path) -> str:
    try:
        return path.resolve().relative_to(root.resolve()).as_posix()
    except Exception:
        return path.name


def _segments(value: str) -> set[str]:
    return {segment.lower() for segment in _SEGMENT_SPLIT_RE.split(value) if segment}


def _is_main_source(path: Path) -> bool:
    text = path.as_posix().lower()
    return not any(token in text for token in ("/src/test/", "/src/it/", "/test/", "/tests/", "/target/", "/build/"))


def _model_annotation_kind(name: str) -> str | None:
    low = name.lower()
    if name in _STRONG_MODEL_ANNOTATIONS:
        return "standard_model_annotation"
    if low.endswith(("entity", "dictionary", "aggregate", "valueobject")):
        return "custom_model_annotation"
    return None


def _relation_annotation(name: str) -> bool:
    low = name.lower()
    return name in _RELATION_ANNOTATIONS or low.endswith(("reference", "relationship"))


def _has_model_path(cls: JavaClass, root: Path) -> bool:
    rel = _relative(cls.file, root)
    return bool((_segments(rel) | _segments(cls.package)) & _MODEL_PATH_SEGMENTS)


def _is_executable_class(cls: JavaClass) -> bool:
    names = {annotation.name for annotation in cls.annotations}
    if names & _EXECUTABLE_ANNOTATIONS:
        return True
    low = cls.name.lower()
    return low.endswith(("controller", "service", "consumer", "listener", "configuration", "application"))


def _is_model_tooling_class(cls: JavaClass) -> bool:
    identity = f"{cls.package}.{cls.name}".lower().replace("_", "")
    if any(token in identity for token in _MODEL_TOOLING_TOKENS):
        return True
    annotations = {annotation.name for annotation in cls.annotations}
    return "Mojo" in annotations and any(token in identity for token in ("model", "schema", "meta"))


def _evidence(kind: str, path: Path, root: Path, *, symbol: str | None = None,
              line_start: int | None = None, line_end: int | None = None,
              annotation: str | None = None, detail: str | None = None) -> dict[str, Any]:
    item: dict[str, Any] = {
        "kind": kind,
        "path": _relative(path, root),
    }
    if symbol:
        item["symbol"] = symbol
    if line_start is not None:
        item["line_start"] = int(line_start)
    if line_end is not None:
        item["line_end"] = int(line_end)
    if annotation:
        item["annotation"] = annotation
    if detail:
        item["detail"] = detail
    return item


def _bounded_append(items: list[dict[str, Any]], item: dict[str, Any], *, limit: int = 40) -> None:
    if len(items) < limit:
        items.append(item)


def _score(signals: dict[str, Any]) -> tuple[int, list[dict[str, Any]]]:
    score = 0
    components: list[dict[str, Any]] = []

    def add(component: str, points: int, basis: str) -> None:
        nonlocal score
        if points:
            score += points
            components.append({"component": component, "points": points, "basis": basis})

    annotated = int(signals["annotated_model_type_count"])
    if annotated >= 20:
        add("model_annotations", 40, f"{annotated} classes use standard or custom model annotations")
    elif annotated >= 5:
        add("model_annotations", 30, f"{annotated} classes use standard or custom model annotations")
    elif annotated >= 1:
        add("model_annotations", 15, f"{annotated} class uses a standard or custom model annotation")

    model_types = int(signals["model_path_type_count"])
    class_count = max(1, int(signals["java_class_count"]))
    model_ratio = float(signals["model_path_type_ratio"])
    if model_types >= 20 and model_ratio >= 0.50:
        add("model_path_concentration", 25, f"{model_types}/{class_count} classes are in model-oriented paths")
    elif model_types >= 5 and model_ratio >= 0.50:
        add("model_path_concentration", 15, f"{model_types}/{class_count} classes are in model-oriented paths")
    elif model_types >= 10 and model_ratio >= 0.20:
        add("model_path_concentration", 15, f"{model_types}/{class_count} classes are in model-oriented paths")
    elif model_types >= 5 and model_ratio >= 0.05:
        add("model_path_concentration", 8, f"{model_types}/{class_count} classes are in model-oriented paths")

    tooling = int(signals["model_tooling_type_count"])
    if tooling >= 10:
        add("model_tooling", 30, f"{tooling} model parser/generator/compiler classes observed")
    elif tooling >= 3:
        add("model_tooling", 20, f"{tooling} model parser/generator/compiler classes observed")
    elif tooling >= 1:
        add("model_tooling", 10, f"{tooling} model parser/generator/compiler class observed")

    modules = int(signals["model_named_module_count"])
    if modules >= 2:
        add("model_modules", 15, f"{modules} model-oriented modules or source roots observed")
    elif modules == 1:
        add("model_modules", 8, "one model-oriented module or source root observed")

    jpa_entities = int(signals["standard_entity_type_count"])
    if jpa_entities >= 20:
        add("standard_entities", 20, f"{jpa_entities} standard persistence/document entities observed")
    elif jpa_entities >= 5:
        add("standard_entities", 12, f"{jpa_entities} standard persistence/document entities observed")
    elif jpa_entities >= 1:
        add("standard_entities", 5, f"{jpa_entities} standard persistence/document entity observed")

    bindings = int(signals["schema_binding_type_count"])
    if bindings >= 10:
        add("schema_bindings", 12, f"{bindings} schema-bound classes observed")
    elif bindings >= 3:
        add("schema_bindings", 8, f"{bindings} schema-bound classes observed")
    elif bindings >= 1:
        add("schema_bindings", 3, f"{bindings} schema-bound class observed")

    declarative = int(signals["declarative_schema_file_count"])
    if declarative >= 20:
        add("declarative_schemas", 20, f"{declarative} declarative schema files observed")
    elif declarative >= 5:
        add("declarative_schemas", 12, f"{declarative} declarative schema files observed")
    elif declarative >= 1:
        add("declarative_schemas", 5, f"{declarative} declarative schema file observed")

    physical = int(signals["physical_schema_file_count"])
    if physical >= 20:
        add("physical_schema", 12, f"{physical} migration or DDL files observed")
    elif physical >= 5:
        add("physical_schema", 8, f"{physical} migration or DDL files observed")
    elif physical >= 1:
        add("physical_schema", 3, f"{physical} migration or DDL file observed")

    executable = int(signals["executable_type_count"])
    executable_ratio = executable / class_count
    if executable_ratio >= 0.20 and annotated < 5 and tooling < 3:
        add("application_shape_penalty", -15, f"{executable}/{class_count} classes look executable and strong model ownership evidence is absent")
    elif executable_ratio >= 0.05 and annotated == 0 and tooling == 0:
        add("application_shape_penalty", -5, f"{executable}/{class_count} classes look executable")

    return max(0, min(100, score)), components


def _status(score: int) -> str:
    if score >= 60:
        return "strong"
    if score >= 30:
        return "possible"
    if score >= 15:
        return "weak"
    return "not_candidate"


def scan_data_model_candidate(
    repository_root: Path,
    files: Iterable[Path],
    *,
    repo_id: str,
    project_code: str,
    system_name: str,
    core_version: str,
) -> tuple[dict[str, Any], list[Fact], dict[str, Any]]:
    root = repository_root.resolve()
    all_files = sorted({Path(path).resolve() for path in files})
    java_files = [path for path in all_files if path.suffix.lower() == ".java" and _is_main_source(path)]
    workspace = parse_java_workspace(java_files)

    annotation_counts: Counter[str] = Counter()
    model_annotation_counts: Counter[str] = Counter()
    schema_binding_counts: Counter[str] = Counter()
    model_module_roots: set[str] = set()
    evidence: list[dict[str, Any]] = []
    java_class_count = 0
    java_field_count = 0
    model_path_type_count = 0
    model_path_field_count = 0
    annotated_model_type_count = 0
    standard_entity_type_count = 0
    relationship_field_count = 0
    schema_binding_type_count = 0
    model_tooling_type_count = 0
    executable_type_count = 0

    for parsed in workspace.parsed_files:
        for cls in parsed.classes:
            java_class_count += 1
            java_field_count += len(cls.fields)
            class_annotations = [annotation.name for annotation in cls.annotations]
            annotation_counts.update(class_annotations)
            model_annotations = [name for name in class_annotations if _model_annotation_kind(name)]
            standard_annotations = [name for name in class_annotations if name in _STRONG_MODEL_ANNOTATIONS]
            binding_annotations = [name for name in class_annotations if name in _SCHEMA_BINDING_ANNOTATIONS]
            model_path = _has_model_path(cls, root)
            if model_path:
                model_path_type_count += 1
                model_path_field_count += len(cls.fields)
                rel_parts = Path(_relative(cls.file, root)).parts
                for index, part in enumerate(rel_parts[:-1]):
                    if _segments(part) & _MODEL_PATH_SEGMENTS:
                        model_module_roots.add("/".join(rel_parts[: index + 1]))
                        break
            if model_annotations:
                annotated_model_type_count += 1
                model_annotation_counts.update(model_annotations)
                _bounded_append(evidence, _evidence(
                    "model_annotation", cls.file, root, symbol=cls.name,
                    line_start=cls.line_start, line_end=cls.line_end,
                    annotation=model_annotations[0],
                ))
            if standard_annotations:
                standard_entity_type_count += 1
            if binding_annotations:
                schema_binding_type_count += 1
                schema_binding_counts.update(binding_annotations)
                _bounded_append(evidence, _evidence(
                    "schema_binding", cls.file, root, symbol=cls.name,
                    line_start=cls.line_start, line_end=cls.line_end,
                    annotation=binding_annotations[0],
                ))
            if _is_model_tooling_class(cls):
                model_tooling_type_count += 1
                _bounded_append(evidence, _evidence(
                    "model_tooling", cls.file, root, symbol=cls.name,
                    line_start=cls.line_start, line_end=cls.line_end,
                ))
            if _is_executable_class(cls):
                executable_type_count += 1
            elif model_path and len(cls.fields) >= 2:
                _bounded_append(evidence, _evidence(
                    "model_path_type", cls.file, root, symbol=cls.name,
                    line_start=cls.line_start, line_end=cls.line_end,
                    detail=f"fields={len(cls.fields)}",
                ))
            for field in cls.fields:
                field_annotations = [annotation.name for annotation in field.annotations]
                annotation_counts.update(field_annotations)
                relation_names = [name for name in field_annotations if _relation_annotation(name)]
                if relation_names:
                    relationship_field_count += 1
                    _bounded_append(evidence, _evidence(
                        "relationship_annotation", cls.file, root,
                        symbol=f"{cls.name}.{field.name}", line_start=field.line_start,
                        line_end=field.line_end, annotation=relation_names[0],
                    ))

    declarative_schema_files: list[str] = []
    physical_schema_files: list[str] = []
    for path in all_files:
        if not path.is_file():
            continue
        suffix = path.suffix.lower()
        rel = _relative(path, root)
        rel_low = rel.lower()
        if suffix in _DECLARATIVE_SCHEMA_SUFFIXES:
            declarative_schema_files.append(rel)
            _bounded_append(evidence, _evidence("declarative_schema", path, root))
        if suffix == ".sql":
            migration_path = any(token in rel_low for token in _MIGRATION_PATH_TOKENS)
            ddl = False
            if not migration_path:
                try:
                    ddl = bool(_CREATE_TABLE_RE.search(path.read_text(encoding="utf-8", errors="ignore")[:250_000]))
                except OSError:
                    ddl = False
            if migration_path or ddl:
                physical_schema_files.append(rel)
                _bounded_append(evidence, _evidence(
                    "physical_schema", path, root,
                    detail="migration_path" if migration_path else "create_table",
                ))
        segments = _segments(rel)
        if segments & _MODEL_PATH_SEGMENTS:
            parts = Path(rel).parts
            if len(parts) > 1:
                model_module_roots.add(parts[0])

    model_ratio = round(model_path_type_count / max(1, java_class_count), 6)
    signals: dict[str, Any] = {
        "files_scanned": len(all_files),
        "java_file_count": len(java_files),
        "java_class_count": java_class_count,
        "java_field_count": java_field_count,
        "model_path_type_count": model_path_type_count,
        "model_path_field_count": model_path_field_count,
        "model_path_type_ratio": model_ratio,
        "annotated_model_type_count": annotated_model_type_count,
        "standard_entity_type_count": standard_entity_type_count,
        "relationship_field_count": relationship_field_count,
        "schema_binding_type_count": schema_binding_type_count,
        "model_tooling_type_count": model_tooling_type_count,
        "executable_type_count": executable_type_count,
        "model_named_module_count": len(model_module_roots),
        "declarative_schema_file_count": len(declarative_schema_files),
        "physical_schema_file_count": len(physical_schema_files),
        "parse_error_count": workspace.parse_errors,
    }
    score, score_components = _score(signals)
    candidate_status = _status(score)
    profile = {
        "artifact": "data_model_candidate_profile",
        "schema_version": SCHEMA_VERSION,
        "repo_id": repo_id,
        "project_code": project_code,
        "system_name": system_name,
        "candidate_status": candidate_status,
        "score": score,
        "signals": signals,
        "score_components": score_components,
        "observed_annotations": {
            "model": [{"name": name, "count": count} for name, count in sorted(model_annotation_counts.items())],
            "schema_binding": [{"name": name, "count": count} for name, count in sorted(schema_binding_counts.items())],
            "top_all": [{"name": name, "count": count} for name, count in annotation_counts.most_common(25)],
        },
        "model_named_modules": sorted(model_module_roots)[:100],
        "declarative_schema_files": sorted(declarative_schema_files)[:100],
        "physical_schema_files": sorted(physical_schema_files)[:100],
        "evidence": sorted(evidence, key=lambda item: (item.get("kind", ""), item.get("path", ""), item.get("line_start") or 0, item.get("symbol", ""))),
        "coverage": {
            "status": "complete" if not workspace.warnings else "partial",
            "java_parse_warnings": list(workspace.warnings)[:20],
            "evidence_is_repository_relative": True,
            "full_data_model_analysis_performed": False,
        },
        "producer": {
            "component": "code-analyzer-core",
            "version": core_version,
            "analyzer_id": "data-model-candidate-analyzer",
        },
    }

    facts: list[Fact] = []
    for component in score_components:
        facts.append(Fact(
            fact_type="data_model_candidate_signal",
            name=str(component["component"]),
            properties={
                "repo_id": repo_id,
                "candidate_status": candidate_status,
                "score": score,
                **component,
            },
            evidence=[],
        ))
    status = {
        "requested": True,
        "status": "success" if profile["coverage"]["status"] == "complete" else "partial",
        "candidate_status": candidate_status,
        "score": score,
        **signals,
    }
    return profile, facts, status
