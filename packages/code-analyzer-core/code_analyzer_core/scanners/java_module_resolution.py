from __future__ import annotations

"""Deterministic Gradle-aware Java type and call resolution observations.

The resolver composes two already observed source contracts: Tree-sitter Java
syntax and source-declared Gradle project dependencies.  It publishes exact
resolution/boundary facts and explicit unresolved references; it does not infer
architecture roles, runtime dispatch, semantic equivalence, or confidence.
"""

from collections import Counter, defaultdict, deque
from pathlib import Path
from typing import Any
import hashlib
import re

from code_analyzer_core.models import EvidenceRef, Fact
from code_analyzer_core.scanners.java_syntax import JAVA_SYNTAX_EXTRACTOR, parse_java_files

_SIMPLE = {
    "byte", "short", "int", "long", "float", "double", "boolean", "char", "void",
    "Byte", "Short", "Integer", "Long", "Float", "Double", "Boolean", "Character",
    "String", "Object", "Class", "var", "unknown",
}
_CONTAINERS = {"List", "Set", "Collection", "Iterable", "Map", "Optional", "Stream", "ArrayList", "HashMap", "HashSet"}


def _id(prefix: str, *parts: object) -> str:
    raw = "\u001f".join(str(x or "") for x in parts)
    return f"{prefix}_{hashlib.sha256(raw.encode()).hexdigest()[:20]}"


def _simple(value: str | None) -> str:
    text = re.sub(r"\s+", " ", str(value or "").strip())
    text = re.sub(r"\[\]$", "", text)
    if "<" in text:
        text = text.split("<", 1)[0].strip()
    return text.rsplit(".", 1)[-1]


def _tokens(value: str | None) -> list[str]:
    found = re.findall(r"\b[A-Z][A-Za-z0-9_$]*\b", str(value or ""))
    return list(dict.fromkeys(x for x in found if len(x) > 1 and x not in _SIMPLE and x not in _CONTAINERS))


def _evidence(path: Path, start: int | None, end: int | None) -> list[EvidenceRef]:
    return [EvidenceRef(file_path=str(path), line_start=start, line_end=end, extractor=JAVA_SYNTAX_EXTRACTOR)]


def _module_contract(gradle_facts: list[Fact]) -> tuple[dict[str, Path], dict[str, set[str]], dict[tuple[str, str], list[str]]]:
    roots: dict[str, Path] = {}
    direct: dict[str, set[str]] = defaultdict(set)
    edge_refs: dict[tuple[str, str], list[str]] = defaultdict(list)
    for fact in gradle_facts:
        props = fact.properties or {}
        if fact.fact_type == "gradle_module_observation":
            module = str(props.get("module_path") or fact.name)
            directory = props.get("project_directory")
            if directory:
                roots[module] = Path(str(directory)).resolve()
        elif fact.fact_type == "module_dependency_observation":
            source = str(props.get("source_module_path") or "")
            target = str(props.get("target_module_path") or "")
            if source and target:
                direct[source].add(target)
                edge_refs[(source, target)].append(str(props.get("observation_id") or fact.name))
    return roots, direct, edge_refs


def _module_for_file(path: Path, roots: dict[str, Path]) -> str | None:
    resolved = path.resolve()
    matches: list[tuple[int, str]] = []
    for module, root in roots.items():
        try:
            resolved.relative_to(root)
            matches.append((len(root.parts), module))
        except ValueError:
            pass
    return max(matches)[1] if matches else None


def _source_set(path: Path, module_root: Path | None) -> str:
    if module_root is None:
        return "main"
    try:
        rel = path.resolve().relative_to(module_root)
    except ValueError:
        return "main"
    parts = rel.parts
    if "src" in parts:
        index = parts.index("src")
        if index + 1 < len(parts):
            return parts[index + 1]
    return "main"


def _accessible_modules(module: str | None, direct: dict[str, set[str]]) -> set[str]:
    if not module:
        return set()
    seen = {module}
    queue = deque([module])
    while queue:
        current = queue.popleft()
        for target in sorted(direct.get(current, set())):
            if target not in seen:
                seen.add(target)
                queue.append(target)
    return seen


def _resolve_type(*, parsed: Any, token: str, source_module: str | None, by_simple: dict[str, list[dict[str, Any]]], accessible: set[str]) -> dict[str, Any]:
    exact_imports = sorted({x for x in parsed.imports if not x.endswith(".*") and x.rsplit(".", 1)[-1] == token})
    candidates = list(by_simple.get(token) or [])
    by_fqcn = {x["fqcn"]: x for x in candidates}
    if len(exact_imports) == 1:
        imported = by_fqcn.get(exact_imports[0])
        if imported and imported["module"] in accessible:
            return {"status": "resolved", "basis": "explicit_import_and_module_access", "target": imported, "candidates": [imported]}
        if imported:
            return {"status": "inaccessible", "basis": "explicit_import_without_project_dependency", "candidates": [imported]}
        return {"status": "external", "basis": "explicit_import_external", "external_fqcn": exact_imports[0], "candidates": []}
    if len(exact_imports) > 1:
        return {"status": "ambiguous", "basis": "multiple_explicit_imports", "candidates": [by_fqcn[x] for x in exact_imports if x in by_fqcn]}
    same_package = [x for x in candidates if x["package"] == parsed.package and x["module"] in accessible]
    if len(same_package) == 1:
        return {"status": "resolved", "basis": "same_package_and_module_access", "target": same_package[0], "candidates": same_package}
    visible = [x for x in candidates if x["module"] in accessible]
    same_module = [x for x in visible if x["module"] == source_module]
    if len(same_module) == 1:
        return {"status": "resolved", "basis": "same_module_unique_type", "target": same_module[0], "candidates": same_module}
    if len(visible) == 1:
        return {"status": "resolved", "basis": "accessible_project_dependency_unique_type", "target": visible[0], "candidates": visible}
    if len(visible) > 1:
        return {"status": "ambiguous", "basis": "multiple_accessible_project_types", "candidates": visible}
    if candidates:
        return {"status": "inaccessible", "basis": "type_exists_outside_module_neighborhood", "candidates": candidates}
    return {"status": "unresolved", "basis": "no_source_type_or_explicit_import", "candidates": []}


def build_java_module_resolution_facts(files: list[Path], gradle_facts: list[Fact]) -> tuple[list[Fact], dict[str, Any]]:
    roots, direct, edge_refs = _module_contract(gradle_facts)
    if not roots:
        return [], {"requested": True, "status": "not_applicable", "reason": "no_gradle_module_graph", "facts_extracted": 0}
    parsed_files, warnings = parse_java_files(files)
    types: list[dict[str, Any]] = []
    by_simple: dict[str, list[dict[str, Any]]] = defaultdict(list)
    methods_by_fqcn: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for parsed in parsed_files:
        module = _module_for_file(parsed.file, roots)
        source_set = _source_set(parsed.file, roots.get(module) if module else None)
        for cls in parsed.classes:
            fqcn = f"{parsed.package}.{cls.name}" if parsed.package else cls.name
            entry = {"fqcn": fqcn, "simple": cls.name, "package": parsed.package, "module": module, "source_set": source_set, "file": parsed.file, "class": cls, "parsed": parsed}
            types.append(entry)
            by_simple[cls.name].append(entry)
            for method in cls.methods:
                methods_by_fqcn[fqcn].append({"method": method, "entry": entry})

    facts: list[Fact] = []
    resolution_cache: dict[tuple[str, str], dict[str, Any]] = {}
    for entry in types:
        parsed, cls, source_module = entry["parsed"], entry["class"], entry["module"]
        accessible = _accessible_modules(source_module, direct)
        common = {"source_module_path": source_module, "source_set": entry["source_set"], "owner_fqcn": entry["fqcn"], "module_neighborhood": sorted(accessible), "syntax_provider": "tree_sitter", "build_system": "gradle"}
        refs: list[tuple[str, str, str | None, int | None, int | None]] = []
        refs.extend((x, "super_type", None, cls.line_start, cls.line_end) for x in cls.super_types)
        refs.extend((x.type, "field_type", x.name, x.line_start, x.line_end) for x in cls.fields)
        for method in cls.methods:
            refs.append((method.return_type, "method_return_type", method.name, method.line_start, method.line_end))
            refs.extend((p.type, "method_parameter_type", f"{method.name}.{p.name}", method.line_start, method.line_end) for p in method.params)
        for expression, role, member, line_start, line_end in refs:
            for token in _tokens(expression):
                resolved = _resolve_type(parsed=parsed, token=token, source_module=source_module, by_simple=by_simple, accessible=accessible)
                resolution_cache[(str(parsed.file), token)] = resolved
                target = resolved.get("target") or {}
                props = {**common, "observation_id": _id("cross_module_type", parsed.file, entry["fqcn"], role, member, token, line_start), "reference_role": role, "member_name": member, "referenced_type": token, "declared_type_expression": expression, "resolution_status": resolved["status"], "resolution_basis": resolved["basis"], "target_fqcn": target.get("fqcn"), "target_module_path": target.get("module"), "target_source_set": target.get("source_set"), "candidate_fqcns": [x["fqcn"] for x in resolved.get("candidates", [])], "candidate_modules": sorted({str(x.get("module")) for x in resolved.get("candidates", [])}), "module_dependency_evidence_refs": edge_refs.get((source_module, target.get("module")), []) if target else []}
                if resolved["status"] == "resolved" and target.get("module") != source_module:
                    facts.append(Fact(fact_type="cross_module_type_resolution_observation", name=f"{entry['fqcn']} -> {target.get('fqcn')}", properties={k:v for k,v in props.items() if v is not None}, evidence=_evidence(parsed.file, line_start, line_end)))
                elif resolved["status"] in {"unresolved", "ambiguous", "inaccessible"}:
                    facts.append(Fact(fact_type="unresolved_module_reference_observation", name=f"{entry['fqcn']} -> {token}", properties={k:v for k,v in props.items() if v is not None}, evidence=_evidence(parsed.file, line_start, line_end)))

        fields = {field.name: field.type for field in cls.fields}
        for method in cls.methods:
            variables = dict(fields)
            variables.update({p.name: p.type for p in method.params})
            for assignment in method.assignments:
                if assignment.declared_type:
                    variables[assignment.target] = assignment.declared_type
            for call in method.calls:
                receiver = str(call.receiver or "").strip()
                if not receiver or receiver in {"this", "super"}:
                    target_type = entry
                    receiver_basis = "same_class_receiver"
                else:
                    head = receiver.split(".", 1)[0]
                    declared = variables.get(head)
                    token = _simple(declared) if declared else (_simple(head) if head[:1].isupper() else "")
                    if not token:
                        continue
                    resolved = _resolve_type(parsed=parsed, token=token, source_module=source_module, by_simple=by_simple, accessible=accessible)
                    target_type = resolved.get("target")
                    receiver_basis = f"receiver_type:{resolved.get('basis')}"
                    if not target_type:
                        continue
                method_candidates = [x for x in methods_by_fqcn.get(target_type["fqcn"], []) if x["method"].name == call.method and len(x["method"].params) == len(call.args)]
                if len(method_candidates) != 1:
                    continue
                callee = method_candidates[0]["method"]
                target_module = target_type["module"]
                if target_module == source_module:
                    continue
                call_id = _id("cross_module_call", parsed.file, method.operation, call.start_byte, call.text)
                props = {**common, "observation_id": call_id, "caller_operation": method.operation, "caller_fqcn": entry["fqcn"], "receiver_expression": receiver or None, "receiver_resolution_basis": receiver_basis, "method_name": call.method, "argument_count": len(call.args), "target_fqcn": target_type["fqcn"], "target_module_path": target_module, "target_source_set": target_type["source_set"], "callee_operation": callee.operation, "callee_signature": f"{target_type['fqcn']}#{callee.name}({','.join(p.type for p in callee.params)})", "resolution_basis": "resolved_receiver_type_and_unique_name_arity", "module_dependency_evidence_refs": edge_refs.get((source_module, target_module), []), "observation_policy": "source-declared module accessibility plus exact source type and unique method name/arity; no runtime dispatch verdict"}
                facts.append(Fact(fact_type="cross_module_call_resolution_observation", name=f"{method.operation} -> {target_type['fqcn']}.{callee.name}", properties={k:v for k,v in props.items() if v is not None}, evidence=_evidence(parsed.file, call.line_start, call.line_end)))
                facts.append(Fact(fact_type="module_boundary_interaction_observation", name=f"{source_module} -> {target_module}", properties={**props, "interaction_kind": "java_method_call", "internal_external_classification": "internal_project_module"}, evidence=_evidence(parsed.file, call.line_start, call.line_end)))

    counts = Counter(f.fact_type for f in facts)
    return facts, {"requested": True, "status": "success", "provider": "tree_sitter_plus_gradle_source_contract", "modules_observed": len(roots), "module_edges_observed": sum(len(x) for x in direct.values()), "java_types_indexed": len(types), "facts_extracted": len(facts), "fact_type_counts": dict(sorted(counts.items())), "parse_warnings": list(warnings), "policy": "mechanical source resolution only; no runtime dispatch, architecture role, semantic equivalence, confidence, or business verdict"}
