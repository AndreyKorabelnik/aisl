from __future__ import annotations

import ast
import csv
import hashlib
import json
import re
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any, Iterable

import yaml

from code_analyzer_core.models import Fact, EvidenceRef
from code_analyzer_core.scanners.java_syntax import parse_java_text
from code_analyzer_core.utils import read_text, snippet_around, line_number_for_offset

REFERENCE_SUFFIXES = {".java", ".py", ".sql", ".yaml", ".yml", ".json", ".properties", ".csv", ".tsv", ".xml", ".toml", ".conf"}
MIN_ENTRIES = 2
MAX_ENTRIES_PER_SET = 5000
MAX_SAMPLE = 20
MAX_VALUE_FACTS_PER_SET = 500

def _line_for(path_text: str, offset: int) -> int:
    return line_number_for_offset(path_text, offset)


def _snippet(path_text: str, line: int | None, max_chars: int = 1800) -> str | None:
    if not line:
        return None
    sn = snippet_around(path_text, line, radius=4)
    return sn[:max_chars] if sn else None


def _ev(path: Path, text: str, line_start: int | None, line_end: int | None = None, extractor: str = "declared_value_scan") -> list[EvidenceRef]:
    return [EvidenceRef(file_path=str(path), line_start=line_start, line_end=line_end or line_start, snippet=_snippet(text, line_start), extractor=extractor)]


def _safe_name(value: str | None, fallback: str) -> str:
    raw = str(value or "").strip()
    raw = re.sub(r"[^A-Za-z0-9_.$/-]+", "_", raw).strip("_")
    return raw[:120] or fallback


def _primitive(value: Any) -> bool:
    return isinstance(value, (str, int, float, bool)) or value is None


def _stringify(value: Any, max_len: int = 240) -> str:
    if isinstance(value, str):
        return value[:max_len]
    try:
        return json.dumps(value, ensure_ascii=False, default=str)[:max_len]
    except Exception:
        return str(value)[:max_len]


def _entry(key: Any, value: Any = None, **extra: Any) -> dict[str, Any]:
    item = {"key": _stringify(key), "value": _stringify(value) if value is not None else None}
    item.update({k: v for k, v in extra.items() if v is not None})
    return {k: v for k, v in item.items() if v is not None}


def _stable_id(prefix: str, *parts: Any) -> str:
    raw = "|".join(str(part or "").replace("\\", "/").strip().lower() for part in parts)
    digest = hashlib.sha256(raw.encode("utf-8", errors="ignore")).hexdigest()[:16]
    return f"{prefix}_{digest}"


def _source_set_for_path(path: Path) -> str:
    norm = "/" + str(path).replace("\\", "/").strip("/").lower() + "/"
    if any(x in norm for x in ("/src/test/", "/tests/", "/test/")):
        return "test"
    if any(x in norm for x in ("/db/migration/", "/migrations/", "/migration/", "/liquibase/", "/flyway/")):
        return "migration"
    if any(x in norm for x in ("/fixture/", "/fixtures/")):
        return "fixture"
    if any(x in norm for x in ("/example/", "/examples/", "/sample/", "/samples/")):
        return "example_sample"
    if any(x in norm for x in ("/generated/", "/target/generated/", "/build/generated/")):
        return "generated"
    if any(x in norm for x in ("/docs/", "/documentation/")):
        return "documentation"
    if "/src/main/" in norm:
        return "production"
    return "unknown"



class _Collector:
    def __init__(self) -> None:
        self.value_sets: list[Fact] = []
        self.values: list[Fact] = []

    def add(
        self,
        *,
        name: str,
        syntax_kind: str,
        location_kind: str,
        entries: list[dict[str, Any]],
        path: Path,
        text: str,
        line_start: int | None,
        line_end: int | None = None,
        key_type: str = "unknown",
        value_type: str = "unknown",
        source_expression: str | None = None,
        additional: dict[str, Any] | None = None,
    ) -> None:
        all_entries = [entry for entry in entries if isinstance(entry, dict)]
        if len(all_entries) < MIN_ENTRIES:
            return
        observed_entries = all_entries[:MAX_ENTRIES_PER_SET]
        source_set = _source_set_for_path(path)
        set_id = _stable_id(
            "declared_value_set",
            path,
            syntax_kind,
            name,
            line_start,
            source_expression,
        )
        extraction_truncated = len(all_entries) > len(observed_entries)
        value_fact_count = min(len(observed_entries), MAX_VALUE_FACTS_PER_SET)
        props: dict[str, Any] = {
            "declared_value_set_id": set_id,
            "syntax_kind": syntax_kind,
            "location_kind": location_kind,
            "name": name,
            "display_name": name,
            "entries_count": len(all_entries),
            "entries_observed_count": len(observed_entries),
            "entries": observed_entries,
            "sample_entries": observed_entries[:MAX_SAMPLE],
            "key_type": key_type,
            "value_type": value_type,
            "source_set": source_set,
            "value_facts_emitted": value_fact_count,
            "extraction_truncated": extraction_truncated,
            "truncation_reason": "max_entries_per_set" if extraction_truncated else None,
            "retrieval": {
                "mode": "declared_value_facts" if not extraction_truncated else "declared_value_facts_and_source_evidence",
                "source_file": str(path),
                "line_start": line_start,
                "line_end": line_end or line_start,
            },
            "source_expression": source_expression,
            "file": str(path),
            "file_format": path.suffix.lower().lstrip(".") or "unknown",
            "line_start": line_start,
            "line_end": line_end or line_start,
            "observation_status": "extracted",
        }
        if additional:
            props.update({key: value for key, value in additional.items() if value is not None})
        evidence = _ev(path, text, line_start, line_end, extractor="declared_value_scan")
        self.value_sets.append(Fact(
            fact_type="declared_value_set",
            name=name,
            properties=props,
            evidence=evidence,
        ))
        for ordinal, entry in enumerate(observed_entries[:MAX_VALUE_FACTS_PER_SET], 1):
            value_id = _stable_id(
                "declared_value",
                set_id,
                ordinal,
                entry.get("key"),
                entry.get("value"),
            )
            self.values.append(Fact(
                fact_type="declared_value",
                name=f"{name}.{entry.get('key') or ordinal}",
                properties={
                    "declared_value_id": value_id,
                    "declared_value_set_id": set_id,
                    "set_name": name,
                    "syntax_kind": syntax_kind,
                    "key": entry.get("key"),
                    "value": entry.get("value"),
                    "label": entry.get("label") or entry.get("name") or entry.get("description"),
                    "entry": entry,
                    "ordinal": ordinal,
                    "source_set": source_set,
                    "file": str(path),
                    "line_start": line_start,
                    "line_end": line_end or line_start,
                    "observation_status": "extracted",
                },
                evidence=evidence,
            ))


def _split_top_level_commas(body: str) -> list[str]:
    parts: list[str] = []
    cur: list[str] = []
    depth = 0
    quote: str | None = None
    escape = False
    for ch in body:
        if escape:
            cur.append(ch)
            escape = False
            continue
        if quote:
            cur.append(ch)
            if ch == "\\":
                escape = True
            elif ch == quote:
                quote = None
            continue
        if ch in {'"', "'"}:
            quote = ch
            cur.append(ch)
            continue
        if ch in "([{":
            depth += 1
        elif ch in ")]}":
            depth = max(0, depth - 1)
        if ch == "," and depth == 0:
            part = "".join(cur).strip()
            if part:
                parts.append(part)
            cur = []
        else:
            cur.append(ch)
    part = "".join(cur).strip()
    if part:
        parts.append(part)
    return parts


def _find_matching(text: str, start: int, open_ch: str = "(", close_ch: str = ")") -> int | None:
    depth = 0
    quote: str | None = None
    escape = False
    for i in range(start, len(text)):
        ch = text[i]
        if escape:
            escape = False
            continue
        if quote:
            if ch == "\\":
                escape = True
            elif ch == quote:
                quote = None
            continue
        if ch in {'"', "'"}:
            quote = ch
            continue
        if ch == open_ch:
            depth += 1
        elif ch == close_ch:
            depth -= 1
            if depth == 0:
                return i
    return None


def _java_string_literals(text: str) -> list[str]:
    return [m.group(1) for m in re.finditer(r'"((?:\\.|[^"\\])*)"', text)]


def _scan_java(path: Path, text: str, c: _Collector) -> None:
    # enum StateCode { ACTIVE("A", "Active"), INACTIVE("I", "Inactive"); }
    syntax = parse_java_text(text, path)
    for cls in syntax.classes:
        if cls.kind != "enum" or not cls.enum_constants:
            continue
        entries: list[dict[str, Any]] = []
        for const in cls.enum_constants:
            args = [str(arg).strip().strip('"').strip("'") for arg in const.args]
            if args:
                entries.append(_entry(args[0], args[1] if len(args) > 1 else const.name, enum_constant=const.name))
            else:
                entries.append(_entry(const.name, const.name, enum_constant=const.name))
        c.add(
            name=cls.name,
            syntax_kind="java_enum",
            location_kind="code",
            entries=entries,
            path=path,
            text=text,
            line_start=cls.line_start,
            line_end=cls.line_end,
            key_type="enum_or_string",
            value_type="string",
            source_expression=f"enum {cls.name}",
        )

    # static maps/lists/sets based on Map.of/List.of/Set.of/Arrays.asList/Map.entry.
    assign_re = re.compile(r"(?P<name>[A-Za-z_][A-Za-z0-9_]*)\s*=\s*(?P<factory>(?:[A-Za-z0-9_]+\.)*Map\.ofEntries|(?:[A-Za-z0-9_]+\.)*Map\.of|(?:[A-Za-z0-9_]+\.)*Set\.of|(?:[A-Za-z0-9_]+\.)*List\.of|Arrays\.asList)\s*\(", re.M)
    for m in assign_re.finditer(text):
        name = m.group("name")
        factory = m.group("factory")
        open_idx = text.find("(", m.start("factory"))
        end_idx = _find_matching(text, open_idx)
        if end_idx is None:
            continue
        body = text[open_idx + 1:end_idx]
        literals = _java_string_literals(body)
        entries: list[dict[str, Any]] = []
        kind = "java_static_list"
        if factory.endswith("Map.of") or factory.endswith("Map.ofEntries"):
            kind = "java_static_map"
            if "Map.entry" in body:
                for em in re.finditer(r"Map\.entry\s*\(", body):
                    start = body.find("(", em.start())
                    end = _find_matching(body, start)
                    if end is None:
                        continue
                    vals = _java_string_literals(body[start + 1:end])
                    if len(vals) >= 2:
                        entries.append(_entry(vals[0], vals[1]))
            else:
                for i in range(0, len(literals) - 1, 2):
                    entries.append(_entry(literals[i], literals[i + 1]))
        else:
            for val in literals:
                entries.append(_entry(val, val))
        c.add(
            name=name,
            syntax_kind=kind,
            location_kind="code",
            entries=entries,
            path=path,
            text=text,
            line_start=_line_for(text, m.start()),
            line_end=_line_for(text, end_idx),
            key_type="string",
            value_type="string",
            source_expression=f"{name} = {factory}(...)"[:200],
        )

    # switch-style literal mapping.
    switch_entries: list[dict[str, Any]] = []
    first_line: int | None = None
    last_line: int | None = None
    for m in re.finditer(r"case\s+\"([^\"]+)\"\s*(?::|->)\s*(?:return\s+)?\"([^\"]+)\"", text):
        switch_entries.append(_entry(m.group(1), m.group(2)))
        first_line = first_line or _line_for(text, m.start())
        last_line = _line_for(text, m.end())
    if len(switch_entries) >= MIN_ENTRIES:
        c.add(
            name=f"{path.stem}_switch_literal_mapping",
            syntax_kind="java_switch_mapping",
            location_kind="code",
            entries=switch_entries,
            path=path,
            text=text,
            line_start=first_line,
            line_end=last_line,
            key_type="string",
            value_type="string",
            source_expression="switch/case literal mapping",
        )


def _literal_node_to_entry(value: ast.AST) -> Any:
    try:
        return ast.literal_eval(value)
    except Exception:
        return None


def _scan_python(path: Path, text: str, c: _Collector) -> None:
    try:
        tree = ast.parse(text)
    except SyntaxError:
        return

    class Visitor(ast.NodeVisitor):
        def visit_Assign(self, node: ast.Assign) -> Any:
            names = [t.id for t in node.targets if isinstance(t, ast.Name)]
            if names:
                value = _literal_node_to_entry(node.value)
                for name in names:
                    _add_python_literal(name, value, node)
            self.generic_visit(node)

        def visit_AnnAssign(self, node: ast.AnnAssign) -> Any:
            if isinstance(node.target, ast.Name):
                value = _literal_node_to_entry(node.value) if node.value is not None else None
                _add_python_literal(node.target.id, value, node)
            self.generic_visit(node)

        def visit_ClassDef(self, node: ast.ClassDef) -> Any:
            bases = []
            for b in node.bases:
                try:
                    bases.append(ast.unparse(b))
                except Exception:
                    pass
            if any("Enum" in b for b in bases):
                entries: list[dict[str, Any]] = []
                for stmt in node.body:
                    if isinstance(stmt, (ast.Assign, ast.AnnAssign)):
                        targets = []
                        if isinstance(stmt, ast.Assign):
                            targets = [t.id for t in stmt.targets if isinstance(t, ast.Name)]
                            val_node = stmt.value
                        elif isinstance(stmt.target, ast.Name):
                            targets = [stmt.target.id]
                            val_node = stmt.value
                        else:
                            val_node = None
                        val = _literal_node_to_entry(val_node) if val_node is not None else None
                        for target in targets:
                            if target.startswith("_"):
                                continue
                            entries.append(_entry(val if _primitive(val) else target, target, enum_constant=target))
                c.add(
                    name=node.name,
                    syntax_kind="python_enum",
                    location_kind="code",
                    entries=entries,
                    path=path,
                    text=text,
                    line_start=getattr(node, "lineno", None),
                    line_end=getattr(node, "end_lineno", None),
                    key_type="enum_or_string",
                    value_type="string",
                    source_expression=f"class {node.name}(Enum)",
                )
            self.generic_visit(node)

    def _add_python_literal(name: str, value: Any, node: ast.AST) -> None:
        entries: list[dict[str, Any]] = []
        kind = "python_literal"
        if isinstance(value, dict):
            kind = "python_dict"
            for k, v in list(value.items()):
                if _primitive(k) and (_primitive(v) or isinstance(v, (dict, list, tuple))):
                    entries.append(_entry(k, v))
        elif isinstance(value, (list, tuple, set)):
            kind = "python_list"
            for v in list(value):
                if _primitive(v):
                    entries.append(_entry(v, v))
        c.add(
            name=name,
            syntax_kind=kind,
            location_kind="code",
            entries=entries,
            path=path,
            text=text,
            line_start=getattr(node, "lineno", None),
            line_end=getattr(node, "end_lineno", None),
            key_type="string_or_number",
            value_type="literal_or_object",
            source_expression=name,
        )

    Visitor().visit(tree)


def _walk_json_yaml(obj: Any, path_parts: list[str], out: list[tuple[str, list[dict[str, Any]]]]) -> None:
    name = ".".join(path_parts) if path_parts else "root"
    if isinstance(obj, dict):
        primitive_items = [(k, v) for k, v in obj.items() if _primitive(k) and (_primitive(v) or isinstance(v, (dict, list)))]
        if len(primitive_items) >= MIN_ENTRIES:
            entries = [_entry(k, v) for k, v in primitive_items]
            out.append((name, entries))
        for k, v in obj.items():
            if isinstance(v, (dict, list)):
                _walk_json_yaml(v, path_parts + [str(k)], out)
    elif isinstance(obj, list):
        # list of objects with code/key + label/name/value columns
        rows = [x for x in obj if isinstance(x, dict)]
        if len(rows) >= MIN_ENTRIES:
            keys = {kk for row in rows for kk in row.keys()}
            code_keys = [k for k in keys if str(k).lower() in {"code", "key", "id", "value", "name"}]
            label_keys = [k for k in keys if str(k).lower() in {"label", "name", "description", "title", "value"}]
            if code_keys:
                ck = code_keys[0]
                lk = next((x for x in label_keys if x != ck), None)
                entries = [_entry(row.get(ck), row.get(lk), row=row) for row in rows if row.get(ck) is not None]
                out.append((name, entries))
        for idx, v in enumerate(obj[:20]):
            if isinstance(v, (dict, list)):
                _walk_json_yaml(v, path_parts + [str(idx)], out)


def _scan_json_yaml(path: Path, text: str, c: _Collector) -> None:
    try:
        data = yaml.safe_load(text) if path.suffix.lower() in {".yaml", ".yml"} else json.loads(text)
    except Exception:
        return
    value_sets: list[tuple[str, list[dict[str, Any]]]] = []
    _walk_json_yaml(data, [path.stem], value_sets)
    for name, entries in value_sets:
        # find best-effort first key line
        token = str(entries[0].get("key") or name.split(".")[-1]) if entries else name
        idx = text.find(token)
        line = _line_for(text, idx) if idx >= 0 else 1
        c.add(
            name=name,
            syntax_kind="yaml_map" if path.suffix.lower() in {".yaml", ".yml"} else "json_map",
            location_kind="config_file" if path.suffix.lower() in {".yaml", ".yml"} else "data_file",
            entries=entries,
            path=path,
            text=text,
            line_start=line,
            key_type="string",
            value_type="literal_or_object",
            source_expression=name,
        )


def _scan_properties(path: Path, text: str, c: _Collector) -> None:
    groups: dict[str, list[dict[str, Any]]] = {}
    first_line: dict[str, int] = {}
    for idx, line in enumerate(text.splitlines(), 1):
        raw = line.strip()
        if not raw or raw.startswith(("#", "!")) or "=" not in raw:
            continue
        k, v = raw.split("=", 1)
        k = k.strip()
        v = v.strip()
        parts = re.split(r"[.]", k)
        if len(parts) < 2:
            continue
        group = ".".join(parts[:-1])
        code = parts[-1]
        groups.setdefault(group, []).append(_entry(code, v))
        first_line.setdefault(group, idx)
    for name, entries in groups.items():
        c.add(
            name=name,
            syntax_kind="properties_prefix",
            location_kind="config_file",
            entries=entries,
            path=path,
            text=text,
            line_start=first_line.get(name, 1),
            key_type="string",
            value_type="string",
            source_expression=name,
        )


def _scan_csv_tsv(path: Path, text: str, c: _Collector) -> None:
    delimiter = "\t" if path.suffix.lower() == ".tsv" else ","
    try:
        rows = list(csv.DictReader(text.splitlines(), delimiter=delimiter))
    except Exception:
        return
    if len(rows) < MIN_ENTRIES:
        return
    headers = [h for h in (rows[0].keys() if rows else []) if h]
    low = {h.lower(): h for h in headers}
    code_col = next((low[k] for k in ["code", "key", "id", "value", "state", "status", "type"] if k in low), None)
    label_col = next((low[k] for k in ["name", "label", "description", "title", "value"] if k in low and low[k] != code_col), None)
    if not code_col:
        return
    entries = [_entry(row.get(code_col), row.get(label_col), row=row) for row in rows if row.get(code_col)]
    c.add(
        name=path.stem,
        syntax_kind="csv_table" if delimiter == "," else "tsv_table",
        location_kind="data_file",
        entries=entries,
        path=path,
        text=text,
        line_start=1,
        line_end=min(len(text.splitlines()), len(entries) + 1),
        key_type="string",
        value_type="row",
        source_expression=path.name,
        additional={"columns": headers[:30]},
    )


def _scan_xml(path: Path, text: str, c: _Collector) -> None:
    try:
        root = ET.fromstring(text)
    except Exception:
        return
    groups: dict[str, list[dict[str, Any]]] = {}
    for elem in root.iter():
        attrs = elem.attrib or {}
        if not attrs:
            continue
        low = {k.lower(): k for k in attrs}
        code_key = next((low[k] for k in ["code", "key", "id", "value", "state", "status", "type"] if k in low), None)
        label_key = next((low[k] for k in ["name", "label", "description", "title", "value"] if k in low and low[k] != code_key), None)
        if code_key:
            groups.setdefault(elem.tag, []).append(_entry(attrs.get(code_key), attrs.get(label_key), attributes=attrs))
    for tag, entries in groups.items():
        token = str(entries[0].get("key") or "") if entries else ""
        idx = text.find(token) if token else -1
        c.add(
            name=f"{path.stem}.{tag}",
            syntax_kind="xml_elements",
            location_kind="data_file",
            entries=entries,
            path=path,
            text=text,
            line_start=_line_for(text, idx) if idx >= 0 else 1,
            key_type="string",
            value_type="xml_attributes",
            source_expression=tag,
        )


def _scan_sql_reference(path: Path, text: str, c: _Collector) -> None:
    case_entries: list[dict[str, Any]] = []
    first_line: int | None = None
    last_line: int | None = None
    for m in re.finditer(r"WHEN\s+'([^']+)'\s+THEN\s+'([^']+)'", text, re.I):
        case_entries.append(_entry(m.group(1), m.group(2)))
        first_line = first_line or _line_for(text, m.start())
        last_line = _line_for(text, m.end())
    if len(case_entries) >= MIN_ENTRIES:
        c.add(
            name=f"{path.stem}_case_mapping",
            syntax_kind="sql_case_mapping",
            location_kind="sql",
            entries=case_entries,
            path=path,
            text=text,
            line_start=first_line,
            line_end=last_line,
            key_type="string",
            value_type="string",
            source_expression="CASE WHEN literal mapping",
        )

    tuple_matches = list(re.finditer(r"\(\s*'([^']+)'\s*,\s*'([^']+)'(?:\s*,[^)]*)?\)", text))
    if len(tuple_matches) >= MIN_ENTRIES and re.search(r"\bVALUES\b|\bUNION\s+ALL\b", text, re.I):
        entries = [_entry(m.group(1), m.group(2)) for m in tuple_matches]
        c.add(
            name=f"{path.stem}_literal_rows",
            syntax_kind="sql_values_rows",
            location_kind="sql",
            entries=entries,
            path=path,
            text=text,
            line_start=_line_for(text, tuple_matches[0].start()),
            line_end=_line_for(text, tuple_matches[-1].end()),
            key_type="string",
            value_type="string",
            source_expression="SQL literal row set",
        )



def scan_declared_values(files: list[Path]) -> tuple[list[Fact], dict[str, Any]]:
    c = _Collector()
    scanned = 0
    discovered = 0
    skipped_unsupported = 0
    failed: list[str] = []
    suffix_counts: dict[str, int] = {}
    for path in sorted(files):
        discovered += 1
        suffix = path.suffix.lower()
        suffix_counts[suffix or "<none>"] = suffix_counts.get(suffix or "<none>", 0) + 1
        if suffix not in REFERENCE_SUFFIXES:
            skipped_unsupported += 1
            continue
        try:
            text = read_text(path)
        except Exception as exc:
            failed.append(f"{path}: {exc}")
            continue
        scanned += 1
        try:
            if suffix == ".java":
                _scan_java(path, text, c)
            elif suffix == ".py":
                _scan_python(path, text, c)
            elif suffix in {".yaml", ".yml", ".json"}:
                _scan_json_yaml(path, text, c)
            elif suffix in {".properties", ".conf"}:
                _scan_properties(path, text, c)
            elif suffix in {".csv", ".tsv"}:
                _scan_csv_tsv(path, text, c)
            elif suffix == ".xml":
                _scan_xml(path, text, c)
            elif suffix == ".sql":
                _scan_sql_reference(path, text, c)
            elif suffix == ".toml":
                _scan_properties(path, text.replace(":", "="), c)
        except Exception as exc:
            failed.append(f"{path}: {exc}")
    by_kind: dict[str, int] = {}
    by_source_set: dict[str, int] = {}
    for fact in c.value_sets:
        props = fact.properties or {}
        kind = str(props.get("syntax_kind") or "unknown")
        source_set = str(props.get("source_set") or "unknown")
        by_kind[kind] = by_kind.get(kind, 0) + 1
        by_source_set[source_set] = by_source_set.get(source_set, 0) + 1
    status = {
        "requested": True,
        "enabled": True,
        "mode": "source_only_declared_value_scan",
        "semantic_classification_performed": False,
        "files_discovered": discovered,
        "files_scanned": scanned,
        "files_skipped_unsupported": skipped_unsupported,
        "supported_suffixes": sorted(REFERENCE_SUFFIXES),
        "suffix_counts": dict(sorted(suffix_counts.items())),
        "value_sets_extracted": len(c.value_sets),
        "values_extracted": len(c.values),
        "by_syntax_kind": dict(sorted(by_kind.items())),
        "by_source_set": dict(sorted(by_source_set.items())),
        "failed_count": len(failed),
        "failed_sample": failed[:20],
        "max_entries_per_set": MAX_ENTRIES_PER_SET,
        "max_value_facts_per_set": MAX_VALUE_FACTS_PER_SET,
        "sample_entry_limit": MAX_SAMPLE,
        "coverage_status": "partial" if failed or skipped_unsupported else "complete_for_supported_suffixes",
    }
    return c.value_sets + c.values, status


def _bounded_summary_entries(entries: Any, *, max_entries: int = 8, max_text: int = 180) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    if not isinstance(entries, list):
        return out
    for ent in entries[:max_entries]:
        if not isinstance(ent, dict):
            out.append({"value": _stringify(ent, max_text)})
            continue
        item: dict[str, Any] = {}
        for key in ("key", "value", "label", "name", "description"):
            if key in ent and ent.get(key) is not None:
                item[key] = _stringify(ent.get(key), max_text)
        if not item:
            for key, value in list(ent.items())[:4]:
                item[str(key)[:40]] = _stringify(value, max_text)
        out.append(item)
    return out


def summarize_declared_value_facts(
    all_facts: list[Fact],
    *,
    base_status: dict[str, Any] | None = None,
    max_value_sets: int = 300,
    max_sample_entries: int = 8,
) -> tuple[list[Fact], dict[str, Any]]:
    """Build bounded summaries from facts already extracted by one source scan.

    The previous pipeline invoked ``scan_declared_values`` twice whenever both raw
    facts and summaries were requested.  On real Java repositories that meant a
    second complete Tree-sitter parse of every source file.  Summary materialization
    is purely deterministic projection and therefore reuses the observed facts.
    """
    base_status = dict(base_status or {})
    value_sets = [f for f in all_facts if f.fact_type == "declared_value_set"]
    values = [f for f in all_facts if f.fact_type == "declared_value"]
    selected = sorted(
        value_sets,
        key=lambda f: (int((f.properties or {}).get("entries_count") or 0), str(f.name)),
        reverse=True,
    )[:max_value_sets]
    summaries: list[Fact] = []
    by_kind: dict[str, int] = {}
    for fact in selected:
        props = fact.properties or {}
        kind = str(props.get("syntax_kind") or "unknown")
        by_kind[kind] = by_kind.get(kind, 0) + 1
        summaries.append(Fact(
            fact_type="declared_value_set_summary",
            name=str(props.get("display_name") or props.get("name") or fact.name),
            properties={
                "declared_value_set_summary_id": _stable_id("declared_value_set_summary", props.get("declared_value_set_id") or fact.name),
                "declared_value_set_id": props.get("declared_value_set_id"),
                "name": props.get("name") or fact.name,
                "display_name": props.get("display_name") or props.get("name") or fact.name,
                "syntax_kind": props.get("syntax_kind"),
                "location_kind": props.get("location_kind"),
                "entries_count": props.get("entries_count"),
                "sample_entries": _bounded_summary_entries(props.get("sample_entries") or [], max_entries=max_sample_entries),
                "key_type": props.get("key_type"),
                "value_type": props.get("value_type"),
                "source_expression": _stringify(props.get("source_expression"), 300) if props.get("source_expression") is not None else None,
                "source_set": props.get("source_set") or "unknown",
                "entries_observed_count": props.get("entries_observed_count"),
                "extraction_truncated": props.get("extraction_truncated"),
                "truncation_reason": props.get("truncation_reason"),
                "retrieval": props.get("retrieval"),
                "summary_policy": "bounded_declared_value_set_summary_no_semantic_classification",
            },
            evidence=list(fact.evidence or [])[:1],
        ))
    status = {
        "requested": True,
        "mode": "bounded_declared_value_set_summary",
        "materialization_source": "existing_declared_value_facts",
        "semantic_classification_performed": False,
        "source_extractor_mode": base_status.get("mode"),
        "files_scanned": base_status.get("files_scanned"),
        "raw_value_sets_extracted": len(value_sets),
        "raw_values_extracted": len(values),
        "summary_value_sets_emitted": len(summaries),
        "summary_cap": max_value_sets,
        "by_syntax_kind": dict(sorted(by_kind.items())),
        "failed_count": base_status.get("failed_count"),
        "failed_sample": base_status.get("failed_sample"),
        "coverage_status": base_status.get("coverage_status"),
    }
    return summaries, status


def scan_declared_value_summaries(
    files: list[Path],
    *,
    max_value_sets: int = 300,
    max_sample_entries: int = 8,
) -> tuple[list[Fact], dict[str, Any]]:
    """Compatibility entry point for callers requesting summaries without raw facts."""
    all_facts, base_status = scan_declared_values(files)
    return summarize_declared_value_facts(
        all_facts,
        base_status=base_status,
        max_value_sets=max_value_sets,
        max_sample_entries=max_sample_entries,
    )
