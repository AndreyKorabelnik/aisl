from __future__ import annotations

import hashlib
import logging
import re
from pathlib import Path
from typing import Any

try:
    import sqlglot
    from sqlglot import exp
except Exception:  # sqlglot is optional at runtime; regex fallback still works.
    sqlglot = None
    exp = None

from code_analyzer_core.models import Fact, EvidenceRef
from code_analyzer_core.utils import read_text
from code_analyzer_core.evidence_contract import maturity_props, candidate_signal

logging.getLogger("sqlglot").setLevel(logging.ERROR)

PLACEHOLDER_RE = re.compile(r"\$\{[^}]+\}")
COMMENT_BLOCK_RE = re.compile(r"/\*.*?\*/", re.DOTALL)
COMMENT_LINE_RE = re.compile(r"--.*?$", re.MULTILINE)

CREATE_TABLE_RE = re.compile(r"\bcreate\s+table\s+([a-zA-Z0-9_.$\"{}]+)\s*\(", re.IGNORECASE | re.MULTILINE)
CREATE_VIEW_RE = re.compile(r"\bcreate\s+(?:or\s+replace\s+)?(?:materialized\s+)?view\s+([a-zA-Z0-9_.$\"{}]+)\s+as\b", re.IGNORECASE | re.MULTILINE)
CREATE_PROC_RE = re.compile(r"\bcreate\s+(?:or\s+replace\s+)?procedure\s+([a-zA-Z0-9_.$\"{}]+)", re.IGNORECASE | re.MULTILINE)
CREATE_FUNC_RE = re.compile(r"\bcreate\s+(?:or\s+replace\s+)?function\s+([a-zA-Z0-9_.$\"{}]+)", re.IGNORECASE | re.MULTILINE)
CREATE_TRIGGER_RE = re.compile(r"\bcreate\s+(?:or\s+replace\s+)?trigger\s+([a-zA-Z0-9_.$\"{}]+)", re.IGNORECASE | re.MULTILINE)
INSERT_INTO_RE = re.compile(r"\binsert\s+into\s+([a-zA-Z0-9_.$\"{}]+)", re.IGNORECASE | re.MULTILINE)
UPDATE_RE = re.compile(r"\bupdate\s+([a-zA-Z0-9_.$\"{}]+)", re.IGNORECASE | re.MULTILINE)


def _sql_evidence_props(*, parser: str, kind: str | None = None, target: str | None = None, parsed: bool = True) -> dict[str, Any]:
    low_kind = str(kind or "").lower()
    is_write = low_kind in {"insert", "update", "merge", "delete", "create", "sql_insert_target_fallback", "sql_update_target_fallback"}
    props = maturity_props({
        "sql_statement": "confirmed" if parsed else "unresolved",
        "persistence_write": "confirmed" if is_write and parsed else ("unresolved" if is_write else "not_applicable"),
        "physical_storage": "confirmed" if target and parsed else ("unresolved" if is_write else "not_applicable"),
        "field_mapping": "unresolved" if is_write else "not_applicable",
        "source_boundary": "not_applicable",
        "end_to_end_trace": "not_applicable",
    }, notes=["SQL scanner applies the same strict evidence contract: parsed SQL targets are confirmed; unresolved column/source lineage requires targeted SQL/source inspection."])
    signals = []
    if parser == "regex_fallback":
        signals.append(candidate_signal(
            signal_type="sql_regex_target_signal",
            target=target,
            basis="SQL target was detected by regex fallback rather than full parser",
            recommended_action="use source-open on the SQL file/statement if column lineage or procedural context is decision-blocking",
            requires_source_inspection=True,
        ))
    props["candidate_signals"] = signals
    return props


def normalize_sql_for_parsing(sql: str) -> str:
    sql = PLACEHOLDER_RE.sub("PLACEHOLDER", sql)
    sql = COMMENT_BLOCK_RE.sub("", sql)
    sql = COMMENT_LINE_RE.sub("", sql)
    return sql.strip()


def is_ignorable_sql_fragment(statement: str) -> bool:
    """
    PL/pgSQL DO/procedure blocks are often split into harmless tails like END', END;' or a lone quote.
    These fragments do not carry useful schema/lineage facts and should not pollute warnings.
    """
    s = normalize_sql_for_parsing(statement)
    s = s.strip().lower()
    s = s.replace(";", "").replace("$", "").replace("'", "").strip()
    s = " ".join(s.split())
    return s in {"", "end", "end if", "begin", "do", "language plpgsql"} or len(s) <= 1


def split_sql_statements(text: str) -> list[tuple[int, str]]:
    # Handles normal semicolons; DO/procedure bodies may still be split, fallback covers fragments.
    out: list[tuple[int, str]] = []
    buf: list[str] = []
    start_line = 1
    in_dollar = False
    for idx, line in enumerate(text.splitlines(), 1):
        if not buf:
            start_line = idx
        if "$$" in line:
            in_dollar = not in_dollar
        buf.append(line)
        if line.strip().endswith(";") and not in_dollar:
            stmt = "\n".join(buf).strip().rstrip(";").strip()
            if stmt:
                out.append((start_line, stmt))
            buf = []
    tail = "\n".join(buf).strip()
    if tail:
        out.append((start_line, tail))
    return out


def regex_fallback(statement: str, file_path: Path, line_start: int) -> tuple[list[Fact], dict[str, Any] | None]:
    normalized = normalize_sql_for_parsing(statement)
    facts: list[Fact] = []

    patterns = [
        ("sql_create_table_fallback", "table", CREATE_TABLE_RE),
        ("sql_create_view_fallback", "view", CREATE_VIEW_RE),
        ("sql_procedure_fallback", "procedure", CREATE_PROC_RE),
        ("sql_function_fallback", "function", CREATE_FUNC_RE),
        ("sql_trigger_fallback", "trigger", CREATE_TRIGGER_RE),
        ("sql_insert_target_fallback", "target_table", INSERT_INTO_RE),
        ("sql_update_target_fallback", "target_table", UPDATE_RE),
    ]

    for fact_type, prop, rx in patterns:
        for m in rx.finditer(normalized):
            name = m.group(1)
            facts.append(Fact(
                fact_type=fact_type,
                name=name,
                properties={**{prop: name, "parser": "regex_fallback", "statement_preview": normalized[:500]}, **_sql_evidence_props(parser="regex_fallback", kind=fact_type, target=name, parsed=False)},
                evidence=[EvidenceRef(file_path=str(file_path), line_start=line_start, line_end=line_start + statement.count("\n"), snippet=statement[:800], extractor="sql_regex_fallback")]
            ))

    if facts:
        return facts, None

    warning = {
        "file": str(file_path),
        "line_start": line_start,
        "reason": "sqlglot_failed_and_no_regex_fallback",
        "preview": normalized[:300],
    }
    return facts, warning


def _strip_db_identifier(value: str | None) -> str:
    text = (value or '').strip().strip('"')
    text = re.sub(r'^\$\{[^}]+\}\.', '', text)
    return text.strip().strip('"').lower()


def _stable_fact_id(prefix: str, *parts: Any) -> str:
    raw = "|".join(str(part or "").replace("\\", "/").strip().lower() for part in parts)
    return f"{prefix}_{hashlib.sha256(raw.encode('utf-8', errors='ignore')).hexdigest()[:16]}"


def _source_set_for_path(path: Path) -> str:
    norm = "/" + str(path).replace("\\", "/").strip("/").lower() + "/"
    if any(token in norm for token in ("/src/test/", "/tests/", "/test/")):
        return "test"
    if any(token in norm for token in ("/db/migration/", "/migrations/", "/migration/", "/liquibase/", "/flyway/")):
        return "migration"
    if any(token in norm for token in ("/fixture/", "/fixtures/")):
        return "fixture"
    if any(token in norm for token in ("/example/", "/examples/", "/sample/", "/samples/")):
        return "example_sample"
    if any(token in norm for token in ("/generated/", "/target/generated/", "/build/generated/")):
        return "generated"
    if any(token in norm for token in ("/docs/", "/documentation/")):
        return "documentation"
    if "/src/main/" in norm:
        return "production"
    return "unknown"


def _matching_paren(text: str, start: int) -> int | None:
    depth = 0
    quote: str | None = None
    index = start
    while index < len(text):
        char = text[index]
        if quote:
            if char == quote:
                if quote == "'" and index + 1 < len(text) and text[index + 1] == "'":
                    index += 2
                    continue
                quote = None
            elif char == "\\" and index + 1 < len(text):
                index += 2
                continue
            index += 1
            continue
        if char in {"'", '"'}:
            quote = char
        elif char == "(":
            depth += 1
        elif char == ")":
            depth -= 1
            if depth == 0:
                return index
        index += 1
    return None


def _literal_expression(token: str) -> dict[str, Any]:
    raw = token.strip()
    low = raw.lower()
    result: dict[str, Any] = {"expression": raw[:1000]}
    if re.fullmatch(r"(?:\?|:[A-Za-z_][A-Za-z0-9_]*|\$\{[^}]+\}|#\{[^}]+\})", raw):
        return {**result, "value_kind": "parameter", "parameterized": True}
    if len(raw) >= 2 and raw[0] == raw[-1] == "'":
        return {**result, "value": raw[1:-1].replace("''", "'"), "value_kind": "string", "parameterized": False}
    if low in {"true", "false"}:
        return {**result, "value": low == "true", "value_kind": "boolean", "parameterized": False}
    if low == "null":
        return {**result, "value": None, "value_kind": "null", "parameterized": False}
    if re.fullmatch(r"[-+]?\d+", raw):
        try:
            return {**result, "value": int(raw), "value_kind": "integer", "parameterized": False}
        except ValueError:
            pass
    if re.fullmatch(r"[-+]?(?:\d+\.\d*|\d*\.\d+)", raw):
        try:
            return {**result, "value": float(raw), "value_kind": "number", "parameterized": False}
        except ValueError:
            pass
    return {**result, "value_kind": "expression", "parameterized": bool(re.search(r"(?:\?|:[A-Za-z_]|\$\{|#\{)", raw))}


def _extract_insert_literal_writes(statement: str, file_path: Path, line_start: int) -> list[Fact]:
    normalized = normalize_sql_for_parsing(statement)
    match = re.search(
        r"\binsert\s+into\s+(?P<table>[a-zA-Z0-9_.$\"{}]+)\s*(?:\((?P<columns>[^)]*)\))?\s*values\b",
        normalized,
        re.IGNORECASE | re.DOTALL,
    )
    if not match:
        return []
    table = _strip_db_identifier(match.group("table"))
    columns = [part.strip().strip('"').lower() for part in _split_sql_projection_list(match.group("columns") or "") if part.strip()]
    rows: list[dict[str, Any]] = []
    cursor = match.end()
    while cursor < len(normalized):
        while cursor < len(normalized) and normalized[cursor] in " \t\r\n,":
            cursor += 1
        if cursor >= len(normalized) or normalized[cursor] != "(":
            break
        end = _matching_paren(normalized, cursor)
        if end is None:
            break
        expressions = [_literal_expression(part) for part in _split_sql_projection_list(normalized[cursor + 1:end])]
        row: dict[str, Any] = {"ordinal": len(rows) + 1, "values": expressions}
        if columns:
            row["by_column"] = {column: expressions[idx] for idx, column in enumerate(columns) if idx < len(expressions)}
        rows.append(row)
        cursor = end + 1
    if not table or not rows:
        return []
    parameterized = any(value.get("parameterized") for row in rows for value in row.get("values") or [])
    literal_only = all(value.get("value_kind") in {"string", "boolean", "null", "integer", "number"} for row in rows for value in row.get("values") or [])
    write_id = _stable_fact_id("literal_data_write", file_path, line_start, "insert", table, columns, normalized[:500])
    return [Fact(
        fact_type="literal_data_write",
        name=f"insert into {table}",
        properties={
            "literal_data_write_id": write_id,
            "operation": "insert",
            "table_name": table.split(".")[-1],
            "qualified_table_name": table,
            "columns": columns,
            "rows": rows[:5000],
            "rows_count": len(rows),
            "rows_truncated": len(rows) > 5000,
            "parameterized": parameterized,
            "literal_only": literal_only,
            "values_are_literal_or_declared_expression": True,
            "write_expression_kind": "sql_insert_values",
            "source_set": _source_set_for_path(file_path),
            "file": str(file_path),
            "line_start": line_start,
            "line_end": line_start + statement.count("\n"),
            "statement_preview": normalized[:2000],
            "observation_status": "extracted",
        },
        evidence=[EvidenceRef(file_path=str(file_path), line_start=line_start, line_end=line_start + statement.count("\n"), snippet=statement[:2000], extractor="sql_literal_write_scan")],
    )]


def _extract_update_literal_writes(statement: str, file_path: Path, line_start: int) -> list[Fact]:
    normalized = normalize_sql_for_parsing(statement)
    match = re.search(
        r"\bupdate\s+(?P<table>[a-zA-Z0-9_.$\"{}]+)\s+set\s+(?P<assignments>.*?)(?=\bwhere\b|\breturning\b|$)",
        normalized,
        re.IGNORECASE | re.DOTALL,
    )
    if not match:
        return []
    table = _strip_db_identifier(match.group("table"))
    assignments: list[dict[str, Any]] = []
    for part in _split_sql_projection_list(match.group("assignments") or ""):
        item = re.match(r'(?P<column>[a-zA-Z0-9_".]+)\s*=\s*(?P<value>.*)$', part, re.DOTALL)
        if not item:
            continue
        assignments.append({
            "column": item.group("column").strip().strip('"').lower(),
            "value": _literal_expression(item.group("value")),
        })
    if not table or not assignments:
        return []
    parameterized = any((item.get("value") or {}).get("parameterized") for item in assignments)
    literal_only = all((item.get("value") or {}).get("value_kind") in {"string", "boolean", "null", "integer", "number"} for item in assignments)
    where_match = re.search(r"\bwhere\s+(?P<where>.*?)(?=\breturning\b|$)", normalized, re.IGNORECASE | re.DOTALL)
    write_id = _stable_fact_id("literal_data_write", file_path, line_start, "update", table, assignments, normalized[:500])
    return [Fact(
        fact_type="literal_data_write",
        name=f"update {table}",
        properties={
            "literal_data_write_id": write_id,
            "operation": "update",
            "table_name": table.split(".")[-1],
            "qualified_table_name": table,
            "columns": [item["column"] for item in assignments],
            "assignments": assignments,
            "parameterized": parameterized,
            "literal_only": literal_only,
            "values_are_literal_or_declared_expression": True,
            "write_expression_kind": "sql_update_set",
            "where_expression": ((where_match.group("where") or "").strip()[:2000] if where_match else None),
            "source_set": _source_set_for_path(file_path),
            "file": str(file_path),
            "line_start": line_start,
            "line_end": line_start + statement.count("\n"),
            "statement_preview": normalized[:2000],
            "observation_status": "extracted",
        },
        evidence=[EvidenceRef(file_path=str(file_path), line_start=line_start, line_end=line_start + statement.count("\n"), snippet=statement[:2000], extractor="sql_literal_write_scan")],
    )]


def _extract_literal_data_writes(statement: str, file_path: Path, line_start: int) -> list[Fact]:
    return _extract_insert_literal_writes(statement, file_path, line_start) + _extract_update_literal_writes(statement, file_path, line_start)


def _extract_join_observations(statement: str, file_path: Path, line_start: int) -> list[Fact]:
    normalized = normalize_sql_for_parsing(statement)
    if not re.search(r'\bjoin\b', normalized, re.IGNORECASE):
        return []
    # Conservative usage graph: connect the FROM table to each JOIN table.
    from_m = re.search(r'\bfrom\s+(?P<table>[a-zA-Z0-9_.$"{}]+)(?:\s+(?:as\s+)?(?P<alias>[a-zA-Z0-9_]+))?', normalized, re.IGNORECASE)
    if not from_m:
        return []
    base_table = _strip_db_identifier(from_m.group('table'))
    base_alias = from_m.group('alias') or base_table.split('.')[-1]
    out: list[Fact] = []
    join_rx = re.compile(r'\bjoin\s+(?P<table>[a-zA-Z0-9_.$"{}]+)(?:\s+(?:as\s+)?(?P<alias>[a-zA-Z0-9_]+))?\s+on\s+(?P<on>.*?)(?=\b(?:left|right|inner|outer|full|cross)?\s*join\b|\bwhere\b|\bgroup\s+by\b|\border\s+by\b|\blimit\b|$)', re.IGNORECASE | re.DOTALL)
    for jm in join_rx.finditer(normalized):
        join_table = _strip_db_identifier(jm.group('table'))
        on_clause = ' '.join((jm.group('on') or '').split())[:500]
        if not join_table or join_table == base_table:
            continue
        out.append(Fact(
            fact_type='sql_join_observation',
            name=f'{base_table}->{join_table}',
            properties={
                'source_table': base_table,
                'target_table': join_table,
                'source_alias': base_alias,
                'target_alias': jm.group('alias') or join_table.split('.')[-1],
                'join_condition_preview': on_clause,
                'observation_kind': 'native_sql_join_usage',
                'observation_status': 'extracted',
                'parser': 'regex_join_usage',
                'statement_preview': normalized[:500],
            },
            evidence=[EvidenceRef(file_path=str(file_path), line_start=line_start, line_end=line_start + statement.count('\n'), snippet=statement[:800], extractor='sql_join_usage_regex')]
        ))
    return out




def _split_sql_projection_list(projection: str) -> list[str]:
    out: list[str] = []
    buf: list[str] = []
    depth = 0
    in_single = False
    i = 0
    while i < len(projection):
        ch = projection[i]
        if ch == "'":
            in_single = not in_single
            buf.append(ch)
        elif not in_single and ch == '(':
            depth += 1
            buf.append(ch)
        elif not in_single and ch == ')':
            depth = max(0, depth - 1)
            buf.append(ch)
        elif not in_single and depth == 0 and ch == ',':
            item = ''.join(buf).strip()
            if item:
                out.append(item)
            buf = []
        else:
            buf.append(ch)
        i += 1
    item = ''.join(buf).strip()
    if item:
        out.append(item)
    return out


def _projection_alias(expr_text: str) -> str | None:
    m = re.search(r'\bas\s+([a-zA-Z_][a-zA-Z0-9_]*)\s*$', expr_text, re.IGNORECASE)
    if m:
        return m.group(1)
    m = re.search(r'\s+([a-zA-Z_][a-zA-Z0-9_]*)\s*$', expr_text)
    if m and not re.search(r'[()*/+\-]', m.group(1)):
        # Avoid treating plain single column as alias.
        left = expr_text[:m.start(1)].strip()
        if left and left.lower() not in {'case', 'when', 'then', 'else', 'end'} and left != m.group(1):
            return m.group(1)
    return None


def _projection_kind(expr_text: str) -> str:
    low = expr_text.lower()
    if ' case ' in f' {low} ' or low.startswith('case'):
        return 'case_expression'
    if any(fn in low for fn in ('coalesce(', 'concat(', 'date_trunc(', 'extract(', 'substring(', 'regexp_replace(')):
        return 'function_expression'
    if re.search(r'\b(count|sum|avg|min|max)\s*\(', low):
        return 'aggregation'
    if re.search(r'[+*/-]', expr_text) and not re.match(r'^[a-zA-Z0-9_.]+$', expr_text.strip()):
        return 'calculated_expression'
    return 'direct_column_or_expression'


def _extract_sql_query_model(statement: str, file_path: Path, line_start: int) -> list[Fact]:
    normalized = normalize_sql_for_parsing(statement)
    if not re.search(r'\bselect\b', normalized, re.IGNORECASE):
        return []
    m = re.search(r'\bselect\s+(?P<select>.*?)\s+from\s+(?P<from>[a-zA-Z0-9_.$"{}]+)', normalized, re.IGNORECASE | re.DOTALL)
    if not m:
        return []
    projection_text = ' '.join(m.group('select').split())
    source_tables = [_strip_db_identifier(m.group('from'))]
    source_tables += [_strip_db_identifier(x) for x in re.findall(r'\bjoin\s+([a-zA-Z0-9_.$"{}]+)', normalized, re.IGNORECASE)]
    source_tables = [x for i, x in enumerate(source_tables) if x and x not in source_tables[:i]]
    selected: list[dict[str, Any]] = []
    calculated: list[dict[str, Any]] = []
    for idx, expr_text in enumerate(_split_sql_projection_list(projection_text)[:200], 1):
        alias = _projection_alias(expr_text)
        kind = _projection_kind(expr_text)
        item = {'ordinal': idx, 'expression': expr_text[:500], 'alias': alias, 'projection_kind': kind}
        selected.append(item)
        if kind != 'direct_column_or_expression' or alias:
            calculated.append(item)
    filter_preview = None
    where_m = re.search(r'\bwhere\s+(?P<where>.*?)(?=\bgroup\s+by\b|\border\s+by\b|\blimit\b|$)', normalized, re.IGNORECASE | re.DOTALL)
    if where_m:
        filter_preview = ' '.join(where_m.group('where').split())[:600]
    group_by = None
    group_m = re.search(r'\bgroup\s+by\s+(?P<group>.*?)(?=\border\s+by\b|\blimit\b|$)', normalized, re.IGNORECASE | re.DOTALL)
    if group_m:
        group_by = ' '.join(group_m.group('group').split())[:500]
    return [Fact(
        fact_type='sql_query_model',
        name=f'select in {file_path.name}:{line_start}',
        properties={
            'query_kind': 'select',
            'source_tables': source_tables,
            'selected_fields': selected[:100],
            'calculated_fields': calculated[:50],
            'filters_preview': filter_preview,
            'group_by_preview': group_by,
            'statement_preview': normalized[:800],
            'evidence_maturity_level': 'confirmed',
            'parser': 'regex_sql_query_model',
        },
        evidence=[EvidenceRef(file_path=str(file_path), line_start=line_start, line_end=line_start + statement.count('\n'), snippet=statement[:1000], extractor='sql_query_model_regex')]
    )]

def scan_sql_files(files: list[Path]) -> tuple[list[Fact], dict[str, Any], list[dict[str, Any]]]:
    facts: list[Fact] = []
    warnings: list[dict[str, Any]] = []
    summary = {
        "files": 0,
        "statements": 0,
        "sqlglot": 0,
        "regex_fallback": 0,
        "failed": 0,
        "procedural_or_dynamic_warnings": 0,
        "literal_data_writes": 0,
    }

    for p in files:
        if p.suffix.lower() != ".sql":
            continue
        summary["files"] += 1
        text = read_text(p)
        for line_start, statement in split_sql_statements(text):
            summary["statements"] += 1
            normalized = normalize_sql_for_parsing(statement)
            if not normalized or is_ignorable_sql_fragment(statement):
                continue

            literal_writes = _extract_literal_data_writes(statement, p, line_start)
            if literal_writes:
                facts.extend(literal_writes)
                summary["literal_data_writes"] += len(literal_writes)
            join_candidates = _extract_join_observations(statement, p, line_start)
            if join_candidates:
                facts.extend(join_candidates)
            query_models = _extract_sql_query_model(statement, p, line_start)
            if query_models:
                facts.extend(query_models)

            if sqlglot is None:
                fb, warn = regex_fallback(statement, p, line_start)
                facts.extend(fb)
                if fb:
                    summary["regex_fallback"] += len(fb)
                if warn:
                    warn["reason"] = "sqlglot_not_installed_and_no_regex_fallback"
                    warnings.append(warn)
                    summary["failed"] += 1
                continue

            try:
                expressions = sqlglot.parse(normalized, read=None, error_level="ignore")
                parsed_any = False
                for expression in expressions or []:
                    if expression is None:
                        continue
                    parsed_any = True
                    tables = sorted({t.name for t in expression.find_all(exp.Table) if t.name}) if exp is not None else []
                    columns = sorted({c.name for c in expression.find_all(exp.Column) if c.name}) if exp is not None else []
                    kind = expression.key or expression.__class__.__name__
                    facts.append(Fact(
                        fact_type=f"sql_{kind}",
                        name=f"{kind} in {p.name}",
                        properties={**{"kind": kind, "tables": tables, "columns": columns[:300], "statement_preview": normalized[:500], "parser": "sqlglot"}, **_sql_evidence_props(parser="sqlglot", kind=kind, target=(tables[0] if tables else None), parsed=True)},
                        evidence=[EvidenceRef(file_path=str(p), line_start=line_start, line_end=line_start + statement.count("\n"), snippet=statement[:800], extractor="sqlglot")]
                    ))
                    summary["sqlglot"] += 1
                if not parsed_any:
                    fb, warn = regex_fallback(statement, p, line_start)
                    facts.extend(fb)
                    if fb:
                        summary["regex_fallback"] += len(fb)
                    if warn:
                        warnings.append(warn)
                        summary["failed"] += 1
            except Exception as exc:
                fb, warn = regex_fallback(statement, p, line_start)
                facts.extend(fb)
                if fb:
                    summary["regex_fallback"] += len(fb)
                if warn:
                    warn["exception"] = str(exc)
                    warnings.append(warn)
                    summary["failed"] += 1

    summary["procedural_or_dynamic_warnings"] = len(warnings)
    return facts, summary, warnings
