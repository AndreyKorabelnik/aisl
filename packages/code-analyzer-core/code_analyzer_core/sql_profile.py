from __future__ import annotations

import hashlib
import json
import re
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

import yaml
from yaml.nodes import MappingNode, Node, ScalarNode, SequenceNode

try:
    import sqlglot
    from sqlglot import exp
    from sqlglot.optimizer.scope import Scope as SqlglotScope, traverse_scope
except Exception:  # pragma: no cover
    sqlglot = None
    exp = None
    SqlglotScope = None
    traverse_scope = None

from code_analyzer_core import __version__ as CORE_VERSION
from code_analyzer_core.sql_artifact import (
    SQL_ANALYSIS_CONTRACT_VERSION,
    SQL_ANALYSIS_SCHEMA_VERSION,
    SQL_CANONICAL_FACTS,
    sql_analysis_content_fingerprint,
)
from code_analyzer_core.scanners.sql_scanner import (
    is_ignorable_sql_fragment,
)
from code_analyzer_core.utils import normalize_name, read_text, write_json, line_number_for_offset, snippet_around
from code_analyzer_core.evidence_contract import maturity_props, candidate_signal
from code_analyzer_core.evidence_kernel import sanitize_public_payload

SQL_PROFILE_VERSION = "1.8"

TEXT_SUFFIXES = {".sql", ".hql", ".q", ".py", ".scala", ".java", ".kt", ".yaml", ".yml", ".json", ".properties", ".conf", ".sh"}
SQL_SUFFIXES = {".sql", ".hql", ".q"}
CONFIG_SUFFIXES = {".yaml", ".yml", ".json", ".properties", ".conf", ".sh"}

COMMENT_LINE_RE = re.compile(r"--(?P<text>.*)$", re.MULTILINE)
COMMENT_BLOCK_RE = re.compile(r"/\*(?P<text>.*?)\*/", re.DOTALL)
COMMENT_ON_TABLE_RE = re.compile(r"\bcomment\s+on\s+table\s+([a-zA-Z0-9_.$\"{}]+)\s+is\s+(['\"])(.*?)\2", re.IGNORECASE | re.DOTALL)
COMMENT_ON_COLUMN_RE = re.compile(r"\bcomment\s+on\s+column\s+([a-zA-Z0-9_.$\"{}]+)\s+is\s+(['\"])(.*?)\2", re.IGNORECASE | re.DOTALL)
TABLE_COMMENT_RE = re.compile(r"\bcomment\s+(['\"])(.*?)\1", re.IGNORECASE | re.DOTALL)

EMBEDDED_SQL_PATTERNS = [
    re.compile(r"spark\.sql\s*\(\s*(?P<quote>\"\"\"|'''|\"|')(?P<sql>.*?)(?P=quote)\s*\)", re.DOTALL | re.IGNORECASE),
    re.compile(r"sqlContext\.sql\s*\(\s*(?P<quote>\"\"\"|'''|\"|')(?P<sql>.*?)(?P=quote)\s*\)", re.DOTALL | re.IGNORECASE),
    re.compile(r"session\.sql\s*\(\s*(?P<quote>\"\"\"|'''|\"|')(?P<sql>.*?)(?P=quote)\s*\)", re.DOTALL | re.IGNORECASE),
    re.compile(r"(?P<name>query|sql|hql|statement)\s*=\s*(?P<quote>\"\"\"|'''|\"|')(?P<sql>.*?)(?P=quote)", re.DOTALL | re.IGNORECASE),
]

OBJECT_NAME_RE = r"[a-zA-Z0-9_.$\"{}:-]+"
CREATE_TABLE_RE = re.compile(rf"\bcreate\s+(?:external\s+)?table\s+(?:if\s+not\s+exists\s+)?(?P<name>{OBJECT_NAME_RE})", re.IGNORECASE)
CREATE_VIEW_RE = re.compile(rf"\bcreate\s+(?:or\s+replace\s+)?(?:materialized\s+)?view\s+(?:if\s+not\s+exists\s+)?(?P<name>{OBJECT_NAME_RE})", re.IGNORECASE)
INSERT_RE = re.compile(rf"\binsert\s+(?:overwrite\s+table|overwrite|into\s+table|into)\s+(?P<name>{OBJECT_NAME_RE})", re.IGNORECASE)
MERGE_RE = re.compile(rf"\bmerge\s+into\s+(?P<name>{OBJECT_NAME_RE})", re.IGNORECASE)
UPDATE_RE = re.compile(rf"\bupdate\s+(?P<name>{OBJECT_NAME_RE})", re.IGNORECASE)
DELETE_RE = re.compile(rf"\bdelete\s+from\s+(?P<name>{OBJECT_NAME_RE})", re.IGNORECASE)
FROM_JOIN_RE = re.compile(rf"\b(?:from|join)\s+(?P<name>{OBJECT_NAME_RE})(?:\s+(?:as\s+)?(?P<alias>[a-zA-Z_][a-zA-Z0-9_]*))?", re.IGNORECASE)
CTE_RE = re.compile(r"(?:with|,)\s+(?P<name>[a-zA-Z_][a-zA-Z0-9_]*)\s+as\s*\(", re.IGNORECASE)
COLUMN_ALIAS_RE = re.compile(r"\bas\s+([a-zA-Z_][a-zA-Z0-9_]*)\b", re.IGNORECASE)
PARTITION_RE = re.compile(r"\bpartition(?:ed)?\s+by\s*\((?P<body>[^)]*)\)", re.IGNORECASE | re.DOTALL)
JOIN_CONDITION_RE = re.compile(r"\bjoin\s+[^\n]+?\s+on\s+(?P<cond>.*?)(?=\bjoin\b|\bwhere\b|\bgroup\s+by\b|\border\s+by\b|\bhaving\b|$)", re.IGNORECASE | re.DOTALL)
WHERE_RE = re.compile(r"\bwhere\s+(?P<body>.*?)(?=\bgroup\s+by\b|\border\s+by\b|\bhaving\b|\bqualify\b|$)", re.IGNORECASE | re.DOTALL)
GROUP_BY_RE = re.compile(r"\bgroup\s+by\s+(?P<body>.*?)(?=\border\s+by\b|\bhaving\b|\bqualify\b|$)", re.IGNORECASE | re.DOTALL)
SQL_PLACEHOLDER_RE = re.compile(r"\$\{(?P<name>[^}]+)\}|\{\{\s*(?P<jinja>[^}]+?)\s*\}\}|%\((?P<py>[^)]+)\)s")
BARE_DSL_VARIABLE_RE = re.compile(r"(?<![\w$])\$(?P<name>[a-zA-Z_][a-zA-Z0-9_.]*(?:\[[^\]]+\])?)")

SQL_TOP_LEVEL_KEYWORDS = {
    "select", "with", "insert", "create", "merge", "update", "delete",
    "drop", "alter", "truncate", "msck", "analyze", "refresh", "cache",
    "uncache", "explain", "describe", "desc", "show", "grant", "revoke",
    "use", "set",
}
SCRIPT_CONTROL_KEYWORDS = {
    "if", "elif", "else", "for", "while", "loop", "begin", "end",
    "try", "catch", "then", "do",
}
SCRIPT_ASSIGNMENT_KEYWORDS = {"let", "var", "const"}
SCRIPT_LOGGING_KEYWORDS = {"log_info", "log_error", "log_warn", "log_warning", "echo"}
SCRIPT_ERROR_KEYWORDS = {"raise", "throw", "return", "exit"}
SQL_KEYWORD_RE = re.compile(
    r"\b(select|with|insert|create|merge|update|delete|drop|alter|truncate)\b",
    re.IGNORECASE,
)
SQL_PATH_RE = re.compile(r"['\"](?P<path>[^'\"]+\.(?:sql|hql|q))['\"]", re.IGNORECASE)
CONFIG_PATH_RE = re.compile(r"['\"](?P<path>[^'\"]+\.(?:ya?ml|json|properties|conf))['\"]", re.IGNORECASE)

IDENTIFIER_TOKENS = ("id", "key", "ucp", "guid", "uuid", "object", "entity", "client", "profile", "account", "card", "phone", "agreement", "correlation", "event")
STATUS_TOKENS = ("status", "state", "result", "error", "reason", "code", "success", "fail", "failed", "reject")
TIME_TOKENS = ("dt", "date", "time", "timestamp", "valid", "effective", "load", "created", "updated", "business")
AUDIT_TOKENS = ("created_by", "updated_by", "deleted", "actual", "version", "hash", "source")

OPTIMIZATION_PATTERNS = [
    ("select_star", re.compile(r"\bselect\s+\*", re.IGNORECASE), "SELECT * may increase scan volume and make lineage less explicit"),
    ("insert_overwrite", re.compile(r"\binsert\s+overwrite\b", re.IGNORECASE), "INSERT OVERWRITE may imply full/partition rewrite; verify incremental strategy"),
    ("cross_join", re.compile(r"\bcross\s+join\b", re.IGNORECASE), "CROSS JOIN can be expensive"),
    ("distinct", re.compile(r"\bselect\s+distinct\b|\bdistinct\s*\(", re.IGNORECASE), "DISTINCT after joins can hide duplication and increase shuffle"),
    ("window_function", re.compile(r"\bover\s*\(\s*partition\s+by\b", re.IGNORECASE), "Window function detected; check partitioning and sort keys"),
    ("many_joins", re.compile(r"\bjoin\b", re.IGNORECASE), "Many joins may be expensive or affect grain"),
    ("order_by", re.compile(r"\border\s+by\b", re.IGNORECASE), "ORDER BY may be expensive in Spark SQL unless required"),
    ("union_all", re.compile(r"\bunion\s+all\b", re.IGNORECASE), "UNION ALL combines branches; check grain and duplicate rules"),
]

PATTERN_HINTS = [
    ("transaction_outcome_split", re.compile(r"\b(success|successful|fail|failed|failure|error|reject|rejected|declined)\b", re.IGNORECASE), "success/error/reject outcome naming or filtering"),
    ("history_current_split", re.compile(r"\b(hist|history|curr|current|actual|valid_from|valid_to|effective_from|effective_to)\b", re.IGNORECASE), "current/history or temporal pattern"),
    ("staging_processed_split", re.compile(r"\b(raw|stg|stage|staging|ods|processed|mart|dm_)\b", re.IGNORECASE), "raw/staging/processed/mart layering"),
    ("error_or_retry_structure", re.compile(r"\b(retry|dead[_-]?letter|dlq|error|failed|reject)\b", re.IGNORECASE), "error/retry/dead-letter/reject structure"),
    ("outbox_or_publication_structure", re.compile(r"\b(outbox|inbox|publish|publication|sent_flg|message_id|topic)\b", re.IGNORECASE), "outbox/inbox/publication structure"),
    ("dedup_or_idempotency", re.compile(r"\b(row_number\s*\(|rank\s*\(|dedup|duplicate|idempot|correlation|event_id|message_id)\b", re.IGNORECASE), "deduplication or idempotency hint"),
]


def _rel(repo: Path, path: Path) -> str:
    try:
        return str(path.relative_to(repo)).replace("\\", "/")
    except Exception:
        return str(path).replace("\\", "/")


def _hash(value: str, n: int = 12) -> str:
    return hashlib.sha256(value.encode("utf-8", errors="ignore")).hexdigest()[:n]


def _clean_object_name(value: str | None) -> str | None:
    if not value:
        return None
    s = str(value).strip().strip(";,").strip()
    s = s.strip('"`[]')
    if not s or s.lower() in {"select", "where", "on", "as"}:
        return None
    return s


def _canonical_object(value: str | None) -> str | None:
    s = _clean_object_name(value)
    if not s:
        return None
    # Placeholder identity is part of the logical relation identity.  Do not
    # collapse `${source_schema}` and `${target_schema}` into the same object.
    return s.lower()


def _split_columns_csv(body: str) -> list[str]:
    out: list[str] = []
    buf: list[str] = []
    depth = 0
    quote: str | None = None
    for ch in body:
        if quote:
            buf.append(ch)
            if ch == quote:
                quote = None
            continue
        if ch in {"'", '"', '`'}:
            quote = ch
            buf.append(ch)
            continue
        if ch == '(':
            depth += 1
            buf.append(ch)
            continue
        if ch == ')':
            depth = max(0, depth - 1)
            buf.append(ch)
            continue
        if ch == ',' and depth == 0:
            part = ''.join(buf).strip()
            if part:
                out.append(part)
            buf = []
            continue
        buf.append(ch)
    part = ''.join(buf).strip()
    if part:
        out.append(part)
    return out


def _extract_target(statement: str) -> tuple[str | None, str | None]:
    for kind, rx in [
        ("create_table", CREATE_TABLE_RE),
        ("create_view", CREATE_VIEW_RE),
        ("insert", INSERT_RE),
        ("merge", MERGE_RE),
        ("update", UPDATE_RE),
        ("delete", DELETE_RE),
    ]:
        m = rx.search(statement)
        if m:
            return _canonical_object(m.group("name")), kind
    return None, None



def _normalize_placeholder_name(value: str) -> str:
    return str(value or "").strip().lstrip("$").strip()


def _placeholder_name(match: re.Match[str]) -> str:
    return _normalize_placeholder_name(str(match.group("name") or match.group("jinja") or match.group("py") or ""))


def _placeholder_occurrences(text: str) -> list[dict[str, Any]]:
    occurrences: list[dict[str, Any]] = []
    occupied: list[tuple[int, int]] = []
    for match in SQL_PLACEHOLDER_RE.finditer(text):
        name = _placeholder_name(match)
        if not name:
            continue
        occurrences.append({
            "name": name,
            "raw": match.group(0),
            "start": match.start(),
            "end": match.end(),
            "syntax": "braced_or_template",
        })
        occupied.append((match.start(), match.end()))
    for match in BARE_DSL_VARIABLE_RE.finditer(text):
        if any(start <= match.start() < end for start, end in occupied):
            continue
        name = _normalize_placeholder_name(match.group("name"))
        if not name:
            continue
        occurrences.append({
            "name": name,
            "raw": match.group(0),
            "start": match.start(),
            "end": match.end(),
            "syntax": "bare_dsl_variable",
        })
    return sorted(occurrences, key=lambda item: (item["start"], item["end"]))


def _find_placeholders(text: str) -> list[str]:
    return sorted({item["name"] for item in _placeholder_occurrences(text)})


def _strip_sql_comments_preserving_literals(text: str) -> str:
    """Remove SQL comments without touching comment markers inside literals.

    Comment characters are replaced with spaces while newlines are preserved.  This
    keeps line offsets stable for evidence and prevents values such as ``'--'`` or
    ``'/* literal */'`` from being truncated before sqlglot sees them.
    """
    out = list(text)
    quote: str | None = None
    dollar_delimiter: str | None = None
    in_line_comment = False
    in_block_comment = False
    i = 0

    while i < len(text):
        ch = text[i]
        nxt = text[i + 1] if i + 1 < len(text) else ""

        if in_line_comment:
            if ch == "\n":
                in_line_comment = False
            else:
                out[i] = " "
            i += 1
            continue

        if in_block_comment:
            if ch == "*" and nxt == "/":
                out[i] = " "
                out[i + 1] = " "
                i += 2
                in_block_comment = False
                continue
            if ch != "\n":
                out[i] = " "
            i += 1
            continue

        if dollar_delimiter is not None:
            if text.startswith(dollar_delimiter, i):
                i += len(dollar_delimiter)
                dollar_delimiter = None
            else:
                i += 1
            continue

        if quote is not None:
            if ch == quote:
                if nxt == quote:
                    i += 2
                    continue
                quote = None
                i += 1
                continue
            if ch == "\\" and nxt:
                i += 2
                continue
            i += 1
            continue

        if ch == "-" and nxt == "-":
            out[i] = " "
            out[i + 1] = " "
            i += 2
            in_line_comment = True
            continue

        if ch == "/" and nxt == "*":
            out[i] = " "
            out[i + 1] = " "
            i += 2
            in_block_comment = True
            continue

        if ch in {"'", '"', "`"}:
            quote = ch
            i += 1
            continue

        if ch == "$":
            match = re.match(r"\$[a-zA-Z_][a-zA-Z0-9_]*\$|\$\$", text[i:])
            if match:
                dollar_delimiter = match.group(0)
                i += len(dollar_delimiter)
                continue

        i += 1

    return "".join(out)


def _is_select_prefix_placeholder_fragment(sql: str, item: dict[str, Any]) -> bool:
    """Return true for a dynamic SELECT prefix that cannot be parsed as a column.

    Datamart DSLs commonly inject optimizer hints or a comma-terminated projection
    fragment immediately after ``SELECT``. Replacing such a placeholder with a bare
    identifier makes SQLGlot interpret the following qualified column as its alias and
    silently discard the rest of the statement. The placeholder remains a semantic
    fact, but is omitted from the parser view when a static projection follows without
    an explicit comma.
    """
    start = int(item.get("start") or 0)
    end = int(item.get("end") or start)
    masked = _mask_literals_and_comments(sql)
    prefix = masked[:start]
    if not re.search(r"\bselect(?:\s+(?:distinct|all))?\s*$", prefix, re.IGNORECASE):
        return False
    suffix = masked[end:].lstrip()
    if not suffix:
        return False
    if suffix.startswith(",") or suffix.startswith(")"):
        return False
    if re.match(r"(?i)^from\b", suffix):
        return False
    return True


def _is_relation_suffix_fragment_placeholder(sql: str, item: dict[str, Any]) -> bool:
    """Return true for a standalone dynamic SQL fragment after a FROM relation.

    Some SQL DSLs inject an optional JOIN/filter fragment on its own line immediately
    after a complete ``FROM <relation> [alias]`` clause. Replacing that fragment with
    a bare placeholder identifier makes SQLGlot accept only the leading CTE and drop
    the remaining WITH query. The placeholder remains published as semantic evidence;
    only the parser view omits the unknown fragment. Whole relation placeholders such
    as ``FROM ${source_table}`` are intentionally not matched.
    """
    start = int(item.get("start") or 0)
    end = int(item.get("end") or start)
    masked = _mask_literals_and_comments(sql)
    line_start = masked.rfind("\n", 0, start) + 1
    line_end = masked.find("\n", end)
    if line_end < 0:
        line_end = len(masked)
    if masked[line_start:start].strip() or masked[end:line_end].strip():
        return False
    prefix = masked[:line_start].rstrip()
    # Require a statically complete FROM relation directly before the fragment.
    # This keeps placeholders used as relation identities or SELECT/WHERE expressions
    # in the parser view instead of silently erasing them.
    return bool(re.search(
        r"(?is)\bfrom\s+[a-zA-Z0-9_.$`\"{}-]+(?:\s+(?:as\s+)?[a-zA-Z_][a-zA-Z0-9_]*)?\s*$",
        prefix,
    ))


def _normalize_sql_for_profile(sql: str) -> tuple[str, dict[str, str]]:
    """Create parser-safe SQL without losing logical placeholder identity."""
    replacements: dict[str, str] = {}
    occurrences = _placeholder_occurrences(sql)
    by_raw: dict[str, str] = {}
    pieces: list[str] = []
    cursor = 0
    for item in occurrences:
        raw = str(item["raw"])
        token = by_raw.get(raw)
        if token is None:
            stem = re.sub(r"[^a-zA-Z0-9_]+", "_", item["name"]).strip("_").lower() or "value"
            token = f"__sqlph_{stem[:48]}_{_hash(raw, n=8)}"
            by_raw[raw] = token
        start = int(item["start"])
        end = int(item["end"])
        pieces.append(sql[cursor:start])
        if _is_select_prefix_placeholder_fragment(sql, item) or _is_relation_suffix_fragment_placeholder(sql, item):
            pieces.append(" " * max(0, end - start))
        else:
            pieces.append(token)
            replacements[token.lower()] = raw
        cursor = end
    pieces.append(sql[cursor:])
    rendered = "".join(pieces)
    rendered = _strip_sql_comments_preserving_literals(rendered)
    return rendered.strip(), replacements


def _restore_sql_placeholders(value: str | None, replacements: dict[str, str]) -> str | None:
    if value is None:
        return None
    rendered = str(value)
    for token, raw in sorted(replacements.items(), key=lambda pair: len(pair[0]), reverse=True):
        rendered = re.sub(re.escape(token), lambda _m, raw=raw: raw, rendered, flags=re.IGNORECASE)
    return rendered


def _relation_semantics(value: str | None) -> dict[str, Any]:
    name = str(value or "")
    placeholders = _find_placeholders(name)
    last_part = name.rsplit(".", 1)[-1].strip('`"') if name else None
    logical_name = None if (last_part and _find_placeholders(last_part)) else last_part
    return {
        "relation_kind": "physical_template" if placeholders else "physical",
        "template_name": name or None,
        "logical_name": logical_name,
        "placeholder_refs": placeholders,
    }


def _sql_profile_query_contract(*, operation: str | None, target: str | None, has_source_objects: bool, unresolved_placeholders: bool = False) -> dict[str, Any]:
    is_write = str(operation or "").lower() in {"insert", "update", "merge", "delete", "create", "create_table", "create_view"}
    return maturity_props({
        "sql_statement": "confirmed",
        "persistence_write": "confirmed" if is_write and target and not unresolved_placeholders else ("unresolved" if is_write else "not_applicable"),
        "physical_storage": "confirmed" if target and not unresolved_placeholders else ("unresolved" if is_write else "not_applicable"),
        "field_mapping": "confirmed" if has_source_objects and target and not unresolved_placeholders else ("unresolved" if is_write else "not_applicable"),
        "source_boundary": "not_applicable",
        "end_to_end_trace": "not_applicable",
    }, notes=["SQL profile uses strict evidence contract: parsed SQL objects are confirmed; unresolved placeholders/dynamic lineage remain gaps and may require source-open on concrete SQL lines."])


def _sql_navigation_signal(*, signal_type: str, target: str | None, basis: str, recommended_action: str) -> dict[str, Any]:
    return candidate_signal(
        signal_type=signal_type,
        target=target,
        basis=basis,
        recommended_action=recommended_action,
        requires_source_inspection=True,
    )


def _extract_comments(text: str, file_path: str, repo_id: str) -> list[dict[str, Any]]:
    comments: list[dict[str, Any]] = []
    for m in COMMENT_LINE_RE.finditer(text):
        body = m.group("text").strip()
        if not body:
            continue
        line = line_number_for_offset(text, m.start())
        comments.append({
            "comment_id": f"comment_{repo_id}_{_hash(file_path + ':' + str(line) + body)}",
            "repo_id": repo_id,
            "file": file_path,
            "line_start": line,
            "line_end": line,
            "comment_type": "line",
            "comment_text": body[:2000],
            "attached_to": "nearby_sql",
            "near_object": None,
        })
    for m in COMMENT_BLOCK_RE.finditer(text):
        body = " ".join(m.group("text").strip().split())
        if not body:
            continue
        line = line_number_for_offset(text, m.start())
        comments.append({
            "comment_id": f"comment_{repo_id}_{_hash(file_path + ':' + str(line) + body)}",
            "repo_id": repo_id,
            "file": file_path,
            "line_start": line,
            "line_end": line + m.group(0).count("\n"),
            "comment_type": "block",
            "comment_text": body[:2000],
            "attached_to": "nearby_sql",
            "near_object": None,
        })
    for rx, typ in [(COMMENT_ON_TABLE_RE, "table_comment"), (COMMENT_ON_COLUMN_RE, "column_comment")]:
        for m in rx.finditer(text):
            obj = _canonical_object(m.group(1))
            body = " ".join(m.group(3).strip().split())
            line = line_number_for_offset(text, m.start())
            comments.append({
                "comment_id": f"comment_{repo_id}_{_hash(file_path + ':' + str(line) + str(obj) + body)}",
                "repo_id": repo_id,
                "file": file_path,
                "line_start": line,
                "line_end": line + m.group(0).count("\n"),
                "comment_type": typ,
                "comment_text": body[:2000],
                "attached_to": "table" if typ == "table_comment" else "column",
                "near_object": obj,
            })
    return comments


def _split_sql_script_fragments(text: str) -> list[tuple[int, str]]:
    """Split a mixed SQL/DSL file on semicolons outside strings and comments.

    The previous line-oriented splitter only ended a statement when a physical line
    ended with ``;``.  In the datamart DSL several assignments share a line or a DSL
    assignment is followed by SQL before the next line-ending semicolon.  That merged
    unrelated constructs and caused sqlglot to publish them as ``alias``/``anonymous``
    SQL queries.
    """
    out: list[tuple[int, str]] = []
    buf: list[str] = []
    line = 1
    start_line = 1
    quote: str | None = None
    in_line_comment = False
    in_block_comment = False
    in_dollar_quote = False
    has_content = False
    i = 0

    def flush() -> None:
        nonlocal buf, start_line, has_content
        statement = "".join(buf).strip()
        if statement:
            out.append((start_line, statement))
        buf = []
        has_content = False

    while i < len(text):
        ch = text[i]
        nxt = text[i + 1] if i + 1 < len(text) else ""
        if not has_content and not ch.isspace():
            start_line = line
            has_content = True

        if in_line_comment:
            buf.append(ch)
            if ch == "\n":
                in_line_comment = False
                line += 1
            i += 1
            continue
        if in_block_comment:
            buf.append(ch)
            if ch == "*" and nxt == "/":
                buf.append(nxt)
                i += 2
                in_block_comment = False
                continue
            if ch == "\n":
                line += 1
            i += 1
            continue
        if in_dollar_quote:
            if ch == "$" and nxt == "$":
                buf.extend([ch, nxt])
                i += 2
                in_dollar_quote = False
                continue
            buf.append(ch)
            if ch == "\n":
                line += 1
            i += 1
            continue
        if quote:
            buf.append(ch)
            if ch == quote:
                if nxt == quote:
                    buf.append(nxt)
                    i += 2
                    continue
                quote = None
            elif ch == "\\" and nxt:
                buf.append(nxt)
                i += 2
                continue
            if ch == "\n":
                line += 1
            i += 1
            continue

        if ch == "-" and nxt == "-":
            buf.extend([ch, nxt])
            i += 2
            in_line_comment = True
            continue
        if ch == "/" and nxt == "*":
            buf.extend([ch, nxt])
            i += 2
            in_block_comment = True
            continue
        if ch == "$" and nxt == "$":
            buf.extend([ch, nxt])
            i += 2
            in_dollar_quote = True
            continue
        if ch in {"'", '"', "`"}:
            quote = ch
            buf.append(ch)
            i += 1
            continue
        if ch == ";":
            flush()
            i += 1
            continue

        buf.append(ch)
        if ch == "\n":
            line += 1
        i += 1

    flush()

    # Some repository DSLs terminate control-flow blocks without a semicolon
    # (for example ``end loop``) and immediately start a ``let`` assignment.
    # The generic semicolon splitter therefore sees ``end ...\nlet ...`` as one
    # control-flow fragment and the assignment occurrence is lost.  Preserve
    # both observed statements by splitting only when the prefix ends in an
    # explicit control-flow terminator.  Do not split ordinary SQL ``CASE END``.
    normalized: list[tuple[int, str]] = []
    tail_let_re = re.compile(r"(?im)^[ \t]*let\s+[$A-Za-z_][A-Za-z0-9_.]*(?:\[[^\]]+\])?\s*=")
    control_end_re = re.compile(r"(?im)(?:^|\n)[ \t]*end(?:[ \t]+(?:loop|if|while|for|try|catch))?[ \t]*$")
    for fragment_line, fragment in out:
        matches = list(tail_let_re.finditer(fragment))
        split_at = None
        for match in matches:
            if match.start() == 0:
                continue
            prefix = fragment[:match.start()].rstrip()
            end_matches = list(control_end_re.finditer(prefix))
            if end_matches and end_matches[-1].end() == len(prefix):
                split_at = match.start()
                break
        if split_at is None:
            normalized.append((fragment_line, fragment))
            continue
        prefix = fragment[:split_at].strip()
        tail = fragment[split_at:].strip()
        if prefix:
            normalized.append((fragment_line, prefix))
        if tail:
            tail_line = fragment_line + fragment[:split_at].count("\n")
            normalized.append((tail_line, tail))
    return normalized


def _leading_statement_token(statement: str) -> str | None:
    cleaned = COMMENT_BLOCK_RE.sub(" ", statement)
    cleaned = COMMENT_LINE_RE.sub(" ", cleaned).lstrip()
    cleaned = re.sub(r"^[()]+\s*", "", cleaned)
    match = re.match(r"([a-zA-Z_][a-zA-Z0-9_]*)", cleaned)
    return match.group(1).lower() if match else None


def _mask_literals_and_comments(text: str) -> str:
    """Return text with literals/comments replaced by spaces while preserving offsets."""
    chars = list(text)
    quote: str | None = None
    in_line_comment = False
    in_block_comment = False
    i = 0
    while i < len(chars):
        ch = chars[i]
        nxt = chars[i + 1] if i + 1 < len(chars) else ""
        if in_line_comment:
            if ch == "\n":
                in_line_comment = False
            else:
                chars[i] = " "
            i += 1
            continue
        if in_block_comment:
            chars[i] = " "
            if ch == "*" and nxt == "/":
                chars[i + 1] = " "
                i += 2
                in_block_comment = False
                continue
            i += 1
            continue
        if quote:
            chars[i] = " "
            if ch == quote:
                if nxt == quote:
                    chars[i + 1] = " "
                    i += 2
                    continue
                quote = None
            elif ch == "\\" and nxt:
                chars[i + 1] = " "
                i += 2
                continue
            i += 1
            continue
        if ch == "-" and nxt == "-":
            chars[i] = chars[i + 1] = " "
            i += 2
            in_line_comment = True
            continue
        if ch == "/" and nxt == "*":
            chars[i] = chars[i + 1] = " "
            i += 2
            in_block_comment = True
            continue
        if ch in {"'", '"', "`"}:
            chars[i] = " "
            quote = ch
        i += 1
    return "".join(chars)


def _classify_script_fragment(statement: str) -> dict[str, Any]:
    token = _leading_statement_token(statement)
    masked = _mask_literals_and_comments(statement)
    sql_matches = list(SQL_KEYWORD_RE.finditer(masked))
    embedded_keywords = sorted({m.group(1).lower() for m in sql_matches})
    first_embedded = sql_matches[0] if sql_matches else None
    sql_paths = sorted({
        path
        for path in (m.group("path").replace("\\", "/") for m in SQL_PATH_RE.finditer(statement))
        if path and not re.search(r"\s", path)
    })

    if token in SQL_TOP_LEVEL_KEYWORDS:
        return {
            "classification": "sql",
            "statement_kind": "sql_statement",
            "leading_token": token,
            "contains_embedded_sql": False,
            "embedded_sql_keywords": [],
            "embedded_sql_first_keyword": None,
            "embedded_sql_preview": None,
            "referenced_sql_paths": sql_paths,
        }
    if token in SCRIPT_ASSIGNMENT_KEYWORDS:
        kind = "assignment"
    elif token in SCRIPT_CONTROL_KEYWORDS:
        kind = "control_flow"
    elif token in SCRIPT_LOGGING_KEYWORDS:
        kind = "logging"
    elif token in SCRIPT_ERROR_KEYWORDS:
        kind = "error_handling"
    elif token and re.match(
        rf"\s*{re.escape(token)}\s*\(", _strip_leading_script_comments(statement), re.IGNORECASE
    ):
        kind = "invocation"
    elif token is None:
        kind = "unknown_script"
    elif token in {"publish"}:
        kind = "invocation"
    else:
        kind = "script_expression"

    embedded_preview = None
    first_keyword = None
    if first_embedded:
        first_keyword = first_embedded.group(1).lower()
        embedded_preview = " ".join(statement[first_embedded.start():].split())[:2000]
    return {
        "classification": "script",
        "statement_kind": kind,
        "leading_token": token,
        "contains_embedded_sql": bool(first_embedded),
        "embedded_sql_keywords": embedded_keywords,
        "embedded_sql_first_keyword": first_keyword,
        "embedded_sql_preview": embedded_preview,
        "referenced_sql_paths": sql_paths,
    }


def _script_statement_fact(
    *,
    repo_id: str,
    file: str,
    absolute_file: str,
    line_start: int,
    statement: str,
    classification: dict[str, Any],
) -> dict[str, Any]:
    line_end = line_start + statement.count("\n")
    identity = f"{repo_id}|{file}|{line_start}|{statement}"
    return {
        "sql_script_statement_id": f"sql_script_statement_{repo_id}_{_hash(identity, n=16)}",
        "fact_type": "sql_script_statement",
        "repo_id": repo_id,
        "file": file,
        "line_start": line_start,
        "line_end": line_end,
        "statement_kind": classification.get("statement_kind"),
        "leading_token": classification.get("leading_token"),
        "contains_embedded_sql": bool(classification.get("contains_embedded_sql")),
        "embedded_sql_keywords": classification.get("embedded_sql_keywords") or [],
        "embedded_sql_first_keyword": classification.get("embedded_sql_first_keyword"),
        "embedded_sql_preview": classification.get("embedded_sql_preview"),
        "referenced_sql_paths": classification.get("referenced_sql_paths") or [],
        "statement_preview": " ".join(statement.split())[:1500],
        "evidence": [{
            "file": str(Path(absolute_file)),
            "relative_file": file,
            "line_start": line_start,
            "line_end": line_end,
            "extractor": "sql_script_structure",
            "snippet": statement[:4000],
        }],
        **maturity_props({
            "sql_statement": "not_applicable",
            "persistence_write": "not_applicable",
            "physical_storage": "not_applicable",
            "field_mapping": "not_applicable",
            "source_boundary": "not_applicable",
            "end_to_end_trace": "not_applicable",
        }, notes=["Mixed SQL/DSL file fragment is preserved as script evidence and is not published as a top-level SQL query."]),
    }



def _split_script_call_arguments(text: str) -> list[str]:
    """Split a DSL call argument list without interpreting argument semantics."""
    out: list[str] = []
    start = 0
    depth = 0
    quote: str | None = None
    escape = False
    for index, ch in enumerate(text):
        if quote:
            if escape:
                escape = False
                continue
            if ch == "\\":
                escape = True
                continue
            if ch == quote:
                quote = None
            continue
        if ch in {"'", '"', "`"}:
            quote = ch
            continue
        if ch in "([{":
            depth += 1
            continue
        if ch in ")]}":
            depth = max(0, depth - 1)
            continue
        if ch == "," and depth == 0:
            item = text[start:index].strip()
            if item:
                out.append(item)
            start = index + 1
    tail = text[start:].strip()
    if tail:
        out.append(tail)
    return out


def _iter_call_payloads(statement: str) -> list[tuple[str, str, int]]:
    """Return observed call syntax anywhere in one DSL statement.

    The extractor is lexical and deliberately assigns no semantics to symbols.
    Calls nested inside control-flow statements are retained because they may
    reference repository artifacts or other execution inputs.  Quoted literals
    and comments are masked before call starts are detected.
    """
    masked = _mask_literals_and_comments(statement)
    starts = list(re.finditer(r"(?<![A-Za-z0-9_.])(?P<symbol>[A-Za-z_][A-Za-z0-9_.]*)\s*\(", masked))
    out: list[tuple[str, str, int]] = []
    for match in starts:
        symbol = str(match.group("symbol") or "")
        open_index = masked.find("(", match.start("symbol") + len(symbol))
        if open_index < 0:
            continue
        depth = 0
        quote: str | None = None
        escape = False
        close_index: int | None = None
        for index in range(open_index, len(statement)):
            ch = statement[index]
            if quote:
                if escape:
                    escape = False
                    continue
                if ch == "\\":
                    escape = True
                    continue
                if ch == quote:
                    quote = None
                continue
            if ch in {"'", '"', "`"}:
                quote = ch
                continue
            if ch == "(":
                depth += 1
            elif ch == ")":
                depth -= 1
                if depth == 0:
                    close_index = index
                    break
        if close_index is not None:
            out.append((symbol, statement[open_index + 1:close_index], match.start("symbol")))
    return out


def _outer_call_payload(statement: str) -> tuple[str, str] | None:
    """Return the observed top-level DSL call symbol and raw argument payload."""
    match = re.match(
        r"^\s*(?:(?:try|then)\s+)?(?P<symbol>[A-Za-z_][A-Za-z0-9_.]*)\s*\(",
        statement,
        re.IGNORECASE | re.DOTALL,
    )
    if not match:
        return None
    symbol = str(match.group("symbol") or "")
    open_index = statement.find("(", match.start("symbol") + len(symbol))
    if open_index < 0:
        return None
    depth = 0
    quote: str | None = None
    escape = False
    close_index: int | None = None
    for index in range(open_index, len(statement)):
        ch = statement[index]
        if quote:
            if escape:
                escape = False
                continue
            if ch == "\\":
                escape = True
                continue
            if ch == quote:
                quote = None
            continue
        if ch in {"'", '"', "`"}:
            quote = ch
            continue
        if ch == "(":
            depth += 1
        elif ch == ")":
            depth -= 1
            if depth == 0:
                close_index = index
                break
    if close_index is None:
        return None
    return symbol, statement[open_index + 1:close_index]


def _build_script_calls(repo_id: str, script_statements: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Publish generic structured DSL call syntax; do not assign business semantics."""
    out: list[dict[str, Any]] = []
    for item in script_statements:
        if item.get("statement_kind") not in {"invocation", "control_flow", "logging", "error_handling"}:
            continue
        evidence = item.get("evidence") or []
        statement = str((evidence[0] if evidence else {}).get("snippet") or item.get("statement_preview") or "")
        calls = _iter_call_payloads(statement)
        for symbol, payload, call_offset in calls:
            named: dict[str, str] = {}
            positional: list[str] = []
            for argument in _split_script_call_arguments(payload):
                named_match = re.match(r"^\s*(?P<name>[A-Za-z_][A-Za-z0-9_.]*)\s*=\s*(?P<value>.*)$", argument, re.DOTALL)
                if named_match:
                    name = str(named_match.group("name") or "")
                    value = " ".join(str(named_match.group("value") or "").strip().split())[:2000]
                    if name in named:
                        # Duplicate names are preserved positionally rather than silently overwritten.
                        positional.append(" ".join(argument.split())[:2000])
                    else:
                        named[name] = value
                else:
                    positional.append(" ".join(argument.split())[:2000])
            placeholder_names = sorted({
                ref["name"]
                for value in [*named.values(), *positional]
                for ref in _placeholder_occurrences(value)
            })
            identity = f"{item.get('sql_script_statement_id')}|{call_offset}|{symbol}|{json.dumps(named, ensure_ascii=False, sort_keys=True)}|{json.dumps(positional, ensure_ascii=False, sort_keys=True)}"
            out.append({
                "sql_script_call_id": f"sql_script_call_{repo_id}_{_hash(identity, n=16)}",
                "fact_type": "sql_script_call",
                "repo_id": repo_id,
                "parent_script_statement_id": item.get("sql_script_statement_id"),
                "file": item.get("file"),
                "line_start": item.get("line_start"),
                "line_end": item.get("line_end"),
                "call_symbol": symbol,
                "named_arguments": named,
                "positional_arguments": positional,
                "referenced_placeholders": placeholder_names,
                "evidence": evidence,
                **maturity_props({
                    "sql_statement": "not_applicable",
                    "persistence_write": "not_applicable",
                    "physical_storage": "not_applicable",
                    "field_mapping": "not_applicable",
                    "source_boundary": "not_applicable",
                    "end_to_end_trace": "not_applicable",
                }, notes=["Structured DSL call syntax is observed without assigning semantics to the called symbol or argument names."]),
            })
    return out

def _strip_leading_script_comments(text: str) -> str:
    """Remove only leading SQL-style comments before DSL code; preserve literals and inline content."""
    value = str(text or "")
    pos = 0
    while True:
        while pos < len(value) and value[pos].isspace():
            pos += 1
        if value.startswith("--", pos):
            end = value.find("\n", pos + 2)
            if end < 0:
                return ""
            pos = end + 1
            continue
        if value.startswith("/*", pos):
            end = value.find("*/", pos + 2)
            if end < 0:
                return value[pos:]
            pos = end + 2
            continue
        return value[pos:]


def _split_script_string_concat(expression: str) -> list[str] | None:
    """Split one DSL ``||`` expression without interpreting arbitrary code.

    The helper is intentionally narrow: only top-level concatenation is split;
    quoted content is preserved verbatim.  An unterminated quote means the
    expression is not safe to evaluate and therefore remains unresolved.
    """
    text = str(expression or "")
    parts: list[str] = []
    start = 0
    quote: str | None = None
    escaped = False
    index = 0
    while index < len(text):
        ch = text[index]
        if quote is not None:
            if escaped:
                escaped = False
            elif ch == "\\":
                escaped = True
            elif ch == quote:
                quote = None
            index += 1
            continue
        if ch in {"'", '"'}:
            quote = ch
            index += 1
            continue
        if text.startswith("||", index):
            parts.append(text[start:index].strip())
            index += 2
            start = index
            continue
        index += 1
    if quote is not None:
        return None
    parts.append(text[start:].strip())
    return parts


def _evaluate_script_string_expression(
    expression: str,
    *,
    local_values: dict[str, str],
) -> tuple[str | None, str | None]:
    """Evaluate only exact local string concatenation.

    This is not a general DSL evaluator.  Supported operands are quoted string
    literals and references to already observed file-local scalar bindings.
    Any other operand keeps the binding unresolved.  Placeholders embedded in a
    quoted literal are retained unless an exact file-local binding for the same
    name already exists.
    """
    parts = _split_script_string_concat(expression)
    if not parts or len(parts) <= 1:
        return None, None
    rendered: list[str] = []
    reference_re = re.compile(
        r"^(?:\$\{\s*\$?(?P<braced>[A-Za-z_][A-Za-z0-9_.]*)\s*\}|"
        r"\$(?P<bare>[A-Za-z_][A-Za-z0-9_.]*))$"
    )
    for part in parts:
        item = part.strip()
        if len(item) >= 2 and item[0] == item[-1] and item[0] in {"'", '"'}:
            rendered.append(item[1:-1])
            continue
        match = reference_re.fullmatch(item)
        if not match:
            return None, None
        name = str(match.group("braced") or match.group("bare") or "").lower()
        if name not in local_values:
            return None, None
        rendered.append(local_values[name])

    value = "".join(rendered)
    # Resolve only exact local placeholders occurring inside the resulting
    # string.  Workflow/runtime placeholders stay visible for downstream
    # diagnostics and are never guessed here.
    placeholder_re = re.compile(
        r"\$\{\s*\$?(?P<braced>[A-Za-z_][A-Za-z0-9_.]*)\s*\}|"
        r"(?<![A-Za-z0-9$])\$(?P<bare>[A-Za-z_][A-Za-z0-9_.]*)"
    )
    for _ in range(16):
        changed = False

        def replace(match: re.Match[str]) -> str:
            nonlocal changed
            name = str(match.group("braced") or match.group("bare") or "").lower()
            replacement = local_values.get(name)
            if replacement is None:
                return match.group(0)
            changed = True
            return replacement

        updated = placeholder_re.sub(replace, value)
        value = updated
        if not changed:
            break
    return value, "file_local_literal_string_concatenation"


def _build_script_bindings(
    repo_id: str,
    script_statements: list[dict[str, Any]],
    *,
    raw_statements: dict[str, str] | None = None,
) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    binding_re = re.compile(
        r"^\s*let\s+(?P<name>\$?[a-zA-Z_][a-zA-Z0-9_.]*(?:\[[^\]]+\])?)\s*=\s*(?P<value>.*)$",
        re.IGNORECASE | re.DOTALL,
    )
    local_values_by_file: dict[str, dict[str, str]] = defaultdict(dict)
    ordered_statements = sorted(
        script_statements,
        key=lambda item: (
            str(item.get("file") or ""),
            int(item.get("line_start") or 0),
            str(item.get("sql_script_statement_id") or ""),
        ),
    )
    for item in ordered_statements:
        if item.get("statement_kind") != "assignment":
            continue
        evidence = item.get("evidence") or []
        statement_id = str(item.get("sql_script_statement_id") or "")
        snippet = str(
            (raw_statements or {}).get(statement_id)
            or (evidence[0] if evidence else {}).get("snippet")
            or item.get("statement_preview")
            or ""
        )
        match = binding_re.match(_strip_leading_script_comments(snippet))
        if not match:
            continue
        name = _normalize_placeholder_name(match.group("name"))
        value_expr = match.group("value").strip()
        binding_kind = "expression"
        scalar_value = None
        if re.fullmatch(r'''"(?:\\.|[^"\\])*"|'(?:\\.|[^'\\])*' ''', value_expr, re.DOTALL | re.VERBOSE):
            binding_kind = "template" if _placeholder_occurrences(value_expr[1:-1]) else "literal"
            scalar_value = value_expr[1:-1]
        elif re.fullmatch(r"-?\d+(?:\.\d+)?|true|false|null|none", value_expr, re.IGNORECASE):
            binding_kind = "literal"
            scalar_value = value_expr
        elif re.fullmatch(r"\$[a-zA-Z_][a-zA-Z0-9_.]*(?:\[[^\]]+\])?", value_expr):
            binding_kind = "reference"
            scalar_value = value_expr
        scalar_resolution_basis = None
        if scalar_value is None:
            scalar_value, scalar_resolution_basis = _evaluate_script_string_expression(
                value_expr,
                local_values=local_values_by_file[str(item.get("file") or "")],
            )
            if scalar_value is not None:
                binding_kind = "template" if _placeholder_occurrences(scalar_value) else "literal"
        if scalar_value is not None:
            local_values_by_file[str(item.get("file") or "")][name.lower()] = str(scalar_value)
        referenced = _placeholder_occurrences(value_expr)
        identity = f"{item.get('sql_script_statement_id')}|{name}|{value_expr}"
        out.append({
            "sql_script_binding_id": f"sql_script_binding_{repo_id}_{_hash(identity, n=16)}",
            "fact_type": "sql_script_binding",
            "repo_id": repo_id,
            "parent_script_statement_id": item.get("sql_script_statement_id"),
            "file": item.get("file"),
            "line_start": item.get("line_start"),
            "line_end": item.get("line_end"),
            "binding_name": name,
            "binding_kind": binding_kind,
            "scalar_value": scalar_value,
            "value_expression": " ".join(value_expr.split())[:2000],
            "scalar_resolution_basis": scalar_resolution_basis,
            "referenced_placeholders": [ref["name"] for ref in referenced],
            "is_sql_path_candidate": bool(scalar_value and re.search(r"\.(?:sql|hql|q)$", scalar_value, re.IGNORECASE)),
            "evidence": evidence,
            **maturity_props({
                "sql_statement": "not_applicable",
                "persistence_write": "not_applicable",
                "physical_storage": "not_applicable",
                "field_mapping": "not_applicable",
                "source_boundary": "not_applicable",
                "end_to_end_trace": "not_applicable",
            }, notes=["Simple local DSL binding is observed without constructing a workflow or deployment model."]),
        })
    return out


def _placeholder_usage_roles(q: dict[str, Any], raw: str, name: str) -> list[str]:
    roles: set[str] = set()
    snippet = str((q.get("evidence") or [{}])[0].get("snippet") or "")
    if raw and re.search(
        r"\bselect(?:\s+(?:distinct|all))?\s*" + re.escape(raw) + r"(?=\s+[^,])",
        _strip_sql_comments_preserving_literals(snippet),
        re.IGNORECASE,
    ):
        roles.add("select_modifier_or_projection_fragment")
    target = str(q.get("target_object") or "")
    sources = [str(item) for item in q.get("source_objects") or []]
    schema_form = bool(raw and re.search(re.escape(raw) + r"\s*\.\s*[a-zA-Z_]", str((q.get("evidence") or [{}])[0].get("snippet") or "")))
    if raw and raw in target:
        roles.add("relation_schema" if schema_form else "target_relation")
    if raw and any(raw in source for source in sources):
        roles.add("relation_schema" if schema_form else "source_relation")
    if raw and raw in str(q.get("where_clause") or ""):
        roles.add("predicate")
    if raw and any(raw in str(cond) for cond in q.get("join_conditions") or []):
        roles.add("join_predicate")
    for col in q.get("target_columns") or []:
        if raw and raw in str(col.get("column") or ""):
            roles.add("target_column")
        if raw and raw in str(col.get("expression") or ""):
            roles.add("expression")
    if not roles:
        # Infer a relation-schema placeholder from the common `${schema}.table` form.
        if raw and re.search(re.escape(raw) + r"\s*\.\s*[a-zA-Z_]", snippet):
            roles.add("relation_schema")
    return sorted(roles or {"unknown"})


def _build_embedded_sql_facts(repo_id: str, script_statements: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    schema_keywords = {"create", "drop", "alter", "truncate"}
    write_keywords = {"insert", "merge", "update", "delete"}
    for parent in script_statements:
        keyword = str(parent.get("embedded_sql_first_keyword") or "").lower()
        preview = parent.get("embedded_sql_preview")
        if not keyword or not preview:
            continue
        if keyword in schema_keywords:
            role = "schema_definition_or_change"
            affects_graph = True
        elif keyword in write_keywords:
            role = "data_write"
            affects_graph = True
        elif keyword in {"select", "with"}:
            role = "script_value_query"
            affects_graph = False
        else:
            role = "other_sql"
            affects_graph = False
        identity = f"{parent.get('sql_script_statement_id')}|{keyword}|{preview}"
        out.append({
            "sql_script_embedded_sql_id": f"sql_script_embedded_sql_{repo_id}_{_hash(identity, n=16)}",
            "fact_type": "sql_script_embedded_sql",
            "repo_id": repo_id,
            "parent_script_statement_id": parent.get("sql_script_statement_id"),
            "file": parent.get("file"),
            "line_start": parent.get("line_start"),
            "line_end": parent.get("line_end"),
            "sql_role": role,
            "first_keyword": keyword,
            "affects_logical_sql_graph": affects_graph,
            "canonical_lineage_inclusion": "deferred",
            "sql_preview": preview,
            "evidence": parent.get("evidence") or [],
            **maturity_props({
                "sql_statement": "confirmed",
                "persistence_write": "unresolved" if role == "data_write" else "not_applicable",
                "physical_storage": "unresolved" if affects_graph else "not_applicable",
                "field_mapping": "unresolved" if role == "data_write" else "not_applicable",
                "source_boundary": "not_applicable",
                "end_to_end_trace": "not_applicable",
            }, notes=["SQL nested in a DSL statement is inventoried separately. Canonical lineage inclusion is deferred until its semantic role and placeholders are resolved."]),
        })
    return out


def _static_path_suffix(template: str) -> str:
    parts = [part for part in template.replace("\\", "/").split("/") if part and part != "."]
    # Repository config discovery must never guess a placeholder value.  Keep
    # only the exact literal suffix after the last placeholder-bearing path
    # segment, so every matching repository config remains an observed candidate.
    last_dynamic = -1
    for index, part in enumerate(parts):
        if any(marker in part for marker in ("$", "{", "}")):
            last_dynamic = index
    if last_dynamic >= 0:
        parts = parts[last_dynamic + 1:]
    return "/".join(parts)


def _build_script_invocations(
    repo_id: str,
    script_statements: list[dict[str, Any]],
    sql_units: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    available = sorted({str(unit.get("file") or "").replace("\\", "/") for unit in sql_units if unit.get("file")})
    lower_to_actual = {path.lower(): path for path in available}
    out: list[dict[str, Any]] = []
    for parent in script_statements:
        for template in parent.get("referenced_sql_paths") or []:
            normalized = str(template).replace("\\", "/").lstrip("./")
            exact = lower_to_actual.get(normalized.lower())
            candidates: list[str] = []
            basis = None
            if exact:
                candidates = [exact]
                basis = "exact_repository_relative_path"
            else:
                suffix = _static_path_suffix(normalized)
                if suffix:
                    candidates = [path for path in available if path.lower().endswith(suffix.lower())]
                    if candidates:
                        basis = "static_suffix_after_dynamic_prefix"
                if not candidates and "/" not in suffix:
                    candidates = [path for path in available if Path(path).name.lower() == suffix.lower()]
                    if candidates:
                        basis = "unique_basename" if len(candidates) == 1 else "ambiguous_basename"
            if len(candidates) == 1:
                status = "resolved"
                resolved_file = candidates[0]
            elif len(candidates) > 1:
                status = "ambiguous"
                resolved_file = None
            else:
                status = "unresolved"
                resolved_file = None
            identity = f"{parent.get('sql_script_statement_id')}|{template}"
            out.append({
                "sql_script_invocation_id": f"sql_script_invocation_{repo_id}_{_hash(identity, n=16)}",
                "fact_type": "sql_script_invocation",
                "repo_id": repo_id,
                "parent_script_statement_id": parent.get("sql_script_statement_id"),
                "file": parent.get("file"),
                "line_start": parent.get("line_start"),
                "invoked_symbol": parent.get("leading_token"),
                "invocation_kind": (
                    "direct_invocation" if parent.get("statement_kind") == "invocation"
                    else "path_binding" if parent.get("statement_kind") == "assignment"
                    else "conditional_or_nested_reference"
                ),
                "target_path_template": template,
                "resolved_file": resolved_file,
                "resolution_status": status,
                "resolution_basis": basis,
                "resolution_candidates": candidates[:20],
                "evidence": parent.get("evidence") or [],
                **maturity_props({
                    "sql_statement": "not_applicable",
                    "persistence_write": "not_applicable",
                    "physical_storage": "not_applicable",
                    "field_mapping": "not_applicable",
                    "source_boundary": "not_applicable",
                    "end_to_end_trace": "not_applicable",
                }, notes=["SQL script invocation is resolved only from repository-local path evidence; deployment metadata is not modeled."]),
            })
    return out



def _config_scalar_type(value: Any) -> str:
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "boolean"
    if isinstance(value, (int, float)):
        return "number"
    return "string"


def _config_value_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, bool):
        return "true" if value else "false"
    return str(value)


def _config_leaf_name(path: str) -> str:
    leaf = str(path or "").split(".")[-1]
    return re.sub(r"\[\d+\]$", "", leaf)


def _config_line_for(text: str, path: str, value: Any) -> int | None:
    leaf = _config_leaf_name(path)
    probes = []
    if leaf:
        probes.extend([f'"{leaf}"', f"'{leaf}'", leaf])
    value_text = _config_value_text(value)
    if value_text:
        probes.append(value_text)
    for probe in probes:
        match = re.search(re.escape(probe), text)
        if match:
            return text.count("\n", 0, match.start()) + 1
    return None


def _quote_bare_yaml_template_scalars(text: str) -> tuple[str, tuple[int, ...]]:
    """Quote only whole-line bare template scalar values so YAML remains parseable.

    This is a syntax-preserving recovery for repository configuration such as
    ``profile: {{global.PROFILE}}``.  The template token itself is preserved as
    the scalar value; no placeholder is resolved and no surrounding structure is
    inferred.  Line count is unchanged so source provenance remains exact.
    """
    pattern = re.compile(
        r"^(?P<prefix>\s*[^#\n][^:\n]*:\s*)(?P<value>\{\{[^{}\n]+\}\})(?P<suffix>\s*(?:#.*)?)$"
    )
    recovered: list[int] = []
    lines = text.splitlines(keepends=True)
    out: list[str] = []
    for line_number, line in enumerate(lines, 1):
        body = line[:-1] if line.endswith("\n") else line
        newline = "\n" if line.endswith("\n") else ""
        if body.endswith("\r"):
            body = body[:-1]
            newline = "\r" + newline
        match = pattern.match(body)
        if not match:
            out.append(line)
            continue
        value = match.group("value")
        out.append(f"{match.group('prefix')}{json.dumps(value, ensure_ascii=False)}{match.group('suffix')}{newline}")
        recovered.append(line_number)
    return "".join(out), tuple(recovered)


def _yaml_scalar_nodes(text: str) -> list[dict[str, Any]]:
    if not text.strip():
        return []
    parse_text = text
    parse_mode = "strict"
    recovered_lines: tuple[int, ...] = ()
    try:
        loaded = yaml.safe_load(parse_text)
        root = yaml.compose(parse_text, Loader=yaml.SafeLoader)
    except yaml.YAMLError:
        parse_text, recovered_lines = _quote_bare_yaml_template_scalars(text)
        if not recovered_lines:
            raise
        loaded = yaml.safe_load(parse_text)
        root = yaml.compose(parse_text, Loader=yaml.SafeLoader)
        parse_mode = "template_tolerant"
    if root is None:
        return []
    lines = text.splitlines()
    out: list[dict[str, Any]] = []

    def key_value(node: Node) -> Any:
        if not isinstance(node, ScalarNode):
            return str(getattr(node, "value", ""))
        try:
            return yaml.safe_load(node.value)
        except Exception:
            return node.value

    def walk(node: Node, value: Any, path: str, parent_path: str | None, binding_name: str | None = None) -> None:
        if isinstance(node, MappingNode) and isinstance(value, dict):
            for key_node, value_node in node.value:
                key_obj = key_value(key_node)
                key = str(key_obj)
                child_path = f"{path}.{key}" if path else key
                walk(value_node, value.get(key_obj), child_path, path or None, key)
            return
        if isinstance(node, SequenceNode) and isinstance(value, list):
            for index, value_node in enumerate(node.value):
                child_path = f"{path}[{index}]" if path else f"[{index}]"
                child_value = value[index] if index < len(value) else None
                walk(value_node, child_value, child_path, path or None, binding_name)
            return
        start = int(node.start_mark.line) + 1
        end = max(start, int(node.end_mark.line) + 1)
        snippet = "\n".join(lines[start - 1:end]).strip()[:1000]
        out.append({
            "binding_path": path or "$",
            "parent_path": parent_path,
            "binding_name": binding_name or _config_leaf_name(path),
            "scalar_value": value,
            "line_start": start,
            "line_end": end,
            "raw_snippet": snippet or None,
            "parse_mode": parse_mode,
            "recovered_template_lines": list(recovered_lines),
        })

    walk(root, loaded, "", None)
    return out


def _generic_scalar_nodes(value: Any, text: str, *, path: str = "", parent_path: str | None = None, binding_name: str | None = None) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    if isinstance(value, dict):
        for key, child in value.items():
            child_path = f"{path}.{key}" if path else str(key)
            out.extend(_generic_scalar_nodes(child, text, path=child_path, parent_path=path or None, binding_name=str(key)))
        return out
    if isinstance(value, list):
        for index, child in enumerate(value):
            child_path = f"{path}[{index}]" if path else f"[{index}]"
            out.extend(_generic_scalar_nodes(child, text, path=child_path, parent_path=path or None, binding_name=binding_name))
        return out
    line = _config_line_for(text, path, value)
    snippet = None
    if line:
        lines = text.splitlines()
        snippet = lines[line - 1].strip()[:1000] if line <= len(lines) else None
    out.append({
        "binding_path": path or "$",
        "parent_path": parent_path,
        "binding_name": binding_name or _config_leaf_name(path),
        "scalar_value": value,
        "line_start": line,
        "line_end": line,
        "raw_snippet": snippet,
    })
    return out


def _properties_scalar_nodes(text: str) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for line_number, raw in enumerate(text.splitlines(), 1):
        stripped = raw.strip()
        if not stripped or stripped.startswith(("#", "!")):
            continue
        if "=" in stripped:
            key, value = stripped.split("=", 1)
        elif ":" in stripped:
            key, value = stripped.split(":", 1)
        else:
            continue
        key = key.strip()
        if not key:
            continue
        out.append({
            "binding_path": key,
            "parent_path": None,
            "binding_name": key,
            "scalar_value": value.strip(),
            "line_start": line_number,
            "line_end": line_number,
            "raw_snippet": stripped[:1000],
        })
    return out


def _shell_scalar_nodes(text: str) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    assignment = re.compile(r"^(?:export\s+)?(?P<name>[A-Za-z_][A-Za-z0-9_.]*)\s*=\s*(?P<value>.*)$")
    for line_number, raw in enumerate(text.splitlines(), 1):
        match = assignment.match(raw.strip())
        if not match:
            continue
        name = match.group("name")
        value = match.group("value").strip().strip('"\'')
        out.append({
            "binding_path": name,
            "parent_path": None,
            "binding_name": name,
            "scalar_value": value,
            "line_start": line_number,
            "line_end": line_number,
            "raw_snippet": raw.strip()[:1000],
        })
    return out


def _config_scalar_nodes(path: Path, text: str) -> tuple[str, list[dict[str, Any]]]:
    suffix = path.suffix.lower()
    if suffix in {".yaml", ".yml"}:
        return "yaml", _yaml_scalar_nodes(text)
    if suffix == ".json":
        return "json", _generic_scalar_nodes(json.loads(text), text)
    if suffix == ".properties":
        return "properties", _properties_scalar_nodes(text)
    if suffix == ".sh":
        return "shell", _shell_scalar_nodes(text)
    if suffix == ".conf":
        try:
            return "yaml", _yaml_scalar_nodes(text)
        except Exception:
            return "properties", _properties_scalar_nodes(text)
    return suffix.lstrip(".") or "unknown", []


def _build_workflow_bindings(repo_id: str, config_hints: list[dict[str, Any]]) -> list[dict[str, Any]]:
    facts: list[dict[str, Any]] = []
    for hint in config_hints:
        absolute_file = Path(str(hint.get("absolute_file") or ""))
        relative_file = str(hint.get("file") or "")
        if not absolute_file.is_file() or not relative_file:
            continue
        try:
            text = read_text(absolute_file)
            config_format, nodes = _config_scalar_nodes(absolute_file, text)
        except Exception:
            continue
        for node in nodes:
            path = str(node.get("binding_path") or "$")
            value = node.get("scalar_value")
            value_text = _config_value_text(value)
            placeholders = _find_placeholders(value_text)
            line_start = node.get("line_start")
            line_end = node.get("line_end") or line_start
            identity = "|".join([
                repo_id,
                relative_file,
                path,
                str(line_start or 0),
                json.dumps(value, ensure_ascii=False, sort_keys=True),
            ])
            facts.append({
                "sql_workflow_binding_id": f"sql_workflow_binding_{repo_id}_{_hash(identity, n=20)}",
                "fact_type": "sql_workflow_binding",
                "repo_id": repo_id,
                "file": relative_file,
                "line_start": line_start,
                "line_end": line_end,
                "config_format": config_format,
                "binding_path": path,
                "parent_path": node.get("parent_path"),
                "binding_name": node.get("binding_name") or _config_leaf_name(path),
                "value_type": _config_scalar_type(value),
                "scalar_value": value,
                "value_expression": value_text,
                "referenced_placeholders": placeholders,
                "resolution_status": "template" if placeholders else "literal",
                "evidence": [{
                    "file": str(absolute_file),
                    "relative_file": relative_file,
                    "line_start": line_start,
                    "line_end": line_end,
                    "extractor": "sql_workflow_binding",
                    "snippet": node.get("raw_snippet") or value_text[:1000],
                    "config_parse_mode": node.get("parse_mode") or "strict",
                    "recovered_template_lines": node.get("recovered_template_lines") or [],
                }],
                **maturity_props({
                    "sql_statement": "not_applicable",
                    "persistence_write": "not_applicable",
                    "physical_storage": "not_applicable",
                    "field_mapping": "not_applicable",
                    "source_boundary": "not_applicable",
                    "end_to_end_trace": "not_applicable",
                }, notes=["Configuration scalar is observed as a binding fact; runtime substitution and deployment precedence are not inferred."]),
            })
    unique = {str(item["sql_workflow_binding_id"]): item for item in facts}
    return sorted(unique.values(), key=lambda item: (str(item.get("file") or ""), int(item.get("line_start") or 0), str(item.get("binding_path") or "")))

def _iter_sql_units(repo: Path, files: list[Path]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    sql_units: list[dict[str, Any]] = []
    config_hints: list[dict[str, Any]] = []
    config_candidates: dict[str, dict[str, Any]] = {}
    referenced_config_templates: set[str] = set()
    for p in files:
        if p.suffix.lower() not in TEXT_SUFFIXES:
            continue
        try:
            text = read_text(p)
        except Exception:
            continue
        rel = _rel(repo, p)
        for match in CONFIG_PATH_RE.finditer(text):
            template = str(match.group("path") or "").replace("\\", "/").strip()
            if template:
                referenced_config_templates.add(template)
        if p.suffix.lower() in SQL_SUFFIXES:
            sql_units.append({"file": rel, "absolute_file": str(p), "line_start": 1, "sql": text, "kind": "sql_file"})
            continue
        if p.suffix.lower() in CONFIG_SUFFIXES:
            candidate = {"file": rel, "absolute_file": str(p), "text": text}
            config_candidates[rel.replace("\\", "/")] = candidate
            low = text.lower()
            if any(token in low for token in ["spark-sql", "spark.sql", ".sql", "insert ", "create table", "select "]):
                config_hints.append({"file": rel, "absolute_file": str(p), "hint_type": "config_or_scheduler_sql_hint", "preview": text[:3000]})
        for rx in EMBEDDED_SQL_PATTERNS:
            for m in rx.finditer(text):
                body = m.group("sql")
                if not body or not any(tok in body.lower() for tok in ["select", "insert", "create", "merge", "update", "delete", "with"]):
                    continue
                line = line_number_for_offset(text, m.start("sql"))
                sql_units.append({"file": rel, "absolute_file": str(p), "line_start": line, "sql": body, "kind": "embedded_sql"})

    known_hints = {str(item.get("file") or "").replace("\\", "/") for item in config_hints}
    for template in sorted(referenced_config_templates):
        normalized = template.lstrip("./")
        exact = config_candidates.get(normalized)
        matches: list[dict[str, Any]] = [exact] if exact else []
        if not matches:
            suffix = _static_path_suffix(normalized)
            if suffix:
                matches = [candidate for path, candidate in config_candidates.items() if path == suffix or path.endswith("/" + suffix)]
        for candidate in matches:
            file_key = str(candidate["file"]).replace("\\", "/")
            if file_key in known_hints:
                continue
            config_hints.append({
                "file": candidate["file"],
                "absolute_file": candidate["absolute_file"],
                "hint_type": "repository_config_reference",
                "preview": str(candidate["text"])[:3000],
            })
            known_hints.add(file_key)
    return sql_units, config_hints


def _nearest_select_ancestor(node: Any) -> Any | None:
    if exp is None:
        return None
    parent = getattr(node, "parent", None)
    while parent is not None:
        if isinstance(parent, exp.Select):
            return parent
        parent = getattr(parent, "parent", None)
    return None


def _projection_column_expression_path(
    column: Any,
    projection: Any | None,
    placeholder_tokens: Mapping[str, str] | None = None,
) -> list[dict[str, Any]]:
    """Return the observed AST path from one projection column to its output.

    This is deliberately structural evidence, not a semantic verdict.  Downstream
    knowledge layers can compose the observed operations with other typed facts
    (for example storage-key lineage) without reparsing SQL text or relying on
    expression-name heuristics.
    """
    if exp is None or projection is None:
        return []

    def restored_sql(node: Any) -> str:
        try:
            value = node.sql(dialect="spark")
        except Exception:
            value = str(node)
        return (_restore_sql_placeholders(value, placeholder_tokens or {}) or value)[:1000]

    result: list[dict[str, Any]] = []
    current = column
    seen: set[int] = set()
    while current is not None and current is not projection:
        current_id = id(current)
        if current_id in seen:
            break
        seen.add(current_id)
        parent = getattr(current, "parent", None)
        if parent is None:
            break

        argument_role = None
        for key, value in getattr(parent, "args", {}).items():
            if value is current:
                argument_role = str(key)
                break
            if isinstance(value, (list, tuple)) and any(item is current for item in value):
                argument_role = str(key)
                break

        item: dict[str, Any] = {
            "operation": str(getattr(parent, "key", None) or type(parent).__name__).lower(),
            "argument_role": argument_role,
        }
        if isinstance(parent, exp.Bracket):
            item["index_expressions"] = [restored_sql(index) for index in (parent.expressions or [])]
        elif isinstance(parent, (exp.Cast, exp.TryCast)):
            target_type = parent.args.get("to")
            item["target_type"] = restored_sql(target_type) if target_type is not None else None
        elif isinstance(parent, exp.Alias):
            item["output_name"] = _restore_sql_placeholders(
                str(getattr(parent, "alias_or_name", None) or ""), placeholder_tokens or {}
            ) or None
        else:
            expression = parent.args.get("expression") if hasattr(parent, "args") else None
            if expression is not None and not isinstance(expression, (list, tuple)):
                item["secondary_expression"] = restored_sql(expression)
        result.append(item)
        current = parent

    return result


def _scope_wrapper(select: Any) -> tuple[str, str | None]:
    """Classify a SELECT by the first structural wrapper before an outer SELECT."""
    if exp is None:
        return "statement", None
    parent = getattr(select, "parent", None)
    while parent is not None and not isinstance(parent, exp.Select):
        if isinstance(parent, exp.CTE):
            return "cte", str(getattr(parent, "alias_or_name", None) or "") or None
        if isinstance(parent, exp.Subquery):
            return "derived", str(getattr(parent, "alias_or_name", None) or "") or None
        if isinstance(parent, (exp.Union, exp.Intersect, exp.Except)):
            return "set_branch", None
        parent = getattr(parent, "parent", None)
    return "statement", None


def _relation_usage_role(table: Any) -> str:
    if exp is None:
        return "read"
    parent = getattr(table, "parent", None)
    while parent is not None and not isinstance(parent, exp.Select):
        if isinstance(parent, exp.Join):
            return "join"
        if isinstance(parent, exp.From):
            return "from"
        parent = getattr(parent, "parent", None)
    return "read"


def _is_descendant_or_same(node: Any, ancestor: Any, *, stop: Any | None = None) -> bool:
    current = node
    while current is not None and current is not stop:
        if current is ancestor:
            return True
        current = getattr(current, "parent", None)
    return False


def _column_usage_role(column: Any, select: Any) -> str:
    if exp is None:
        return "unknown"
    parent = getattr(column, "parent", None)
    while parent is not None and parent is not select:
        if isinstance(parent, exp.Join):
            return "join"
        if isinstance(parent, exp.Where):
            return "filter"
        if isinstance(parent, exp.Having):
            return "having"
        if isinstance(parent, exp.Group):
            return "group_by"
        if isinstance(parent, exp.Order):
            window = next(
                (candidate for candidate in _ancestor_nodes(parent, stop=select) if isinstance(candidate, exp.Window)),
                None,
            )
            return "window_order" if window is not None else "order_by"
        if isinstance(parent, exp.Window):
            partition_expressions = list(parent.args.get("partition_by") or [])
            if any(_is_descendant_or_same(column, item, stop=parent) for item in partition_expressions):
                return "window_partition"
            # A column used as the argument of SUM/LEAD/etc. remains a projection
            # input; merely being inside OVER(...) must not turn it into a
            # partition key. Window ORDER BY was handled above.
            return "projection"
        parent = getattr(parent, "parent", None)
    return "projection"


def _ancestor_nodes(node: Any, *, stop: Any | None = None) -> list[Any]:
    out: list[Any] = []
    parent = getattr(node, "parent", None)
    while parent is not None and parent is not stop:
        out.append(parent)
        parent = getattr(parent, "parent", None)
    return out


def _is_projection_wildcard(projection: Any) -> bool:
    if exp is None:
        return False
    if isinstance(projection, exp.Star):
        return True
    return isinstance(projection, exp.Column) and isinstance(projection.args.get("this"), exp.Star)


def _ast_relation_name(node: Any, placeholder_tokens: dict[str, str]) -> str | None:
    if exp is None or node is None:
        return None
    table = node.this if isinstance(node, exp.Schema) else node
    if not isinstance(table, exp.Table):
        return None
    parts = [getattr(table, "catalog", None), getattr(table, "db", None), getattr(table, "name", None)]
    raw_name = ".".join(str(part) for part in parts if part) or str(getattr(table, "name", None) or "")
    return _canonical_object(_restore_sql_placeholders(raw_name, placeholder_tokens))


def _ast_target_columns(node: Any, placeholder_tokens: dict[str, str]) -> list[str]:
    if exp is None or not isinstance(node, exp.Schema):
        return []
    out: list[str] = []
    for item in getattr(node, "expressions", None) or []:
        raw = str(getattr(item, "name", None) or "")
        restored = _restore_sql_placeholders(raw, placeholder_tokens)
        if restored:
            out.append(restored)
    return out


def _set_output_selects(node: Any) -> list[Any]:
    if exp is None or node is None:
        return []
    while isinstance(node, (exp.Subquery, exp.Paren)):
        node = getattr(node, "this", None)
        if node is None:
            return []
    if isinstance(node, exp.Select):
        return [node]
    if isinstance(node, (exp.Union, exp.Intersect, exp.Except)):
        return _set_output_selects(getattr(node, "this", None)) + _set_output_selects(getattr(node, "expression", None))
    return []




def _join_type(join: Any) -> str:
    side = str((getattr(join, "args", {}) or {}).get("side") or "").strip().lower()
    kind = str((getattr(join, "args", {}) or {}).get("kind") or "").strip().lower()
    method = str((getattr(join, "args", {}) or {}).get("method") or "").strip().lower()
    if kind == "cross":
        return "cross"
    if method == "natural":
        return "natural_" + (side or kind or "inner")
    if kind in {"semi", "anti"}:
        return "_".join(item for item in [side or "left", kind] if item)
    if side:
        return side
    if kind:
        return kind
    return "inner"


def _join_condition_kind(join: Any) -> str:
    args = getattr(join, "args", {}) or {}
    if args.get("on") is not None:
        return "on"
    if args.get("using"):
        return "using"
    if str(args.get("method") or "").lower() == "natural":
        return "natural"
    if _join_type(join) == "cross":
        return "cross"
    return "none"


def _join_conjuncts(node: Any) -> list[Any]:
    if exp is None or node is None:
        return []
    if isinstance(node, exp.And):
        return _join_conjuncts(getattr(node, "this", None)) + _join_conjuncts(getattr(node, "expression", None))
    return [node]


def _comparison_operator(node: Any) -> str | None:
    if exp is None or node is None:
        return None
    mapping = [
        (exp.EQ, "="),
        (getattr(exp, "NullSafeEQ", exp.EQ), "<=>"),
        (exp.NEQ, "!="),
        (exp.GT, ">"),
        (exp.GTE, ">="),
        (exp.LT, "<"),
        (exp.LTE, "<="),
    ]
    # NullSafeEQ may inherit from EQ in some SQLGlot releases; check it first.
    mapping.sort(key=lambda item: 0 if item[1] == "<=>" else 1)
    for cls, operator in mapping:
        if isinstance(node, cls):
            return operator
    return None


def _node_sql(node: Any, placeholder_tokens: dict[str, str]) -> str:
    if node is None:
        return ""
    try:
        raw = node.sql(dialect="spark")
    except Exception:
        raw = str(node)
    return _restore_sql_placeholders(raw, placeholder_tokens) or raw


def _build_scoped_sql_facts(
    normalized: str,
    *,
    placeholder_tokens: dict[str, str],
    repo_id: str,
    query_id: str,
    file: str,
    line_start: int,
    evidence: list[dict[str, Any]],
) -> tuple[
    list[dict[str, Any]],
    list[dict[str, Any]],
    list[dict[str, Any]],
    list[dict[str, Any]],
    list[dict[str, Any]],
    list[dict[str, Any]],
    list[dict[str, Any]],
]:
    """Build scoped SQL facts including write-target projection bindings.

    This is intentionally an inventory contract. Existing mart lineage is not yet
    rewritten to consume these scopes; that migration is a separate iteration.
    """
    if sqlglot is None or exp is None:
        return [], [], [], [], [], [], []
    try:
        expressions = sqlglot.parse(normalized, read="spark", error_level="ignore")
    except Exception:
        return [], [], [], [], [], [], []

    scopes: list[dict[str, Any]] = []
    relations: list[dict[str, Any]] = []
    projections: list[dict[str, Any]] = []
    column_usages: list[dict[str, Any]] = []
    write_targets: list[dict[str, Any]] = []
    target_projection_bindings: list[dict[str, Any]] = []
    join_edges: list[dict[str, Any]] = []
    seen_relations: set[tuple[str, str, str, str]] = set()
    scope_output_contracts: dict[str, dict[str, Any]] = {}
    cte_explicit_columns: dict[tuple[str, ...], list[str]] = {}

    def select_output_contract(select: Any, scope_id: str) -> dict[str, Any]:
        projection_nodes = list(getattr(select, "expressions", None) or [])
        output_columns: list[str] = []
        wildcard_expressions: list[str] = []
        wildcard_present = False
        unnamed_projection_present = False
        for projection in projection_nodes:
            if _is_projection_wildcard(projection):
                wildcard_present = True
                wildcard_expressions.append(_node_sql(projection, placeholder_tokens))
                continue
            output_name = _restore_sql_placeholders(
                str(getattr(projection, "alias_or_name", None) or ""),
                placeholder_tokens,
            ) or None
            if output_name:
                output_columns.append(str(output_name))
            else:
                unnamed_projection_present = True
        normalized_output_columns = [item.lower() for item in output_columns]
        duplicate_output_name_present = len(set(normalized_output_columns)) != len(normalized_output_columns)
        complete = not wildcard_present and not unnamed_projection_present and not duplicate_output_name_present
        return {
            "scope_id": scope_id,
            "output_columns": list(dict.fromkeys(output_columns)),
            "explicit_output_columns": list(output_columns),
            "wildcard_expressions": wildcard_expressions,
            "output_contract_status": "complete" if complete else "partial",
            "output_contract_basis": "explicit_select_projections",
            "output_contract_wildcard_present": wildcard_present,
            "output_contract_unnamed_projection_present": unnamed_projection_present,
            "output_contract_duplicate_name_present": duplicate_output_name_present,
        }

    for expression_index, expression in enumerate(expressions or [], 1):
        if expression is None:
            continue
        select_nodes = list(expression.find_all(exp.Select))
        select_local_ids = {id(node): f"e{expression_index}_s{idx}" for idx, node in enumerate(select_nodes, 1)}
        global_scope_ids = {
            local_id: f"sql_select_scope_{repo_id}_{_hash(query_id + ':' + local_id, n=16)}"
            for local_id in select_local_ids.values()
        }
        for select in select_nodes:
            scope_id = global_scope_ids[select_local_ids[id(select)]]
            scope_output_contracts[scope_id] = select_output_contract(select, scope_id)

        # Resolve CTE references through SQLGlot's lexical scope graph rather than
        # a repository-wide name map. This preserves nested shadowing and every
        # output branch of UNION/INTERSECT/EXCEPT definitions.
        source_scope_ids_by_reference: dict[int, list[str]] = {}
        source_scope_ids_by_expression: dict[int, list[str]] = {}
        if traverse_scope is not None and SqlglotScope is not None:
            try:
                analyzed_scopes = list(traverse_scope(expression))
            except Exception:
                analyzed_scopes = []
            for analyzed_scope in analyzed_scopes:
                try:
                    selected_sources = getattr(analyzed_scope, "selected_sources", None) or {}
                except Exception:
                    # SQLGlot resolves selected_sources lazily and can raise OptimizeError
                    # for ambiguous scopes such as duplicate relation aliases. Lexical
                    # source linking is optional enrichment, so preserve the remaining
                    # observed SQL facts and let existing ambiguous/unresolved statuses
                    # represent the affected scope instead of failing the whole repository.
                    selected_sources = {}
                for _alias, selected in selected_sources.items():
                    reference_node, source = selected
                    if not isinstance(source, SqlglotScope):
                        continue
                    output_scope_ids = [
                        global_scope_ids[select_local_ids[id(select)]]
                        for select in _set_output_selects(source.expression)
                        if id(select) in select_local_ids
                    ]
                    if output_scope_ids:
                        source_scope_ids_by_reference[id(reference_node)] = output_scope_ids
                        source_scope_ids_by_expression[id(source.expression)] = output_scope_ids

        cte_definition_scopes_by_name: dict[str, list[list[str]]] = defaultdict(list)
        for cte in expression.find_all(exp.CTE):
            raw_cte_name = str(getattr(cte, "alias_or_name", None) or "")
            cte_name = _canonical_object(_restore_sql_placeholders(raw_cte_name, placeholder_tokens))
            if not cte_name:
                continue
            definition_scope_ids = [
                global_scope_ids[select_local_ids[id(select)]]
                for select in _set_output_selects(cte.this)
                if id(select) in select_local_ids
            ]
            cte_definition_scopes_by_name[cte_name.lower()].append(definition_scope_ids)
            alias_expression = (getattr(cte, "args", None) or {}).get("alias")
            explicit_columns = [
                _restore_sql_placeholders(
                    str(getattr(identifier, "name", None) or identifier or ""),
                    placeholder_tokens,
                )
                for identifier in list(getattr(alias_expression, "columns", None) or [])
            ]
            explicit_columns = [str(item) for item in explicit_columns if item]
            if explicit_columns and definition_scope_ids:
                explicit_names_unique = len({item.lower() for item in explicit_columns}) == len(explicit_columns)
                if explicit_names_unique:
                    cte_explicit_columns[tuple(definition_scope_ids)] = explicit_columns
        cte_names = set(cte_definition_scopes_by_name)

        for ordinal, select in enumerate(select_nodes, 1):
            local_id = select_local_ids[id(select)]
            scope_id = global_scope_ids[local_id]
            outer = _nearest_select_ancestor(select)
            parent_scope_id = None
            if outer is not None and id(outer) in select_local_ids:
                parent_scope_id = global_scope_ids[select_local_ids[id(outer)]]
            scope_kind, raw_scope_name = _scope_wrapper(select)
            scope_name = _restore_sql_placeholders(raw_scope_name, placeholder_tokens) if raw_scope_name else None
            projection_count = len(getattr(select, "expressions", None) or [])
            scopes.append({
                "sql_select_scope_id": scope_id,
                "fact_type": "sql_select_scope",
                "repo_id": repo_id,
                "query_id": query_id,
                "expression_index": expression_index,
                "scope_ordinal": ordinal,
                "parent_scope_id": parent_scope_id,
                "scope_kind": scope_kind,
                "scope_name": scope_name,
                "projection_count": projection_count,
                "output_columns": list((scope_output_contracts.get(scope_id) or {}).get("output_columns") or []),
                "output_contract_status": (scope_output_contracts.get(scope_id) or {}).get("output_contract_status"),
                "output_contract_basis": (scope_output_contracts.get(scope_id) or {}).get("output_contract_basis"),
                "file": file,
                "line_start": line_start,
                "evidence": evidence[:1],
                **maturity_props({
                    "sql_statement": "confirmed",
                    "persistence_write": "not_applicable",
                    "physical_storage": "not_applicable",
                    "field_mapping": "not_applicable",
                    "source_boundary": "not_applicable",
                    "end_to_end_trace": "not_applicable",
                }),
            })

        # Physical and CTE table references belong to their nearest SELECT scope.
        for table in expression.find_all(exp.Table):
            select = _nearest_select_ancestor(table)
            if select is None or id(select) not in select_local_ids:
                # INSERT/CREATE targets have no SELECT ancestor and are modeled elsewhere.
                continue
            scope_id = global_scope_ids[select_local_ids[id(select)]]
            parts = [getattr(table, "catalog", None), getattr(table, "db", None), getattr(table, "name", None)]
            raw_name = ".".join(str(part) for part in parts if part) or str(getattr(table, "name", None) or "")
            name = _canonical_object(_restore_sql_placeholders(raw_name, placeholder_tokens))
            if not name:
                continue
            try:
                raw_alias = table.alias
            except Exception:
                raw_alias = None
            alias = _restore_sql_placeholders(str(raw_alias), placeholder_tokens) if raw_alias else None
            semantics = _relation_semantics(name)
            source_scope_ids = list(source_scope_ids_by_reference.get(id(table)) or [])
            if not source_scope_ids and name.lower() in cte_names:
                fallback_definitions = cte_definition_scopes_by_name.get(name.lower()) or []
                # Use the AST-name fallback only when one definition is present in
                # the parsed expression. Lexical scope analysis remains authoritative
                # for nested/shadowed CTE names.
                if len(fallback_definitions) == 1:
                    source_scope_ids = list(fallback_definitions[0])
            relation_kind = "cte" if source_scope_ids else semantics["relation_kind"]
            # If a CTE is visible by name but its defining output scopes still cannot
            # be selected safely, preserve it as an unresolved intermediate relation.
            if relation_kind != "cte" and name.lower() in cte_names:
                relation_kind = "cte"
            key = (scope_id, relation_kind, name, str(alias or ""))
            if key in seen_relations:
                continue
            seen_relations.add(key)
            relations.append({
                "sql_relation_id": f"sql_relation_{repo_id}_{_hash(query_id + ':' + '|'.join(key), n=16)}",
                "fact_type": "sql_relation",
                "repo_id": repo_id,
                "query_id": query_id,
                "scope_id": scope_id,
                "relation_kind": relation_kind,
                "relation_name": name,
                "template_name": semantics.get("template_name"),
                "logical_name": semantics.get("logical_name") if relation_kind != "cte" else name,
                "placeholder_refs": semantics.get("placeholder_refs") or [],
                "alias": alias,
                "usage_role": _relation_usage_role(table),
                "source_scope_ids": source_scope_ids,
                "definition_status": (
                    "resolved" if relation_kind == "cte" and source_scope_ids
                    else "unresolved" if relation_kind == "cte"
                    else "not_applicable"
                ),
                "file": file,
                "line_start": line_start,
                "evidence": evidence[:1],
                **maturity_props({
                    "sql_statement": "confirmed",
                    "persistence_write": "not_applicable",
                    "physical_storage": "confirmed" if relation_kind in {"physical", "physical_template"} else "not_applicable",
                    "field_mapping": "not_applicable",
                    "source_boundary": "not_applicable",
                    "end_to_end_trace": "not_applicable",
                }),
            })

        # A subquery used by an outer SELECT is a derived relation bound by alias.
        for subquery in expression.find_all(exp.Subquery):
            alias = str(getattr(subquery, "alias_or_name", None) or "") or None
            if not alias:
                continue
            outer = _nearest_select_ancestor(subquery)
            if outer is None or id(outer) not in select_local_ids:
                continue
            child_scope_ids = list(source_scope_ids_by_expression.get(id(subquery.this)) or [])
            if not child_scope_ids:
                child_scope_ids = [
                    global_scope_ids[select_local_ids[id(child)]]
                    for child in _set_output_selects(subquery.this)
                    if id(child) in select_local_ids
                ]
            scope_id = global_scope_ids[select_local_ids[id(outer)]]
            key = (scope_id, "derived", alias, alias)
            if key in seen_relations:
                continue
            seen_relations.add(key)
            relations.append({
                "sql_relation_id": f"sql_relation_{repo_id}_{_hash(query_id + ':' + '|'.join(key), n=16)}",
                "fact_type": "sql_relation",
                "repo_id": repo_id,
                "query_id": query_id,
                "scope_id": scope_id,
                "relation_kind": "derived",
                "relation_name": alias,
                "template_name": alias,
                "logical_name": alias,
                "placeholder_refs": [],
                "alias": alias,
                "usage_role": "derived_source",
                "source_scope_ids": child_scope_ids,
                "definition_status": "resolved" if child_scope_ids else "unresolved",
                "_explicit_output_columns": [
                    _restore_sql_placeholders(
                        str(getattr(identifier, "name", None) or identifier or ""),
                        placeholder_tokens,
                    )
                    for identifier in list(getattr((getattr(subquery, "args", None) or {}).get("alias"), "columns", None) or [])
                    if str(getattr(identifier, "name", None) or identifier or "")
                ],
                "file": file,
                "line_start": line_start,
                "evidence": evidence[:1],
                **maturity_props({
                    "sql_statement": "confirmed",
                    "persistence_write": "not_applicable",
                    "physical_storage": "not_applicable",
                    "field_mapping": "not_applicable",
                    "source_boundary": "not_applicable",
                    "end_to_end_trace": "not_applicable",
                }),
            })

        # LATERAL VIEW / EXPLODE outputs are generated row values, not physical
        # tables.  Model their visible output aliases explicitly so nested fields
        # such as ``participant.status`` resolve without being attributed to the
        # physical JSON source table.  The table alias (for example
        # ``participant_table``) is only a wrapper; Hive/Spark SQL references the
        # generated column aliases listed after AS.
        for lateral in expression.find_all(exp.Lateral):
            select = _nearest_select_ancestor(lateral)
            if select is None or id(select) not in select_local_ids:
                continue
            scope_id = global_scope_ids[select_local_ids[id(select)]]
            table_alias = lateral.args.get("alias")
            generated_names = [
                _restore_sql_placeholders(str(getattr(identifier, "name", None) or identifier), placeholder_tokens)
                for identifier in list(getattr(table_alias, "columns", None) or [])
            ]
            generated_names = [str(name) for name in generated_names if name]
            if not generated_names:
                fallback_name = _restore_sql_placeholders(
                    str(getattr(table_alias, "name", None) or ""),
                    placeholder_tokens,
                )
                if fallback_name:
                    generated_names = [fallback_name]
            try:
                generator_expression = _restore_sql_placeholders(
                    lateral.this.sql(dialect="spark"),
                    placeholder_tokens,
                )
            except Exception:
                generator_expression = str(getattr(lateral, "this", None) or "")
            wrapper_alias = _restore_sql_placeholders(
                str(getattr(table_alias, "name", None) or ""),
                placeholder_tokens,
            ) or None
            for generated_name in generated_names:
                key = (scope_id, "generated", generated_name, generated_name)
                if key in seen_relations:
                    continue
                seen_relations.add(key)
                relations.append({
                    "sql_relation_id": f"sql_relation_{repo_id}_{_hash(query_id + ':' + '|'.join(key), n=16)}",
                    "fact_type": "sql_relation",
                    "repo_id": repo_id,
                    "query_id": query_id,
                    "scope_id": scope_id,
                    "relation_kind": "generated",
                    "relation_name": generated_name,
                    "template_name": generated_name,
                    "logical_name": generated_name,
                    "placeholder_refs": [],
                    "alias": generated_name,
                    "usage_role": "generated_source",
                    "source_scope_ids": [],
                    "definition_status": "resolved",
                    "generator_expression": generator_expression,
                    "generator_wrapper_alias": wrapper_alias,
                    "file": file,
                    "line_start": line_start,
                    "evidence": evidence[:1],
                    **maturity_props({
                        "sql_statement": "confirmed",
                        "persistence_write": "not_applicable",
                        "physical_storage": "not_applicable",
                        "field_mapping": "confirmed",
                        "source_boundary": "not_applicable",
                        "end_to_end_trace": "not_applicable",
                    }),
                })

    relation_explicit_columns: dict[str, list[str]] = {}

    def apply_relation_output_contract(relation: dict[str, Any]) -> bool:
        relation_kind = str(relation.get("relation_kind") or "")

        def contract_signature() -> tuple[Any, ...]:
            return (
                tuple(relation.get("output_columns") or []),
                relation.get("output_contract_status"),
                relation.get("output_contract_basis"),
                tuple(
                    (item.get("wildcard_expression"), item.get("source_relation_id"), item.get("resolution_status"))
                    for item in relation.get("output_contract_wildcard_provenance") or []
                ),
                tuple(
                    (
                        item.get("branch_ordinal"),
                        item.get("scope_id"),
                        item.get("output_contract_status"),
                        tuple(item.get("output_columns") or []),
                    )
                    for item in relation.get("output_contract_branches") or []
                ),
                tuple(
                    (item.get("code"), item.get("branch_ordinal"), item.get("details"))
                    for item in relation.get("output_contract_diagnostics") or []
                ),
            )

        previous = contract_signature()
        if relation_kind not in {"cte", "derived"}:
            relation["output_columns"] = []
            relation["output_contract_status"] = "not_applicable"
            relation["output_contract_basis"] = "not_applicable"
            relation["output_contract_wildcard_provenance"] = []
            relation["output_contract_branches"] = []
            relation["output_contract_diagnostics"] = []
            return contract_signature() != previous

        source_scope_ids = [str(item) for item in relation.get("source_scope_ids") or []]
        explicit_columns = relation_explicit_columns.get(str(relation.get("sql_relation_id") or ""))
        if explicit_columns is None:
            explicit_columns = cte_explicit_columns.get(tuple(source_scope_ids))

        contract: dict[str, Any] | None = None
        branches: list[dict[str, Any]] = []
        diagnostics: list[dict[str, Any]] = []

        if len(source_scope_ids) == 1:
            contract = scope_output_contracts.get(source_scope_ids[0])
        elif len(source_scope_ids) > 1:
            for branch_ordinal, scope_id in enumerate(source_scope_ids, 1):
                branch_contract = scope_output_contracts.get(scope_id)
                branch_payload = {
                    "branch_ordinal": branch_ordinal,
                    "scope_id": scope_id,
                    "output_columns": list((branch_contract or {}).get("output_columns") or []),
                    "output_contract_status": (branch_contract or {}).get("output_contract_status") or "unavailable",
                    "output_contract_basis": (branch_contract or {}).get("output_contract_basis") or "definition_scope_unavailable",
                }
                branches.append(branch_payload)
                if branch_contract is None or branch_payload["output_contract_status"] != "complete":
                    diagnostics.append({
                        "code": "set_operation_branch_incomplete",
                        "branch_ordinal": branch_ordinal,
                        "details": branch_payload["output_contract_status"],
                    })
            branch_cardinalities = {len(item["output_columns"]) for item in branches}
            all_branches_complete = bool(branches) and all(
                item["output_contract_status"] == "complete" for item in branches
            )
            cardinality_matches = len(branch_cardinalities) == 1
            if all_branches_complete and cardinality_matches:
                first_branch = branches[0]
                wildcard_provenance = []
                for branch in branches:
                    branch_contract = scope_output_contracts.get(str(branch["scope_id"])) or {}
                    wildcard_provenance.extend({
                        **item,
                        "set_branch_ordinal": branch["branch_ordinal"],
                        "set_branch_scope_id": branch["scope_id"],
                    } for item in branch_contract.get("output_contract_wildcard_provenance") or [])
                contract = {
                    "output_columns": list(first_branch["output_columns"]),
                    "output_contract_status": "complete",
                    "output_contract_basis": "set_operation_ordinal",
                    "output_contract_wildcard_provenance": wildcard_provenance,
                }
            else:
                if all_branches_complete and not cardinality_matches:
                    diagnostics.append({
                        "code": "set_operation_cardinality_mismatch",
                        "branch_ordinal": None,
                        "details": ",".join(str(item) for item in sorted(branch_cardinalities)),
                    })
                first_columns = list(branches[0]["output_columns"]) if branches else []
                contract = {
                    "output_columns": first_columns,
                    "output_contract_status": "partial",
                    "output_contract_basis": (
                        "set_operation_cardinality_mismatch"
                        if all_branches_complete and not cardinality_matches
                        else "set_operation_branch_incomplete"
                    ),
                    "output_contract_wildcard_provenance": [],
                }

        if contract is None:
            relation["output_columns"] = []
            relation["output_contract_status"] = "unavailable"
            relation["output_contract_basis"] = "definition_scope_unavailable"
            relation["output_contract_wildcard_provenance"] = []
            relation["output_contract_branches"] = branches
            relation["output_contract_diagnostics"] = diagnostics
            return contract_signature() != previous

        if (
            explicit_columns
            and contract.get("output_contract_status") == "complete"
            and len(explicit_columns) == len(contract.get("output_columns") or [])
        ):
            contract = {
                **contract,
                "output_columns": list(explicit_columns),
                "output_contract_basis": (
                    "explicit_derived_column_list"
                    if relation_kind == "derived"
                    else "explicit_cte_column_list"
                ),
            }
        elif explicit_columns and contract.get("output_contract_status") == "complete":
            diagnostics.append({
                "code": "explicit_output_column_count_mismatch",
                "branch_ordinal": None,
                "details": f"declared={len(explicit_columns)},actual={len(contract.get('output_columns') or [])}",
            })
            contract = {
                **contract,
                "output_contract_status": "partial",
                "output_contract_basis": "explicit_output_column_count_mismatch",
            }

        relation["output_columns"] = list(contract.get("output_columns") or [])
        relation["output_contract_status"] = contract.get("output_contract_status")
        relation["output_contract_basis"] = contract.get("output_contract_basis")
        relation["output_contract_wildcard_provenance"] = list(
            contract.get("output_contract_wildcard_provenance") or []
        )
        relation["output_contract_branches"] = branches
        relation["output_contract_diagnostics"] = diagnostics
        return contract_signature() != previous

    for relation in relations:
        relation_id = str(relation.get("sql_relation_id") or "")
        explicit_columns = [
            str(item) for item in relation.pop("_explicit_output_columns", []) if item
        ]
        if explicit_columns:
            relation_explicit_columns[relation_id] = explicit_columns
        apply_relation_output_contract(relation)

    relation_counts = Counter(str(item.get("scope_id")) for item in relations)
    for scope in scopes:
        scope["relation_count"] = relation_counts.get(str(scope.get("sql_select_scope_id")), 0)

    relations_by_scope: dict[str, list[dict[str, Any]]] = defaultdict(list)
    scope_parent: dict[str, str | None] = {}
    for scope in scopes:
        scope_parent[str(scope.get("sql_select_scope_id"))] = scope.get("parent_scope_id")
    for relation in relations:
        relations_by_scope[str(relation.get("scope_id"))].append(relation)

    def wildcard_source_relation(scope_id: str, wildcard_expression: str) -> dict[str, Any] | None:
        candidates = [
            item for item in relations_by_scope.get(scope_id, [])
            if item.get("relation_kind") != "generated"
        ]
        expression = str(wildcard_expression or "").strip()
        if expression == "*":
            return candidates[0] if len(candidates) == 1 else None
        if expression.endswith(".*"):
            token = expression[:-2].strip().strip('`"')
            matches = [
                item for item in candidates
                if token.lower() in {
                    str(item.get("alias") or "").lower(),
                    str(item.get("relation_name") or "").lower(),
                    str(item.get("logical_name") or "").lower(),
                }
            ]
            return matches[0] if len(matches) == 1 else None
        return None

    def expand_scope_wildcard_contract(scope_id: str) -> bool:
        contract = scope_output_contracts.get(scope_id)
        if contract is None or not contract.get("wildcard_expressions"):
            return False
        previous = (
            tuple(contract.get("output_columns") or []),
            contract.get("output_contract_status"),
            contract.get("output_contract_basis"),
            tuple(
                (item.get("wildcard_expression"), item.get("source_relation_id"), item.get("resolution_status"))
                for item in contract.get("output_contract_wildcard_provenance") or []
            ),
        )
        output_columns = list(contract.get("explicit_output_columns") or [])
        provenance: list[dict[str, Any]] = []
        every_wildcard_resolved = True
        for wildcard_expression in contract.get("wildcard_expressions") or []:
            source_relation = wildcard_source_relation(scope_id, str(wildcard_expression))
            if source_relation is None:
                every_wildcard_resolved = False
                provenance.append({
                    "wildcard_expression": wildcard_expression,
                    "source_relation_id": None,
                    "source_relation_name": None,
                    "resolution_status": "unresolved",
                    "resolution_basis": "wildcard_source_not_unique",
                })
                continue
            source_complete = source_relation.get("output_contract_status") == "complete"
            provenance.append({
                "wildcard_expression": wildcard_expression,
                "source_relation_id": source_relation.get("sql_relation_id"),
                "source_relation_name": source_relation.get("relation_name"),
                "resolution_status": "resolved" if source_complete else "unresolved",
                "resolution_basis": (
                    "complete_intermediate_output_contract"
                    if source_complete
                    else "source_output_contract_incomplete"
                ),
            })
            if not source_complete:
                every_wildcard_resolved = False
                continue
            output_columns.extend(str(item) for item in source_relation.get("output_columns") or [])
        normalized_columns = [item.lower() for item in output_columns]
        duplicate_present = len(set(normalized_columns)) != len(normalized_columns)
        complete = (
            every_wildcard_resolved
            and not contract.get("output_contract_unnamed_projection_present")
            and not duplicate_present
        )
        contract["output_columns"] = list(dict.fromkeys(output_columns))
        contract["output_contract_status"] = "complete" if complete else "partial"
        contract["output_contract_basis"] = (
            "expanded_intermediate_wildcard" if complete else "wildcard_expansion_partial"
        )
        contract["output_contract_duplicate_name_present"] = duplicate_present
        contract["output_contract_wildcard_provenance"] = provenance
        current = (
            tuple(contract.get("output_columns") or []),
            contract.get("output_contract_status"),
            contract.get("output_contract_basis"),
            tuple(
                (item.get("wildcard_expression"), item.get("source_relation_id"), item.get("resolution_status"))
                for item in contract.get("output_contract_wildcard_provenance") or []
            ),
        )
        return current != previous

    # Wildcard contracts may form multi-level CTE/derived chains. Iterate until
    # no scope or relation gains a more complete contract. Recursive cycles have
    # no complete seed and therefore remain partial.
    for _iteration in range(len(scopes) + len(relations) + 1):
        changed = False
        for scope_id in sorted(scope_output_contracts):
            changed = expand_scope_wildcard_contract(scope_id) or changed
        for relation in relations:
            changed = apply_relation_output_contract(relation) or changed
        if not changed:
            break

    scope_by_id = {str(item.get("sql_select_scope_id")): item for item in scopes}
    for scope_id, contract in scope_output_contracts.items():
        scope = scope_by_id.get(scope_id)
        if scope is None:
            continue
        scope["output_columns"] = list(contract.get("output_columns") or [])
        scope["output_contract_status"] = contract.get("output_contract_status")
        scope["output_contract_basis"] = contract.get("output_contract_basis")
        scope["output_contract_wildcard_provenance"] = list(
            contract.get("output_contract_wildcard_provenance") or []
        )

    def resolve_relation(scope_id: str, table_or_alias: str | None, column_name: str, output_names: set[str], usage_role: str) -> tuple[dict[str, Any] | None, str]:
        token = str(table_or_alias or "").strip('`"')
        if token:
            current: str | None = scope_id
            first = True
            while current:
                candidates = [
                    item for item in relations_by_scope.get(current, [])
                    if token.lower() in {
                        str(item.get("alias") or "").lower(),
                        str(item.get("relation_name") or "").lower(),
                        str(item.get("logical_name") or "").lower(),
                    }
                ]
                if len(candidates) == 1:
                    return candidates[0], "alias" if first else "outer_scope_alias"
                if len(candidates) > 1:
                    return None, "ambiguous_alias"
                current = scope_parent.get(current)
                first = False
            return None, "alias_unresolved"
        if usage_role == "order_by" and column_name.lower() in output_names:
            return None, "projection_output"
        candidates = relations_by_scope.get(scope_id, [])
        generated_candidates = [
            item for item in candidates
            if item.get("relation_kind") == "generated"
            and column_name.lower() in {
                str(item.get("alias") or "").lower(),
                str(item.get("relation_name") or "").lower(),
                str(item.get("logical_name") or "").lower(),
            }
        ]
        if len(generated_candidates) == 1:
            return generated_candidates[0], "generated_alias_unqualified"
        if len(generated_candidates) > 1:
            return None, "ambiguous_generated_alias"
        primary_candidates = [
            item for item in candidates if item.get("relation_kind") != "generated"
        ]
        if len(primary_candidates) == 1:
            basis = "single_relation_in_scope" if len(candidates) == 1 else "single_primary_relation_in_scope"
            return primary_candidates[0], basis
        if usage_role in {"group_by", "having"} and column_name.lower() in output_names:
            return None, "projection_output"
        if not primary_candidates:
            return None, "relation_unavailable"
        if all(
            item.get("relation_kind") in {"cte", "derived"}
            and item.get("output_contract_status") == "complete"
            for item in primary_candidates
        ):
            normalized_column = column_name.lower()
            owners = [
                item for item in primary_candidates
                if normalized_column in {
                    str(output_name).lower()
                    for output_name in item.get("output_columns") or []
                }
            ]
            if len(owners) == 1:
                return owners[0], "unique_complete_intermediate_output_contract"
            if len(owners) > 1:
                return None, "ambiguous_intermediate_output_contract"
        return None, "ambiguous_unqualified"

    def column_reference_parts(column: Any) -> list[str]:
        """Return the restored multipart column path in source order.

        SQLGlot maps a four-part path to catalog/db/table/name, which means
        ``pad.pr.status`` exposes ``pr`` as ``column.table`` even though ``pad``
        is the actual SQL relation alias.  Using ``Column.parts`` preserves the
        lexical order needed to resolve nested structured values safely.
        """
        restored: list[str] = []
        for part in list(getattr(column, "parts", None) or []):
            raw = str(getattr(part, "name", None) or part or "")
            value = _restore_sql_placeholders(raw, placeholder_tokens)
            if value:
                restored.append(str(value))
        return restored

    def resolve_column_reference(
        scope_id: str,
        column: Any,
        output_names: set[str],
        usage_role: str,
    ) -> tuple[dict[str, Any] | None, str, str | None, str]:
        parts = column_reference_parts(column)
        if not parts:
            return None, "relation_unavailable", None, ""
        if len(parts) == 1:
            column_name = parts[0]
            relation, basis = resolve_relation(scope_id, None, column_name, output_names, usage_role)
            return relation, basis, None, column_name

        # Resolve by the leftmost path segment that is demonstrably a relation
        # alias/name.  Remaining segments form the structured column path.
        for index, candidate in enumerate(parts[:-1]):
            relation, basis = resolve_relation(scope_id, candidate, ".".join(parts[index + 1:]), output_names, usage_role)
            if relation is not None:
                nested_name = ".".join(parts[index + 1:])
                generated_basis = "generated_alias" if relation.get("relation_kind") == "generated" else basis
                return relation, generated_basis, candidate, nested_name
            if basis == "ambiguous_alias":
                return None, basis, candidate, ".".join(parts[index + 1:])

        # A multipart path may be a nested field of the only non-generated
        # source in the scope (for example parsed_data.items.value). Generated
        # LATERAL aliases must not make that physical source artificially
        # ambiguous.
        primary_relations = [
            item for item in relations_by_scope.get(scope_id, [])
            if item.get("relation_kind") != "generated"
        ]
        if len(primary_relations) == 1:
            return primary_relations[0], "single_primary_relation_in_scope", None, ".".join(parts)

        # Preserve the historical unresolved alias shape for diagnostics, but
        # keep the complete nested field path instead of only its final token.
        table_or_alias = parts[0]
        return None, "alias_unresolved", table_or_alias, ".".join(parts[1:])

    # Build projection and column-usage facts after relation bindings are known.
    for expression_index, expression in enumerate(expressions or [], 1):
        if expression is None:
            continue
        select_nodes = list(expression.find_all(exp.Select))
        select_local_ids = {id(node): f"e{expression_index}_s{idx}" for idx, node in enumerate(select_nodes, 1)}
        global_scope_ids = {
            local_id: f"sql_select_scope_{repo_id}_{_hash(query_id + ':' + local_id, n=16)}"
            for local_id in select_local_ids.values()
        }
        for select in select_nodes:
            scope_id = global_scope_ids[select_local_ids[id(select)]]
            projection_nodes = list(getattr(select, "expressions", None) or [])
            output_names = {
                str(getattr(node, "alias_or_name", None) or "").lower()
                for node in projection_nodes
                if getattr(node, "alias_or_name", None)
            }
            usage_by_column_object: dict[int, str] = {}
            usage_resolution_by_id: dict[str, str] = {}
            scoped_columns = [
                column for column in select.find_all(exp.Column)
                if _nearest_select_ancestor(column) is select
            ]
            projection_ordinal_by_column_object: dict[int, int] = {}
            projection_metadata: list[dict[str, Any]] = []
            for projection_ordinal, projection in enumerate(projection_nodes, 1):
                try:
                    expression_sql = _restore_sql_placeholders(projection.sql(dialect="spark"), placeholder_tokens) or ""
                except Exception:
                    expression_sql = str(projection)
                output_name = _restore_sql_placeholders(
                    str(getattr(projection, "alias_or_name", None) or ""),
                    placeholder_tokens,
                ) or None
                projection_id = f"sql_projection_{repo_id}_{_hash(query_id + ':' + scope_id + ':' + str(projection_ordinal) + ':' + expression_sql, n=16)}"
                projection_metadata.append({
                    "projection": projection,
                    "projection_ordinal": projection_ordinal,
                    "projection_id": projection_id,
                    "expression_sql": expression_sql,
                    "output_name": output_name,
                })
                for projection_column in projection.find_all(exp.Column):
                    if _nearest_select_ancestor(projection_column) is select:
                        projection_ordinal_by_column_object[id(projection_column)] = projection_ordinal

            provisional_columns: list[dict[str, Any]] = []
            for column_ordinal, column in enumerate(scoped_columns, 1):
                role = _column_usage_role(column, select)
                relation, resolution_basis, table_or_alias, column_name = resolve_column_reference(
                    scope_id,
                    column,
                    output_names,
                    role,
                )
                if not column_name:
                    continue
                usage_id = f"sql_column_usage_{repo_id}_{_hash(query_id + ':' + scope_id + ':' + str(column_ordinal) + ':' + role + ':' + str(table_or_alias) + ':' + column_name, n=16)}"
                usage_by_column_object[id(column)] = usage_id
                provisional_columns.append({
                    "column": column,
                    "column_ordinal": column_ordinal,
                    "usage_id": usage_id,
                    "role": role,
                    "relation": relation,
                    "resolution_basis": resolution_basis,
                    "table_or_alias": table_or_alias,
                    "column_name": column_name,
                    "projection_ordinal": projection_ordinal_by_column_object.get(id(column)),
                })

            provisional_by_column_object = {
                id(item["column"]): item for item in provisional_columns
            }
            projection_by_ordinal = {
                int(metadata["projection_ordinal"]): metadata["projection"]
                for metadata in projection_metadata
            }
            direct_projection_aliases: dict[str, list[dict[str, Any]]] = defaultdict(list)
            for metadata in projection_metadata:
                projection = metadata["projection"]
                direct_column = projection.this if isinstance(projection, exp.Alias) else projection
                if not isinstance(direct_column, exp.Column):
                    continue
                source = provisional_by_column_object.get(id(direct_column))
                output_name = str(metadata.get("output_name") or "")
                if not source or not output_name:
                    continue
                source_relation = source.get("relation")
                if (
                    source_relation is None
                    or source.get("resolution_basis") != "alias"
                    or not source.get("table_or_alias")
                    or output_name.lower() != str(source.get("column_name") or "").lower()
                ):
                    continue
                direct_projection_aliases[output_name.lower()].append({
                    "projection_ordinal": metadata["projection_ordinal"],
                    "projection_id": metadata["projection_id"],
                    "source_usage_id": source["usage_id"],
                    "source_relation": source_relation,
                })

            for item in provisional_columns:
                relation = item["relation"]
                resolution_basis = str(item["resolution_basis"])
                table_or_alias = item["table_or_alias"]
                column_name = str(item["column_name"])
                role = str(item["role"])
                source_projection_id = None
                source_column_usage_id = None
                current_projection_ordinal = item.get("projection_ordinal")
                if resolution_basis == "ambiguous_unqualified" and current_projection_ordinal is not None:
                    prior_aliases = [
                        candidate
                        for candidate in direct_projection_aliases.get(column_name.lower(), [])
                        if int(candidate["projection_ordinal"]) < int(current_projection_ordinal)
                    ]
                    if len(prior_aliases) == 1:
                        candidate = prior_aliases[0]
                        relation = candidate["source_relation"]
                        resolution_basis = "prior_direct_projection_alias"
                        source_projection_id = candidate["projection_id"]
                        source_column_usage_id = candidate["source_usage_id"]
                unqualified_semantic_parameter = bool(_find_placeholders(column_name)) and not table_or_alias
                if unqualified_semantic_parameter:
                    relation = None
                    resolution_basis = "semantic_parameter"
                    resolution_status = "semantic_parameter"
                else:
                    resolution_status = (
                        "resolved" if relation is not None
                        else "projection_output" if resolution_basis == "projection_output"
                        else "ambiguous" if resolution_basis.startswith("ambiguous")
                        else "unresolved"
                    )
                usage_id = str(item["usage_id"])
                usage_resolution_by_id[usage_id] = resolution_status
                projection_expression_path = _projection_column_expression_path(
                    item["column"],
                    projection_by_ordinal.get(int(current_projection_ordinal))
                    if current_projection_ordinal is not None
                    else None,
                    placeholder_tokens,
                )
                column_usages.append({
                    "sql_column_usage_id": usage_id,
                    "fact_type": "sql_column_usage",
                    "repo_id": repo_id,
                    "query_id": query_id,
                    "scope_id": scope_id,
                    "column_ordinal": item["column_ordinal"],
                    "column_name": column_name,
                    "table_or_alias": table_or_alias,
                    "usage_role": role,
                    "relation_id": relation.get("sql_relation_id") if relation else None,
                    "relation_name": relation.get("relation_name") if relation else None,
                    "relation_kind": relation.get("relation_kind") if relation else None,
                    "resolution_status": resolution_status,
                    "resolution_basis": resolution_basis,
                    "resolution_source_projection_id": source_projection_id,
                    "resolution_source_column_usage_id": source_column_usage_id,
                    "resolution_contract_status": (
                        relation.get("output_contract_status")
                        if relation is not None and resolution_basis == "unique_complete_intermediate_output_contract"
                        else None
                    ),
                    "resolution_contract_basis": (
                        relation.get("output_contract_basis")
                        if relation is not None and resolution_basis == "unique_complete_intermediate_output_contract"
                        else None
                    ),
                    "projection_expression_path": projection_expression_path,
                    "file": file,
                    "line_start": line_start,
                    "evidence": [{
                        "relative_file": file,
                        "line_start": line_start,
                        "extractor": "sql_profile_scoped_ast",
                        "scope_id": scope_id,
                    }],
                    **maturity_props({
                        "sql_statement": "confirmed",
                        "persistence_write": "not_applicable",
                        "physical_storage": "confirmed" if relation and relation.get("relation_kind") in {"physical", "physical_template"} else "not_applicable",
                        "field_mapping": "confirmed" if relation is not None or resolution_status in {"projection_output", "semantic_parameter"} else "unresolved",
                        "source_boundary": "not_applicable",
                        "end_to_end_trace": "not_applicable",
                    }),
                })

            for metadata in projection_metadata:
                projection = metadata["projection"]
                projection_ordinal = metadata["projection_ordinal"]
                projection_id = metadata["projection_id"]
                expression_sql = metadata["expression_sql"]
                output_name = metadata["output_name"]
                source_usage_ids = [
                    usage_by_column_object[id(column)]
                    for column in projection.find_all(exp.Column)
                    if id(column) in usage_by_column_object
                ]
                projection_unresolved = any(
                    usage_resolution_by_id.get(item) in {"ambiguous", "unresolved"}
                    for item in source_usage_ids
                )
                is_wildcard = _is_projection_wildcard(projection)
                projection_status = "partial" if is_wildcard or projection_unresolved else "resolved"
                projections.append({
                    "sql_projection_id": projection_id,
                    "fact_type": "sql_projection",
                    "repo_id": repo_id,
                    "query_id": query_id,
                    "scope_id": scope_id,
                    "projection_ordinal": projection_ordinal,
                    "output_name": output_name,
                    "expression": expression_sql[:4000],
                    "expression_kind": _expression_type(expression_sql),
                    "is_wildcard": is_wildcard,
                    "source_column_usage_ids": source_usage_ids,
                    "source_column_count": len(source_usage_ids),
                    "resolution_status": projection_status,
                    "resolution_basis": "wildcard_requires_schema" if is_wildcard else ("source_column_unresolved" if projection_unresolved else "scoped_ast"),
                    "file": file,
                    "line_start": line_start,
                    "evidence": [{
                        "relative_file": file,
                        "line_start": line_start,
                        "extractor": "sql_profile_scoped_ast",
                        "scope_id": scope_id,
                    }],
                    **maturity_props({
                        "sql_statement": "confirmed",
                        "persistence_write": "not_applicable",
                        "physical_storage": "not_applicable",
                        "field_mapping": "unresolved" if projection_status == "partial" else "confirmed",
                        "source_boundary": "not_applicable",
                        "end_to_end_trace": "not_applicable",
                    }),
                })


            # Build one canonical fact per JOIN clause from the scoped AST.
            scope_relations = relations_by_scope.get(scope_id, [])
            scope_usage_by_id = {
                str(item.get("sql_column_usage_id")): item
                for item in column_usages
                if str(item.get("scope_id")) == scope_id
            }

            def relation_for_node(node: Any) -> dict[str, Any] | None:
                if node is None:
                    return None
                raw_token = str(getattr(node, "alias_or_name", None) or "")
                token = _restore_sql_placeholders(raw_token, placeholder_tokens) or raw_token
                if not token and isinstance(node, exp.Table):
                    parts = [getattr(node, "catalog", None), getattr(node, "db", None), getattr(node, "name", None)]
                    token = _canonical_object(_restore_sql_placeholders(".".join(str(part) for part in parts if part), placeholder_tokens))
                candidates = [
                    item for item in scope_relations
                    if str(token or "").lower() in {
                        str(item.get("alias") or "").lower(),
                        str(item.get("relation_name") or "").lower(),
                        str(item.get("logical_name") or "").lower(),
                    }
                ]
                return candidates[0] if len(candidates) == 1 else None

            from_node = getattr(select.args.get("from_"), "this", None)
            first_relation = relation_for_node(from_node)
            accumulated_relation_ids: list[str] = []
            if first_relation is not None:
                accumulated_relation_ids.append(str(first_relation.get("sql_relation_id")))

            for join_ordinal, join in enumerate(select.args.get("joins") or [], 1):
                right_relation = relation_for_node(getattr(join, "this", None))
                right_relation_id = str((right_relation or {}).get("sql_relation_id") or "") or None
                condition = join.args.get("on")
                using_columns = [
                    _restore_sql_placeholders(str(getattr(item, "name", None) or item), placeholder_tokens)
                    for item in (join.args.get("using") or [])
                ]
                using_columns = [item for item in using_columns if item]
                column_pairs: list[dict[str, Any]] = []
                expression_links: list[dict[str, Any]] = []
                additional_predicates: list[str] = []
                temporal_or_range_predicates: list[str] = []
                condition_relation_ids: set[str] = set()
                predicate_has_unresolved_columns = False

                def usage_payload(column: Any) -> dict[str, Any] | None:
                    usage_id = usage_by_column_object.get(id(column))
                    return scope_usage_by_id.get(str(usage_id)) if usage_id else None

                for conjunct in _join_conjuncts(condition):
                    rendered = _node_sql(conjunct, placeholder_tokens)
                    operator = _comparison_operator(conjunct)
                    left_node = getattr(conjunct, "this", None)
                    right_node = getattr(conjunct, "expression", None)
                    left_columns = [
                        item for item in (left_node.find_all(exp.Column) if left_node is not None else [])
                        if _nearest_select_ancestor(item) is select
                    ]
                    right_columns = [
                        item for item in (right_node.find_all(exp.Column) if right_node is not None else [])
                        if _nearest_select_ancestor(item) is select
                    ]
                    conjunct_columns = [*left_columns, *right_columns]
                    conjunct_usages = [usage_payload(column) for column in conjunct_columns]
                    if any(
                        usage is None or usage.get("resolution_status") in {"ambiguous", "unresolved"}
                        for usage in conjunct_usages
                    ):
                        predicate_has_unresolved_columns = True
                    if operator not in {None, "=", "<=>", "!="} and conjunct_columns:
                        temporal_or_range_predicates.append(rendered[:4000])

                    if operator and len(left_columns) == 1 and len(right_columns) == 1:
                        left_usage = usage_payload(left_columns[0])
                        right_usage = usage_payload(right_columns[0])
                        left_relation_id = str((left_usage or {}).get("relation_id") or "") or None
                        pair_right_relation_id = str((right_usage or {}).get("relation_id") or "") or None

                        # Canonical orientation follows JOIN rowsets rather than the
                        # textual order of operands in the predicate.  This keeps the
                        # joined relation on the right even for ``b.id = a.id``.
                        if left_relation_id == right_relation_id and pair_right_relation_id != right_relation_id:
                            left_usage, right_usage = right_usage, left_usage
                            left_columns, right_columns = right_columns, left_columns
                            left_relation_id, pair_right_relation_id = pair_right_relation_id, left_relation_id

                        if left_relation_id:
                            condition_relation_ids.add(left_relation_id)
                        if pair_right_relation_id:
                            condition_relation_ids.add(pair_right_relation_id)
                        if left_relation_id and pair_right_relation_id and left_relation_id == pair_right_relation_id:
                            additional_predicates.append(rendered[:4000])
                            continue
                        pair_status = (
                            "confirmed"
                            if left_relation_id and pair_right_relation_id and left_relation_id != pair_right_relation_id
                            else "partial"
                        )
                        column_pairs.append({
                            "left_column_usage_id": (left_usage or {}).get("sql_column_usage_id"),
                            "left_relation_id": left_relation_id,
                            "left_relation_name": (left_usage or {}).get("relation_name"),
                            "left_column": (left_usage or {}).get("column_name") or _restore_sql_placeholders(str(getattr(left_columns[0], "name", None) or ""), placeholder_tokens),
                            "right_column_usage_id": (right_usage or {}).get("sql_column_usage_id"),
                            "right_relation_id": pair_right_relation_id,
                            "right_relation_name": (right_usage or {}).get("relation_name"),
                            "right_column": (right_usage or {}).get("column_name") or _restore_sql_placeholders(str(getattr(right_columns[0], "name", None) or ""), placeholder_tokens),
                            "operator": operator,
                            "predicate": rendered[:4000],
                            "predicate_role": "equality_key" if operator in {"=", "<=>"} else "range_or_temporal",
                            "resolution_status": pair_status,
                        })
                    elif operator and left_columns and right_columns:
                        left_usages = [usage_payload(column) for column in left_columns]
                        right_usages = [usage_payload(column) for column in right_columns]
                        left_side_relation_ids = list(dict.fromkeys(
                            str((usage or {}).get("relation_id"))
                            for usage in left_usages
                            if (usage or {}).get("relation_id")
                        ))
                        right_side_relation_ids = list(dict.fromkeys(
                            str((usage or {}).get("relation_id"))
                            for usage in right_usages
                            if (usage or {}).get("relation_id")
                        ))
                        left_expression_node = left_node
                        right_expression_node = right_node
                        if right_relation_id in left_side_relation_ids and right_relation_id not in right_side_relation_ids:
                            left_usages, right_usages = right_usages, left_usages
                            left_side_relation_ids, right_side_relation_ids = right_side_relation_ids, left_side_relation_ids
                            left_expression_node, right_expression_node = right_expression_node, left_expression_node
                        relation_overlap = set(left_side_relation_ids) & set(right_side_relation_ids)
                        if left_side_relation_ids and right_side_relation_ids and not relation_overlap:
                            condition_relation_ids.update(left_side_relation_ids)
                            condition_relation_ids.update(right_side_relation_ids)
                            expression_status = "partial" if predicate_has_unresolved_columns else "confirmed"

                            def expression_columns(usages: list[dict[str, Any] | None]) -> list[dict[str, Any]]:
                                result: list[dict[str, Any]] = []
                                seen: set[tuple[str, str, str]] = set()
                                for usage in usages:
                                    if usage is None:
                                        continue
                                    key = (
                                        str(usage.get("relation_id") or ""),
                                        str(usage.get("column_name") or ""),
                                        str(usage.get("sql_column_usage_id") or ""),
                                    )
                                    if key in seen:
                                        continue
                                    seen.add(key)
                                    result.append({
                                        "column_usage_id": usage.get("sql_column_usage_id"),
                                        "relation_id": usage.get("relation_id"),
                                        "relation_name": usage.get("relation_name"),
                                        "column": usage.get("column_name"),
                                        "resolution_status": usage.get("resolution_status"),
                                    })
                                return result

                            expression_links.append({
                                "left_expression": _node_sql(left_expression_node, placeholder_tokens)[:4000],
                                "left_relation_ids": left_side_relation_ids,
                                "left_relation_names": [
                                    item.get("relation_name") for item in scope_relations
                                    if item.get("sql_relation_id") in left_side_relation_ids
                                ],
                                "left_columns": expression_columns(left_usages),
                                "right_expression": _node_sql(right_expression_node, placeholder_tokens)[:4000],
                                "right_relation_ids": right_side_relation_ids,
                                "right_relation_names": [
                                    item.get("relation_name") for item in scope_relations
                                    if item.get("sql_relation_id") in right_side_relation_ids
                                ],
                                "right_columns": expression_columns(right_usages),
                                "operator": operator,
                                "predicate": rendered[:4000],
                                "predicate_role": "equality_expression" if operator in {"=", "<=>"} else "range_or_temporal_expression",
                                "resolution_status": expression_status,
                            })
                        else:
                            additional_predicates.append(rendered[:4000])
                    else:
                        additional_predicates.append(rendered[:4000])

                left_relation_ids = sorted(
                    item for item in condition_relation_ids
                    if item and item != right_relation_id
                )
                if not left_relation_ids:
                    left_relation_ids = list(dict.fromkeys(accumulated_relation_ids))

                if using_columns:
                    for column_name in using_columns:
                        unique_left_relation_id = left_relation_ids[0] if len(left_relation_ids) == 1 else None
                        left_relation = next(
                            (item for item in scope_relations if item.get("sql_relation_id") == unique_left_relation_id),
                            None,
                        )
                        column_pairs.append({
                            "left_column_usage_id": None,
                            "left_relation_id": unique_left_relation_id,
                            "left_relation_candidate_ids": left_relation_ids if len(left_relation_ids) != 1 else [],
                            "left_relation_name": (left_relation or {}).get("relation_name"),
                            "left_relation_candidate_names": [
                                item.get("relation_name") for item in scope_relations
                                if item.get("sql_relation_id") in left_relation_ids
                            ] if len(left_relation_ids) != 1 else [],
                            "left_column": column_name,
                            "right_column_usage_id": None,
                            "right_relation_id": right_relation_id,
                            "right_relation_name": (right_relation or {}).get("relation_name"),
                            "right_column": column_name,
                            "operator": "=",
                            "predicate": f"USING ({column_name})",
                            "predicate_role": "equality_key",
                            "resolution_status": "confirmed" if unique_left_relation_id and right_relation_id else "partial",
                        })

                join_kind = _join_type(join)
                condition_kind = _join_condition_kind(join)
                participant_ids = list(dict.fromkeys([*left_relation_ids, *([right_relation_id] if right_relation_id else [])]))
                pair_statuses = {str(item.get("resolution_status")) for item in [*column_pairs, *expression_links]}
                if right_relation_id and left_relation_ids and not predicate_has_unresolved_columns and (
                    condition_kind == "cross"
                    or condition_kind == "natural"
                    or (using_columns and column_pairs and pair_statuses <= {"confirmed"})
                    or (condition_kind == "on" and (column_pairs or expression_links) and pair_statuses <= {"confirmed"})
                ):
                    resolution_status = "confirmed"
                elif right_relation_id:
                    resolution_status = "partial"
                else:
                    resolution_status = "unresolved"
                resolution_reasons: list[str] = []
                if right_relation_id is None:
                    resolution_reasons.append("right_relation_unresolved")
                if not left_relation_ids:
                    resolution_reasons.append("left_relation_unresolved")
                if predicate_has_unresolved_columns:
                    resolution_reasons.append("predicate_column_unresolved_or_ambiguous")
                if condition_kind == "on" and not column_pairs and not expression_links:
                    resolution_reasons.append("cross_relation_predicate_not_resolved")
                if using_columns and any(item.get("resolution_status") != "confirmed" for item in column_pairs):
                    resolution_reasons.append("using_left_relation_ambiguous")
                participant_relations = [
                    item for item in scope_relations
                    if item.get("sql_relation_id") in participant_ids
                ]
                physical_join_confirmed = bool(participant_relations) and resolution_status == "confirmed" and all(
                    item.get("relation_kind") in {"physical", "physical_template"}
                    for item in participant_relations
                )
                predicate_sql = _node_sql(condition, placeholder_tokens)[:8000] if condition is not None else None
                identity = "|".join([
                    query_id,
                    scope_id,
                    str(join_ordinal),
                    str(right_relation_id or ""),
                    str(predicate_sql or ""),
                    ",".join(using_columns),
                ])
                join_edges.append({
                    "sql_join_edge_id": f"sql_join_edge_{repo_id}_{_hash(identity, n=16)}",
                    "fact_type": "sql_join_edge",
                    "repo_id": repo_id,
                    "query_id": query_id,
                    "scope_id": scope_id,
                    "join_ordinal": join_ordinal,
                    "join_type": join_kind,
                    "condition_kind": condition_kind,
                    "left_relation_ids": left_relation_ids,
                    "left_relation_id": left_relation_ids[0] if len(left_relation_ids) == 1 else None,
                    "left_relation_names": [
                        item.get("relation_name") for item in scope_relations
                        if item.get("sql_relation_id") in left_relation_ids
                    ],
                    "right_relation_id": right_relation_id,
                    "right_relation_name": (right_relation or {}).get("relation_name"),
                    "right_relation_kind": (right_relation or {}).get("relation_kind"),
                    "participating_relation_ids": participant_ids,
                    "predicate": predicate_sql,
                    "using_columns": using_columns,
                    "column_pairs": column_pairs,
                    "expression_links": expression_links,
                    "additional_predicates": additional_predicates,
                    "temporal_or_range_predicates": list(dict.fromkeys([
                        *temporal_or_range_predicates,
                        *[
                            item.get("predicate") for item in column_pairs
                            if item.get("predicate_role") == "range_or_temporal"
                        ],
                        *[
                            item.get("predicate") for item in expression_links
                            if item.get("predicate_role") == "range_or_temporal_expression"
                        ],
                    ])),
                    "resolution_status": resolution_status,
                    "resolution_reasons": list(dict.fromkeys(resolution_reasons)),
                    "physical_join_confirmed": physical_join_confirmed,
                    "file": file,
                    "line_start": line_start,
                    "evidence": [{
                        "relative_file": file,
                        "line_start": line_start,
                        "extractor": "sql_profile_scoped_ast",
                        "scope_id": scope_id,
                    }],
                    **maturity_props({
                        "sql_statement": "confirmed",
                        "persistence_write": "not_applicable",
                        "physical_storage": "confirmed" if physical_join_confirmed else "unresolved",
                        "field_mapping": "confirmed" if resolution_status == "confirmed" else "unresolved",
                        "source_boundary": "not_applicable",
                        "end_to_end_trace": "not_applicable",
                    }),
                })
                if right_relation_id and right_relation_id not in accumulated_relation_ids:
                    accumulated_relation_ids.append(right_relation_id)

    projections_by_scope: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for projection in projections:
        projections_by_scope[str(projection.get("scope_id"))].append(projection)
    for items in projections_by_scope.values():
        items.sort(key=lambda item: int(item.get("projection_ordinal") or 0))

    # Bind write targets only to top-level output SELECT scopes, never to nested CTE projections.
    for expression_index, expression in enumerate(expressions or [], 1):
        if expression is None or not isinstance(expression, (exp.Insert, exp.Create)):
            continue
        target_node = getattr(expression, "this", None)
        target_name = _ast_relation_name(target_node, placeholder_tokens)
        if not target_name:
            continue
        source_expression = expression.args.get("expression")
        output_selects = _set_output_selects(source_expression)
        select_nodes = list(expression.find_all(exp.Select))
        select_local_ids = {id(node): f"e{expression_index}_s{idx}" for idx, node in enumerate(select_nodes, 1)}
        global_scope_ids = {
            local_id: f"sql_select_scope_{repo_id}_{_hash(query_id + ':' + local_id, n=16)}"
            for local_id in select_local_ids.values()
        }
        source_scope_ids = [
            global_scope_ids[select_local_ids[id(select)]]
            for select in output_selects
            if id(select) in select_local_ids
        ]
        explicit_columns = _ast_target_columns(target_node, placeholder_tokens)
        operation_kind = "insert_overwrite" if isinstance(expression, exp.Insert) and bool(expression.args.get("overwrite")) else (
            "insert" if isinstance(expression, exp.Insert)
            else f"create_{str(expression.args.get('kind') or 'object').lower()}"
        )
        semantics = _relation_semantics(target_name)
        if not source_scope_ids:
            binding_mode = "no_select_source"
        elif explicit_columns:
            binding_mode = "explicit_target_columns"
        elif isinstance(expression, exp.Create):
            binding_mode = "create_output_schema"
        else:
            binding_mode = "projection_name_inferred"
        target_id = f"sql_write_target_{repo_id}_{_hash(query_id + ':' + target_name + ':' + operation_kind, n=16)}"
        branch_projection_counts = [len(projections_by_scope.get(scope_id, [])) for scope_id in source_scope_ids]
        branch_wildcard_flags = [
            any(bool(item.get("is_wildcard")) for item in projections_by_scope.get(scope_id, []))
            for scope_id in source_scope_ids
        ]
        arity_unknown = bool(explicit_columns) and any(branch_wildcard_flags)
        count_mismatch = bool(explicit_columns) and not arity_unknown and any(
            count != len(explicit_columns) for count in branch_projection_counts
        )
        arity_status = (
            "unknown_wildcard" if arity_unknown
            else "mismatch" if count_mismatch
            else "matched" if explicit_columns and source_scope_ids
            else "not_applicable"
        )
        field_mapping_status = (
            "partial" if count_mismatch or arity_unknown
            else "confirmed" if binding_mode in {"explicit_target_columns", "create_output_schema"} and source_scope_ids
            else "inferred" if binding_mode == "projection_name_inferred" and source_scope_ids
            else "not_applicable" if binding_mode == "no_select_source"
            else "unresolved"
        )
        target_status = "partial" if field_mapping_status in {"partial", "inferred"} else (
            "resolved" if field_mapping_status in {"confirmed", "not_applicable"} else "unresolved"
        )
        write_targets.append({
            "sql_write_target_id": target_id,
            "fact_type": "sql_write_target",
            "repo_id": repo_id,
            "query_id": query_id,
            "operation_kind": operation_kind,
            "target_relation_name": target_name,
            "target_relation_kind": semantics.get("relation_kind"),
            "target_logical_name": semantics.get("logical_name"),
            "target_placeholder_refs": semantics.get("placeholder_refs") or [],
            "explicit_target_columns": explicit_columns,
            "source_scope_ids": source_scope_ids,
            "branch_projection_counts": branch_projection_counts,
            "branch_wildcard_flags": branch_wildcard_flags,
            "arity_status": arity_status,
            "binding_mode": binding_mode,
            "resolution_status": target_status,
            "field_mapping_status": field_mapping_status,
            "count_mismatch": count_mismatch,
            "file": file,
            "line_start": line_start,
            "evidence": [{
                "relative_file": file,
                "line_start": line_start,
                "extractor": "sql_profile_scoped_ast",
            }],
            **maturity_props({
                "sql_statement": "confirmed",
                "persistence_write": "confirmed",
                "physical_storage": "unresolved" if semantics.get("relation_kind") == "physical_template" else "confirmed",
                "field_mapping": "confirmed" if field_mapping_status == "confirmed" else ("not_applicable" if field_mapping_status == "not_applicable" else "unresolved"),
                "source_boundary": "not_applicable",
                "end_to_end_trace": "not_applicable",
            }),
        })

        for branch_ordinal, scope_id in enumerate(source_scope_ids, 1):
            branch_projections = projections_by_scope.get(scope_id, [])
            branch_has_wildcard = any(bool(item.get("is_wildcard")) for item in branch_projections)

            binding_rows: list[tuple[int, str | None, dict[str, Any] | None, str, str]] = []
            if explicit_columns and branch_has_wildcard:
                # The target schema is known, but wildcard expansion is not. Preserve
                # every target column as an unresolved mapping instead of reporting a
                # false projection-count mismatch or guessing wildcard ordinals.
                for ordinal, target_column in enumerate(explicit_columns, 1):
                    binding_rows.append((ordinal, target_column, None, "explicit_columns_wildcard_unexpanded", "unresolved"))
            elif explicit_columns:
                max_ordinal = max(len(explicit_columns), len(branch_projections))
                for ordinal in range(1, max_ordinal + 1):
                    target_column = explicit_columns[ordinal - 1] if ordinal <= len(explicit_columns) else None
                    projection = branch_projections[ordinal - 1] if ordinal <= len(branch_projections) else None
                    mapping_status = "confirmed" if not count_mismatch else "partial"
                    binding_rows.append((ordinal, target_column, projection, "explicit_target_columns", mapping_status))
            else:
                for projection in branch_projections:
                    ordinal = int(projection.get("projection_ordinal") or 0)
                    output_name = projection.get("output_name")
                    target_column = None
                    mapping_status = "unresolved"
                    if binding_mode == "create_output_schema" and output_name and not projection.get("is_wildcard"):
                        target_column = output_name
                        mapping_status = "confirmed"
                    elif binding_mode == "projection_name_inferred" and output_name and not projection.get("is_wildcard"):
                        target_column = output_name
                        mapping_status = "inferred"
                    binding_rows.append((ordinal, target_column, projection, binding_mode, mapping_status))

            for ordinal, target_column, projection, mapping_basis, mapping_status in binding_rows:
                output_name = projection.get("output_name") if projection else None
                binding_id = f"sql_target_projection_binding_{repo_id}_{_hash(target_id + ':' + scope_id + ':' + str(branch_ordinal) + ':' + str(ordinal), n=16)}"
                target_projection_bindings.append({
                    "sql_target_projection_binding_id": binding_id,
                    "fact_type": "sql_target_projection_binding",
                    "repo_id": repo_id,
                    "query_id": query_id,
                    "write_target_id": target_id,
                    "target_relation_name": target_name,
                    "target_column": target_column,
                    "target_column_ordinal": ordinal,
                    "source_scope_id": scope_id,
                    "branch_ordinal": branch_ordinal,
                    "projection_id": projection.get("sql_projection_id") if projection else None,
                    "projection_output_name": output_name,
                    "mapping_basis": mapping_basis,
                    "mapping_status": mapping_status,
                    "projection_resolution_status": projection.get("resolution_status") if projection else None,
                    "file": file,
                    "line_start": line_start,
                    "evidence": [{
                        "relative_file": file,
                        "line_start": line_start,
                        "extractor": "sql_profile_scoped_ast",
                        "scope_id": scope_id,
                    }],
                    **maturity_props({
                        "sql_statement": "confirmed",
                        "persistence_write": "confirmed",
                        "physical_storage": "unresolved" if semantics.get("relation_kind") == "physical_template" else "confirmed",
                        "field_mapping": "confirmed" if mapping_status == "confirmed" else "unresolved",
                        "source_boundary": "not_applicable",
                        "end_to_end_trace": "not_applicable",
                    }),
                })

    projection_counts = Counter(str(item.get("scope_id")) for item in projections)
    column_usage_counts = Counter(str(item.get("scope_id")) for item in column_usages)
    for scope in scopes:
        scope_id = str(scope.get("sql_select_scope_id"))
        scope["projection_count"] = projection_counts.get(scope_id, scope.get("projection_count", 0))
        scope["column_usage_count"] = column_usage_counts.get(scope_id, 0)
    return scopes, relations, projections, column_usages, write_targets, target_projection_bindings, join_edges


def _sqlglot_tables_columns(normalized: str, placeholder_tokens: dict[str, str] | None = None) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]], str | None]:
    tables: list[dict[str, Any]] = []
    columns: list[dict[str, Any]] = []
    projections: list[dict[str, Any]] = []
    joins: list[dict[str, Any]] = []
    kind: str | None = None
    placeholder_tokens = placeholder_tokens or {}
    if sqlglot is None or exp is None:
        return tables, columns, projections, joins, None
    try:
        expressions = sqlglot.parse(normalized, read=None, error_level="ignore")
    except Exception:
        return tables, columns, projections, joins, None
    for expression in expressions or []:
        if expression is None:
            continue
        kind = kind or (expression.key or expression.__class__.__name__)
        for t in expression.find_all(exp.Table):
            table_parts = [getattr(t, "catalog", None), getattr(t, "db", None), getattr(t, "name", None)]
            raw_name = ".".join(str(part) for part in table_parts if part) or (t.sql(dialect="spark") if hasattr(t, "sql") else t.name)
            name = _canonical_object(_restore_sql_placeholders(raw_name, placeholder_tokens))
            if name:
                alias = None
                try:
                    alias = t.alias
                except Exception:
                    alias = None
                tables.append({"table": name, "alias": alias or None, "source": "sqlglot"})
        for c in expression.find_all(exp.Column):
            col = _restore_sql_placeholders(c.name, placeholder_tokens)
            table = _restore_sql_placeholders(getattr(c, "table", None) or None, placeholder_tokens)
            if col:
                columns.append({"column": col, "table_or_alias": table, "source": "sqlglot"})
        for sel in expression.find_all(exp.Select):
            for idx, e in enumerate(sel.expressions or [], 1):
                try:
                    expr_sql = _restore_sql_placeholders(e.sql(dialect="spark"), placeholder_tokens) or ""
                except Exception:
                    expr_sql = str(e)
                alias = None
                try:
                    alias = e.alias_or_name
                except Exception:
                    alias = None
                src_cols = []
                try:
                    src_cols = sorted({
                        _restore_sql_placeholders(f"{cc.table + '.' if cc.table else ''}{cc.name}", placeholder_tokens) or ""
                        for cc in e.find_all(exp.Column) if cc.name
                    })
                    src_cols = [item for item in src_cols if item]
                except Exception:
                    src_cols = []
                projections.append({"ordinal": idx, "target_column": alias, "expression": expr_sql[:2000], "source_columns": src_cols[:50]})
        for j in expression.find_all(exp.Join):
            try:
                join_sql = _restore_sql_placeholders(j.sql(dialect="spark"), placeholder_tokens) or ""
            except Exception:
                join_sql = str(j)
            joins.append({"join_expression": join_sql[:2000]})
    # De-duplicate while preserving order
    def dedup(items: list[dict[str, Any]], key: str) -> list[dict[str, Any]]:
        seen = set(); out = []
        for item in items:
            val = item.get(key)
            if not val or val in seen:
                continue
            seen.add(val); out.append(item)
        return out
    return dedup(tables, "table"), columns, projections, joins, kind


def _regex_sources(statement: str) -> tuple[list[dict[str, Any]], dict[str, str]]:
    ctes = {m.group("name").lower() for m in CTE_RE.finditer(statement)}
    aliases: dict[str, str] = {}
    out: list[dict[str, Any]] = []
    for m in FROM_JOIN_RE.finditer(statement):
        name = _canonical_object(m.group("name"))
        if not name or name.lower() in ctes:
            continue
        alias = m.group("alias")
        if alias and alias.lower() not in {"where", "join", "on", "group", "order", "left", "right", "inner", "outer", "full", "cross"}:
            aliases[alias] = name
        out.append({"table": name, "alias": alias, "source": "regex"})
    seen = set(); uniq = []
    for item in out:
        if item["table"] not in seen:
            seen.add(item["table"]); uniq.append(item)
    return uniq, aliases


def _scoped_source_coverage(
    regex_sources: list[dict[str, Any]],
    scoped_relations: list[dict[str, Any]],
    *,
    target: str | None,
) -> dict[str, Any]:
    """Compare lexical FROM/JOIN candidates with relations represented in the AST.

    This does not promote regex candidates to facts. It only prevents a syntactically
    accepted but truncated AST from being reported as complete.
    """
    target_key = normalize_name(str(target or ""))
    expected_by_key: dict[str, str] = {}
    for item in regex_sources:
        name = str(item.get("table") or "")
        key = normalize_name(name)
        # Only strong qualified/template names are suitable for a truncation check.
        # Bare identifiers may be CTEs, aliases, table-valued functions, or LATERAL
        # VIEW outputs and would create false parser-coverage gaps.
        is_strong_relation = "." in name or bool(_placeholder_occurrences(name))
        if name and key and key != target_key and is_strong_relation:
            expected_by_key.setdefault(key, name)
    actual_keys = {
        normalize_name(str(item.get("relation_name") or ""))
        for item in scoped_relations
        if item.get("relation_kind") in {"physical", "physical_template", "temporary"}
    }
    missing = [expected_by_key[key] for key in sorted(set(expected_by_key) - actual_keys)]
    return {
        "status": "complete" if not missing else "partial",
        "lexical_source_candidate_count": len(expected_by_key),
        "scoped_source_count": len(actual_keys),
        "missing_source_candidates": missing,
    }


def _classify_field(name: str) -> list[str]:
    low = normalize_name(name)
    flags: list[str] = []
    if any(tok in low for tok in IDENTIFIER_TOKENS):
        flags.append("identifier_or_key_candidate")
    if any(tok in low for tok in STATUS_TOKENS):
        flags.append("status_result_or_error_candidate")
    if any(tok in low for tok in TIME_TOKENS):
        flags.append("date_time_or_temporal_candidate")
    if any(tok in low for tok in AUDIT_TOKENS):
        flags.append("audit_version_or_lifecycle_candidate")
    if "partition" in low or low in {"dt", "business_dt", "load_dt", "report_dt"}:
        flags.append("partition_or_slice_candidate")
    return flags


def _expression_type(expr_text: str) -> str:
    low = expr_text.lower()
    if "case" in low:
        return "case_when"
    if re.search(r"\b(sum|count|avg|min|max|collect_set|collect_list)\s*\(", low):
        return "aggregation"
    if re.search(r"\bover\s*\(", low):
        return "window_function"
    if re.search(r"\b(coalesce|nvl|ifnull|nullif)\s*\(", low):
        return "null_defaulting"
    if re.search(r"\b(cast|to_date|date_format|substr|substring|upper|lower|trim)\s*\(", low):
        return "normalization_or_cast"
    if re.match(r"^[a-zA-Z_][a-zA-Z0-9_.]*$", expr_text.strip()):
        return "direct_column"
    if re.match(r"^['\"0-9]", expr_text.strip()):
        return "literal_or_constant"
    return "expression"


def _extract_statement(
    sql: str,
    *,
    repo: Path,
    repo_id: str,
    file: str,
    absolute_file: str,
    line_start: int,
    seq: int,
    unit_kind: str,
    observed_sql: str | None = None,
    local_binding_resolution: list[dict[str, Any]] | None = None,
) -> dict[str, Any] | None:
    normalized, placeholder_tokens = _normalize_sql_for_profile(sql)
    if not normalized or is_ignorable_sql_fragment(sql):
        return None
    restored_normalized = _restore_sql_placeholders(normalized, placeholder_tokens) or normalized
    qid = f"query_{repo_id}_{seq:06d}"
    target, operation = _extract_target(normalized)
    target = _restore_sql_placeholders(target, placeholder_tokens)
    observed_target_template = None
    target_name_resolution_basis_hint = None
    if observed_sql is not None and str(observed_sql) != str(sql):
        observed_normalized, observed_placeholder_tokens = _normalize_sql_for_profile(str(observed_sql))
        if observed_normalized:
            raw_target, _raw_operation = _extract_target(observed_normalized)
            observed_target_template = _restore_sql_placeholders(raw_target, observed_placeholder_tokens)
            if observed_target_template and target and observed_target_template != target:
                target_name_resolution_basis_hint = "file_local_script_bindings"
    cte_names = sorted({_restore_sql_placeholders(m.group("name"), placeholder_tokens) or m.group("name") for m in CTE_RE.finditer(normalized)})
    regex_sources, alias_map = _regex_sources(normalized)
    regex_sources = [
        {**item, "table": _restore_sql_placeholders(item.get("table"), placeholder_tokens), "alias": _restore_sql_placeholders(item.get("alias"), placeholder_tokens)}
        for item in regex_sources
    ]
    alias_map = {
        (_restore_sql_placeholders(alias, placeholder_tokens) or alias): (_restore_sql_placeholders(table, placeholder_tokens) or table)
        for alias, table in alias_map.items()
    }
    glot_tables, glot_cols, projections, joins, glot_kind = _sqlglot_tables_columns(normalized, placeholder_tokens)
    source_tables = glot_tables or regex_sources
    if target:
        source_tables = [x for x in source_tables if x.get("table") != target]
    source_tables = [{**item, **_relation_semantics(item.get("table"))} for item in source_tables]
    columns = glot_cols
    if not projections:
        # Best-effort regex projection extraction: top-level SELECT ... FROM only.
        m = re.search(r"\bselect\s+(?P<body>.*?)\bfrom\b", normalized, re.IGNORECASE | re.DOTALL)
        if m:
            for idx, part in enumerate(_split_columns_csv(m.group("body"))[:300], 1):
                alias_m = COLUMN_ALIAS_RE.search(part)
                alias = alias_m.group(1) if alias_m else None
                target_col = alias or part.split(".")[-1].strip().strip('`"')[:120]
                src_cols = re.findall(r"\b([a-zA-Z_][a-zA-Z0-9_]*\.)?([a-zA-Z_][a-zA-Z0-9_]*)\b", part)
                src_rendered = []
                for tbl, col in src_cols:
                    if col.lower() in {"case", "when", "then", "else", "end", "as", "cast", "sum", "count", "null", "true", "false"}:
                        continue
                    src_rendered.append(f"{tbl}{col}" if tbl else col)
                projections.append({
                    "ordinal": idx,
                    "target_column": _restore_sql_placeholders(target_col, placeholder_tokens),
                    "expression": _restore_sql_placeholders(part[:2000], placeholder_tokens),
                    "source_columns": sorted({_restore_sql_placeholders(item, placeholder_tokens) or item for item in src_rendered})[:50],
                })
    join_conditions = [
        _restore_sql_placeholders(" ".join(m.group("cond").split())[:2000], placeholder_tokens)
        for m in JOIN_CONDITION_RE.finditer(normalized)
    ]
    where_clause = None
    m = WHERE_RE.search(normalized)
    if m:
        where_clause = _restore_sql_placeholders(" ".join(m.group("body").split())[:3000], placeholder_tokens)
    group_by = None
    m = GROUP_BY_RE.search(normalized)
    if m:
        group_by = _restore_sql_placeholders(" ".join(m.group("body").split())[:2000], placeholder_tokens)
    partition_fields: list[str] = []
    m = PARTITION_RE.search(normalized)
    if m:
        partition_fields = [
            _restore_sql_placeholders(x.strip().split()[0].strip('`"'), placeholder_tokens) or x.strip().split()[0].strip('`"')
            for x in _split_columns_csv(m.group("body")) if x.strip()
        ]
    statement_type = operation or glot_kind or "unknown_sql"
    source_sql = str(observed_sql if observed_sql is not None else sql)
    evidence = {
        "file": str(Path(absolute_file)),
        "relative_file": file,
        "line_start": line_start,
        "line_end": line_start + source_sql.count("\n"),
        "extractor": "sql_profile",
        "snippet": source_sql[:4000],
    }
    scoped_evidence = [evidence]
    for binding in local_binding_resolution or ():
        scoped_evidence.append({
            "relative_file": file,
            "line_start": binding.get("binding_line_start"),
            "extractor": "sql_profile_file_local_binding_resolution",
            "sql_script_binding_id": binding.get("sql_script_binding_id"),
            "binding_name": binding.get("binding_name"),
            "resolution_basis": binding.get("scalar_resolution_basis"),
        })
    (
        select_scopes,
        scoped_relations,
        scoped_projections,
        scoped_column_usages,
        scoped_write_targets,
        scoped_target_projection_bindings,
        scoped_join_edges,
    ) = _build_scoped_sql_facts(
        normalized,
        placeholder_tokens=placeholder_tokens,
        repo_id=repo_id,
        query_id=qid,
        file=file,
        line_start=line_start,
        evidence=scoped_evidence,
    )
    if target_name_resolution_basis_hint:
        for write_target in scoped_write_targets:
            write_target["observed_target_relation_template"] = observed_target_template
            write_target["target_name_resolution_basis_hint"] = target_name_resolution_basis_hint
    scoped_source_coverage = _scoped_source_coverage(
        regex_sources, scoped_relations, target=target
    )
    source_columns = []
    for c in columns:
        name = c.get("column")
        if name:
            source_columns.append({**c, "classifiers": _classify_field(name)})
    target_columns = []
    for pr in projections:
        col = pr.get("target_column")
        if col:
            target_columns.append({
                "column": col,
                "expression": pr.get("expression"),
                "source_columns": pr.get("source_columns") or [],
                "transformation_type": _expression_type(str(pr.get("expression") or col)),
                "classifiers": _classify_field(str(col)),
            })
    patterns = []
    for name, rx, reason in PATTERN_HINTS:
        if rx.search(normalized) or (target and rx.search(target)):
            patterns.append({"pattern_type": name, "reason": reason, "candidate_signals": [_sql_navigation_signal(signal_type="sql_pattern_hint", target=target, basis=reason, recommended_action="inspect the concrete SQL statement if this pattern is decision-blocking")]})
    optimization_hints = []
    join_count = len(re.findall(r"\bjoin\b", normalized, re.IGNORECASE))
    for name, rx, reason in OPTIMIZATION_PATTERNS:
        if name == "many_joins":
            if join_count >= 5:
                optimization_hints.append({"hint_type": name, "reason": f"{join_count} JOIN clauses detected", "candidate_signals": [_sql_navigation_signal(signal_type="sql_optimization_hint", target=target, basis=f"{join_count} JOIN clauses detected", recommended_action="inspect SQL joins and keys if optimization/lineage decision depends on this hint")]})
            continue
        if rx.search(normalized):
            optimization_hints.append({"hint_type": name, "reason": reason, "candidate_signals": [_sql_navigation_signal(signal_type="sql_optimization_hint", target=target, basis=reason, recommended_action="inspect the concrete SQL statement if this hint is decision-blocking")]})
    statement_hash = _hash(restored_normalized, n=16)
    return {
        "query_id": qid,
        "repo_id": repo_id,
        "file": file,
        "absolute_file": str(Path(absolute_file)),
        "line_start": line_start,
        "line_end": line_start + sql.count("\n"),
        "unit_kind": unit_kind,
        "statement_type": statement_type,
        "operation": operation,
        "target_object": target,
        "source_objects": [x.get("table") for x in source_tables if x.get("table")],
        "source_tables_detailed": source_tables,
        "cte_names": cte_names,
        "alias_map": alias_map,
        "source_columns": source_columns[:500],
        "target_columns": target_columns[:500],
        "join_conditions": join_conditions[:50],
        "joins": joins[:50],
        "where_clause": where_clause,
        "group_by": group_by,
        "partition_fields": partition_fields,
        "patterns": patterns,
        "optimization_hints": optimization_hints,
        "statement_hash": statement_hash,
        "statement_preview": restored_normalized[:1500],
        "semantic_placeholders": _placeholder_occurrences(sql),
        "source_statement_template": source_sql[:4000] if source_sql != sql else None,
        "local_binding_resolution": local_binding_resolution or [],
        "select_scopes": select_scopes,
        "scoped_relations": scoped_relations,
        "scoped_projections": scoped_projections,
        "scoped_column_usages": scoped_column_usages,
        "scoped_write_targets": scoped_write_targets,
        "scoped_target_projection_bindings": scoped_target_projection_bindings,
        "scoped_join_edges": scoped_join_edges,
        "scoped_source_coverage_status": scoped_source_coverage["status"],
        "scoped_source_candidate_count": scoped_source_coverage["lexical_source_candidate_count"],
        "scoped_source_count": scoped_source_coverage["scoped_source_count"],
        "scoped_ast_missing_source_candidates": scoped_source_coverage["missing_source_candidates"],
        "evidence": scoped_evidence,
        **_sql_profile_query_contract(operation=operation, target=target, has_source_objects=bool(source_tables)),
    }



def _build_sql_semantic_placeholders(
    *,
    repo_id: str,
    project_code: str,
    system_name: str,
    queries: list[dict[str, Any]],
    script_bindings: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Build the semantic placeholder facts published by ``sql-analysis/v1``.

    Historical mart-specific aggregates were removed: the canonical SQL artifact
    publishes scoped statements, relations, dependencies and lineage directly.
    """
    bindings_by_file_name: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for binding in script_bindings:
        bindings_by_file_name[(
            str(binding.get("file") or ""),
            str(binding.get("binding_name") or "").lower(),
        )].append(binding)

    semantic_placeholders: list[dict[str, Any]] = []
    for query in queries:
        evidence = query.get("evidence") or []
        first_evidence = evidence[0] if evidence and isinstance(evidence[0], dict) else {}
        raw_sql = str(first_evidence.get("snippet") or query.get("statement_preview") or "")
        occurrences = query.get("semantic_placeholders") or _placeholder_occurrences(raw_sql)
        file = query.get("file")
        line_start = query.get("line_start")
        query_id = query.get("query_id")
        seen_usages: set[tuple[str, str, tuple[str, ...]]] = set()

        for occurrence in occurrences:
            placeholder = str(occurrence.get("name") or "")
            template = str(occurrence.get("raw") or "")
            following = raw_sql[
                int(occurrence.get("end") or 0): int(occurrence.get("end") or 0) + 80
            ]
            roles = (
                ["relation_schema"]
                if re.match(r"\s*\.\s*[a-zA-Z_]", following)
                else _placeholder_usage_roles(query, template, placeholder)
            )
            usage_key = (placeholder, template, tuple(roles))
            if usage_key in seen_usages:
                continue
            seen_usages.add(usage_key)

            candidates = [
                item
                for item in bindings_by_file_name.get((str(file or ""), placeholder.lower()), [])
                if int(item.get("line_start") or 0) <= int(line_start or 0)
                and item.get("scalar_value") is not None
            ]
            resolved_variants = sorted({
                str(item.get("scalar_value"))
                for item in candidates
                if item.get("scalar_value") is not None
            })
            schema_only = set(roles) <= {"relation_schema"}
            if len(resolved_variants) == 1:
                resolution_status = "locally_bound"
            elif schema_only:
                resolution_status = "logical_template"
            else:
                resolution_status = "unbound_semantic"

            semantic_placeholders.append({
                "sql_semantic_placeholder_id": (
                    f"sql_semantic_placeholder_{repo_id}_{_hash(str(query_id) + template + json.dumps(roles))}"
                ),
                "fact_type": "sql_semantic_placeholder",
                "repo_id": repo_id,
                "project_code": project_code,
                "system_name": system_name,
                "query_id": query_id,
                "placeholder": placeholder,
                "template": template,
                "syntax": occurrence.get("syntax"),
                "usage_roles": roles,
                "resolution_status": resolution_status,
                "resolved_variants": resolved_variants,
                "binding_ids": [item.get("sql_script_binding_id") for item in candidates],
                "affects_logical_sql_graph": not schema_only,
                "file": file,
                "line_start": line_start,
                "evidence": evidence[:1],
                "evidence_maturity_level": "confirmed",
            })

    return semantic_placeholders

def _build_scoped_direct_lineage(
    *,
    repo_id: str,
    projections: list[dict[str, Any]],
    column_usages: list[dict[str, Any]],
    relations: list[dict[str, Any]],
    write_targets: list[dict[str, Any]],
    target_bindings: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Build direct target-to-source-column lineage from validated scoped facts.

    The graph intentionally stops at CTE and derived relations. Recursive traversal
    to physical base columns is a later, separately testable step.
    """
    projection_by_id = {str(item.get("sql_projection_id")): item for item in projections}
    usage_by_id = {str(item.get("sql_column_usage_id")): item for item in column_usages}
    relation_by_id = {str(item.get("sql_relation_id")): item for item in relations}
    target_by_id = {str(item.get("sql_write_target_id")): item for item in write_targets}
    edges: list[dict[str, Any]] = []
    gaps: list[dict[str, Any]] = []

    def add_gap(binding: dict[str, Any], kind: str, *, projection: dict[str, Any] | None = None, usage: dict[str, Any] | None = None) -> None:
        identity = "|".join([
            str(binding.get("sql_target_projection_binding_id") or ""),
            kind,
            str((usage or {}).get("sql_column_usage_id") or ""),
        ])
        gaps.append({
            "sql_scoped_lineage_gap_id": f"sql_scoped_lineage_gap_{repo_id}_{_hash(identity, n=16)}",
            "fact_type": "sql_scoped_lineage_gap",
            "repo_id": repo_id,
            "query_id": binding.get("query_id"),
            "write_target_id": binding.get("write_target_id"),
            "target_relation_name": binding.get("target_relation_name"),
            "target_column": binding.get("target_column"),
            "projection_id": binding.get("projection_id"),
            "source_scope_id": binding.get("source_scope_id"),
            "source_column_usage_id": (usage or {}).get("sql_column_usage_id"),
            "source_column": (usage or {}).get("column_name"),
            "table_or_alias": (usage or {}).get("table_or_alias"),
            "target_mapping_status": binding.get("mapping_status"),
            "mapping_basis": binding.get("mapping_basis"),
            "projection_resolution_status": (projection or {}).get("resolution_status"),
            "gap_kind": kind,
            "impact": "direct_target_field_lineage_partial",
            "analysis_status": "partial",
            "file": binding.get("file"),
            "line_start": binding.get("line_start"),
            "evidence": binding.get("evidence") or [],
            **maturity_props({
                "sql_statement": "confirmed",
                "persistence_write": "confirmed",
                "physical_storage": "unresolved",
                "field_mapping": "unresolved",
                "source_boundary": "not_applicable",
                "end_to_end_trace": "not_applicable",
            }),
        })

    for binding in target_bindings:
        target = target_by_id.get(str(binding.get("write_target_id")))
        projection = projection_by_id.get(str(binding.get("projection_id")))
        if not binding.get("target_column"):
            add_gap(binding, "target_column_unresolved", projection=projection)
            continue
        if projection is None:
            gap_kind = (
                "wildcard_projection_unexpanded"
                if binding.get("mapping_basis") == "explicit_columns_wildcard_unexpanded"
                else "projection_missing"
            )
            add_gap(binding, gap_kind)
            continue
        mapping_status = str(binding.get("mapping_status") or "unresolved")
        if mapping_status not in {"confirmed", "inferred"}:
            add_gap(binding, "target_projection_mapping_partial", projection=projection)
        source_usage_ids = list(projection.get("source_column_usage_ids") or [])
        if not source_usage_ids:
            direct_status = "confirmed_direct" if mapping_status == "confirmed" else (
                "inferred_target" if mapping_status == "inferred" else "partial"
            )
            identity = "|".join([
                str(binding.get("sql_target_projection_binding_id")),
                "expression_without_column",
            ])
            edges.append({
                "sql_direct_column_lineage_id": f"sql_direct_column_lineage_{repo_id}_{_hash(identity, n=16)}",
                "fact_type": "sql_direct_column_lineage",
                "repo_id": repo_id,
                "query_id": binding.get("query_id"),
                "write_target_id": binding.get("write_target_id"),
                "target_projection_binding_id": binding.get("sql_target_projection_binding_id"),
                "target_relation_name": binding.get("target_relation_name"),
                "target_relation_kind": (target or {}).get("target_relation_kind"),
                "target_column": binding.get("target_column"),
                "target_mapping_status": mapping_status,
                "source_scope_id": binding.get("source_scope_id"),
                "projection_id": projection.get("sql_projection_id"),
                "projection_ordinal": projection.get("projection_ordinal"),
                "expression": projection.get("expression"),
                "expression_kind": projection.get("expression_kind"),
                "source_kind": "expression_without_column",
                "source_relation_id": None,
                "source_relation_name": None,
                "source_relation_kind": None,
                "source_column_usage_id": None,
                "source_column": None,
                "source_usage_role": None,
                "source_resolution_status": "not_applicable",
                "direct_lineage_status": direct_status,
                "physical_origin_status": "not_applicable",
                "branch_ordinal": binding.get("branch_ordinal"),
                "file": binding.get("file"),
                "line_start": binding.get("line_start"),
                "evidence": binding.get("evidence") or [],
                **maturity_props({
                    "sql_statement": "confirmed",
                    "persistence_write": "confirmed",
                    "physical_storage": "confirmed" if (target or {}).get("target_relation_kind") == "physical" else "unresolved",
                    "field_mapping": "confirmed" if mapping_status == "confirmed" else "unresolved",
                    "source_boundary": "not_applicable",
                    "end_to_end_trace": "not_applicable",
                }),
            })
            continue

        for usage_id in source_usage_ids:
            usage = usage_by_id.get(str(usage_id))
            if usage is None:
                add_gap(binding, "column_usage_missing", projection=projection)
                continue
            relation = relation_by_id.get(str(usage.get("relation_id"))) if usage.get("relation_id") else None
            semantic_parameter = usage.get("resolution_status") == "semantic_parameter"
            source_resolved = semantic_parameter or (usage.get("resolution_status") == "resolved" and relation is not None)
            if not source_resolved:
                add_gap(
                    binding,
                    "source_relation_ambiguous" if usage.get("resolution_status") == "ambiguous" else "source_relation_unresolved",
                    projection=projection,
                    usage=usage,
                )
            if mapping_status == "confirmed" and source_resolved:
                direct_status = "confirmed_direct"
            elif mapping_status == "inferred" and source_resolved:
                direct_status = "inferred_target"
            else:
                direct_status = "partial"
            relation_kind = (relation or {}).get("relation_kind")
            physical_origin_status = (
                "not_applicable" if semantic_parameter
                else "confirmed" if relation_kind == "physical"
                else "logical_template" if relation_kind == "physical_template"
                else "intermediate_not_traced" if relation_kind in {"cte", "derived"}
                else "unresolved"
            )
            identity = "|".join([
                str(binding.get("sql_target_projection_binding_id")),
                str(usage.get("sql_column_usage_id")),
            ])
            edges.append({
                "sql_direct_column_lineage_id": f"sql_direct_column_lineage_{repo_id}_{_hash(identity, n=16)}",
                "fact_type": "sql_direct_column_lineage",
                "repo_id": repo_id,
                "query_id": binding.get("query_id"),
                "write_target_id": binding.get("write_target_id"),
                "target_projection_binding_id": binding.get("sql_target_projection_binding_id"),
                "target_relation_name": binding.get("target_relation_name"),
                "target_relation_kind": (target or {}).get("target_relation_kind"),
                "target_column": binding.get("target_column"),
                "target_mapping_status": mapping_status,
                "source_scope_id": binding.get("source_scope_id"),
                "projection_id": projection.get("sql_projection_id"),
                "projection_ordinal": projection.get("projection_ordinal"),
                "expression": projection.get("expression"),
                "expression_kind": projection.get("expression_kind"),
                "source_kind": "semantic_parameter" if semantic_parameter else "column",
                "source_relation_id": (relation or {}).get("sql_relation_id"),
                "source_relation_name": (relation or {}).get("relation_name"),
                "source_relation_kind": relation_kind,
                "source_column_usage_id": usage.get("sql_column_usage_id"),
                "source_column": usage.get("column_name"),
                "source_table_or_alias": usage.get("table_or_alias"),
                "source_usage_role": usage.get("usage_role"),
                "source_resolution_status": usage.get("resolution_status"),
                "direct_lineage_status": direct_status,
                "physical_origin_status": physical_origin_status,
                "branch_ordinal": binding.get("branch_ordinal"),
                "file": binding.get("file"),
                "line_start": binding.get("line_start"),
                "evidence": binding.get("evidence") or [],
                **maturity_props({
                    "sql_statement": "confirmed",
                    "persistence_write": "confirmed",
                    "physical_storage": "confirmed" if (target or {}).get("target_relation_kind") == "physical" else "unresolved",
                    "field_mapping": "confirmed" if direct_status == "confirmed_direct" else "unresolved",
                    "source_boundary": "not_applicable",
                    "end_to_end_trace": "not_applicable",
                }),
            })
    return edges, gaps



def _build_scoped_recursive_lineage(
    *,
    repo_id: str,
    direct_lineage: list[dict[str, Any]],
    projections: list[dict[str, Any]],
    column_usages: list[dict[str, Any]],
    relations: list[dict[str, Any]],
    max_depth: int = 32,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Resolve direct lineage through CTE and derived relations.

    One result row represents one terminal branch from a target field to a
    physical/template column, semantic parameter, terminal expression, or an
    explicitly unresolved boundary. Set-operation branches are preserved; no
    branch is selected by confidence or name similarity.
    """
    projection_by_id = {str(item.get("sql_projection_id")): item for item in projections}
    usage_by_id = {str(item.get("sql_column_usage_id")): item for item in column_usages}
    relation_by_id = {str(item.get("sql_relation_id")): item for item in relations}
    projections_by_scope: dict[str, list[dict[str, Any]]] = defaultdict(list)
    relations_by_scope: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for projection in projections:
        projections_by_scope[str(projection.get("scope_id"))].append(projection)
    for relation in relations:
        relations_by_scope[str(relation.get("scope_id"))].append(relation)
    for items in projections_by_scope.values():
        items.sort(key=lambda item: int(item.get("projection_ordinal") or 0))

    paths: list[dict[str, Any]] = []
    gaps: list[dict[str, Any]] = []

    def _normalized(value: Any) -> str:
        return normalize_name(str(value or ""))

    def _path_evidence(direct: dict[str, Any], steps: list[dict[str, Any]]) -> list[dict[str, Any]]:
        values: list[dict[str, Any]] = []
        seen: set[str] = set()
        candidates = list(direct.get("evidence") or [])
        for step in steps:
            candidates.extend(step.get("evidence") or [])
        for item in candidates:
            key = json.dumps(item, ensure_ascii=False, sort_keys=True, default=str)
            if key in seen:
                continue
            seen.add(key)
            values.append(item)
        return values[:100]

    def _add_gap(
        direct: dict[str, Any],
        kind: str,
        *,
        relation: dict[str, Any] | None = None,
        column: str | None = None,
        scope_id: str | None = None,
        projection: dict[str, Any] | None = None,
        depth: int = 0,
        branch_path: list[dict[str, Any]] | None = None,
    ) -> None:
        identity = "|".join([
            str(direct.get("sql_direct_column_lineage_id") or ""),
            kind,
            str((relation or {}).get("sql_relation_id") or ""),
            str(column or ""),
            str(scope_id or ""),
            str((projection or {}).get("sql_projection_id") or ""),
            str(depth),
        ])
        gaps.append({
            "sql_scoped_lineage_gap_id": f"sql_scoped_lineage_gap_{repo_id}_{_hash(identity, n=16)}",
            "fact_type": "sql_scoped_lineage_gap",
            "repo_id": repo_id,
            "query_id": direct.get("query_id"),
            "write_target_id": direct.get("write_target_id"),
            "target_relation_name": direct.get("target_relation_name"),
            "target_column": direct.get("target_column"),
            "direct_lineage_id": direct.get("sql_direct_column_lineage_id"),
            "projection_id": (projection or {}).get("sql_projection_id"),
            "source_scope_id": scope_id,
            "source_relation_id": (relation or {}).get("sql_relation_id"),
            "source_relation_name": (relation or {}).get("relation_name"),
            "source_relation_kind": (relation or {}).get("relation_kind"),
            "source_column": column,
            "target_mapping_status": direct.get("target_mapping_status"),
            "gap_kind": kind,
            "impact": "recursive_target_field_lineage_partial",
            "analysis_status": "partial",
            "recursion_depth": depth,
            "branch_path": list(branch_path or []),
            "file": direct.get("file"),
            "line_start": direct.get("line_start"),
            "evidence": direct.get("evidence") or [],
            **maturity_props({
                "sql_statement": "confirmed",
                "persistence_write": "confirmed",
                "physical_storage": "unresolved",
                "field_mapping": "unresolved",
                "source_boundary": "not_applicable",
                "end_to_end_trace": "not_applicable",
            }),
        })

    def _emit_path(
        direct: dict[str, Any],
        *,
        terminal_kind: str,
        terminal_relation: dict[str, Any] | None,
        terminal_column: str | None,
        steps: list[dict[str, Any]],
        recursion_depth: int,
        recursive_resolution_status: str,
        physical_origin_status: str,
        terminal_usage: dict[str, Any] | None = None,
        terminal_expression: dict[str, Any] | None = None,
    ) -> None:
        if recursive_resolution_status == "resolved":
            if direct.get("direct_lineage_status") == "confirmed_direct":
                lineage_status = "confirmed"
            elif direct.get("direct_lineage_status") == "inferred_target":
                lineage_status = "inferred_target"
            else:
                lineage_status = "partial"
        elif recursive_resolution_status == "not_applicable":
            lineage_status = (
                "confirmed" if direct.get("direct_lineage_status") == "confirmed_direct"
                else "inferred_target" if direct.get("direct_lineage_status") == "inferred_target"
                else "partial"
            )
        else:
            lineage_status = "partial"
        step_signature = ":".join(
            "@".join([
                str(item.get("definition_scope_id") or ""),
                str(item.get("projection_id") or ""),
                str(item.get("source_relation_id") or ""),
                str(item.get("source_column") or ""),
            ])
            for item in steps
        )
        identity = "|".join([
            str(direct.get("sql_direct_column_lineage_id") or ""),
            terminal_kind,
            str((terminal_relation or {}).get("sql_relation_id") or ""),
            str(terminal_column or ""),
            step_signature,
            recursive_resolution_status,
        ])
        transformations = [{
            "projection_id": direct.get("projection_id"),
            "scope_id": direct.get("source_scope_id"),
            "output_name": direct.get("target_column"),
            "expression": direct.get("expression"),
            "expression_kind": direct.get("expression_kind"),
            "step_kind": "target_projection",
        }]
        transformations.extend({
            "projection_id": item.get("projection_id"),
            "scope_id": item.get("definition_scope_id"),
            "output_name": item.get("projection_output_name"),
            "expression": item.get("projection_expression"),
            "expression_kind": item.get("projection_expression_kind"),
            "step_kind": "intermediate_projection",
        } for item in steps if item.get("projection_id"))
        paths.append({
            "sql_recursive_column_lineage_id": f"sql_recursive_column_lineage_{repo_id}_{_hash(identity, n=16)}",
            "fact_type": "sql_recursive_column_lineage",
            "repo_id": repo_id,
            "query_id": direct.get("query_id"),
            "write_target_id": direct.get("write_target_id"),
            "target_projection_binding_id": direct.get("target_projection_binding_id"),
            "direct_lineage_id": direct.get("sql_direct_column_lineage_id"),
            "target_relation_name": direct.get("target_relation_name"),
            "target_relation_kind": direct.get("target_relation_kind"),
            "target_column": direct.get("target_column"),
            "target_mapping_status": direct.get("target_mapping_status"),
            "root_projection_id": direct.get("projection_id"),
            "root_expression": direct.get("expression"),
            "root_expression_kind": direct.get("expression_kind"),
            "terminal_source_kind": terminal_kind,
            "terminal_relation_id": (terminal_relation or {}).get("sql_relation_id"),
            "terminal_relation_name": (terminal_relation or {}).get("relation_name"),
            "terminal_relation_kind": (terminal_relation or {}).get("relation_kind"),
            "terminal_column_usage_id": (terminal_usage or {}).get("sql_column_usage_id"),
            "terminal_column": terminal_column,
            "terminal_expression": (terminal_expression or {}).get("expression"),
            "terminal_expression_kind": (terminal_expression or {}).get("expression_kind"),
            "recursion_depth": recursion_depth,
            "recursive_resolution_status": recursive_resolution_status,
            "lineage_status": lineage_status,
            "physical_origin_status": physical_origin_status,
            "branch_path": steps,
            "transformation_path": transformations,
            "file": direct.get("file"),
            "line_start": direct.get("line_start"),
            "evidence": _path_evidence(direct, steps),
            **maturity_props({
                "sql_statement": "confirmed",
                "persistence_write": "confirmed",
                "physical_storage": (
                    "confirmed" if physical_origin_status in {"confirmed", "logical_template"}
                    else "not_applicable" if physical_origin_status == "not_applicable"
                    else "unresolved"
                ),
                "field_mapping": "confirmed" if lineage_status == "confirmed" else "unresolved",
                "source_boundary": "not_applicable",
                "end_to_end_trace": "not_applicable",
            }),
        })

    def _projection_for_field(
        relation: dict[str, Any],
        column: str,
    ) -> list[tuple[str, dict[str, Any] | None, str]]:
        source_scope_ids = [str(item) for item in relation.get("source_scope_ids") or []]
        if not source_scope_ids:
            return []
        normalized_column = _normalized(column)
        first_scope_projections = projections_by_scope.get(source_scope_ids[0], [])
        first_matches = [
            item for item in first_scope_projections
            if not item.get("is_wildcard") and _normalized(item.get("output_name")) == normalized_column
        ]
        canonical_ordinal: int | None = None
        basis = "output_name"
        if len(first_matches) == 1:
            canonical_ordinal = int(first_matches[0].get("projection_ordinal") or 0)
        elif not first_matches and len(first_scope_projections) == 1 and not first_scope_projections[0].get("is_wildcard"):
            # A one-column intermediate has unambiguous ordinal correspondence even
            # when its external field name is supplied by a CTE/derived alias list.
            canonical_ordinal = int(first_scope_projections[0].get("projection_ordinal") or 0)
            basis = "single_projection_ordinal"
        if not canonical_ordinal:
            exact_ordinals = {
                int(item.get("projection_ordinal") or 0)
                for scope_id in source_scope_ids
                for item in projections_by_scope.get(scope_id, [])
                if not item.get("is_wildcard") and _normalized(item.get("output_name")) == normalized_column
            }
            if len(exact_ordinals) == 1:
                canonical_ordinal = next(iter(exact_ordinals))
                basis = "consistent_output_ordinal"
        if not canonical_ordinal and len(source_scope_ids) == 1:
            wildcard_projections = [
                item for item in first_scope_projections if item.get("is_wildcard")
            ]
            if len(wildcard_projections) == 1:
                return [(source_scope_ids[0], wildcard_projections[0], "wildcard_passthrough")]
        result: list[tuple[str, dict[str, Any] | None, str]] = []
        for scope_id in source_scope_ids:
            candidates = [
                item for item in projections_by_scope.get(scope_id, [])
                if int(item.get("projection_ordinal") or 0) == canonical_ordinal
            ] if canonical_ordinal else []
            result.append((scope_id, candidates[0] if len(candidates) == 1 else None, basis))
        return result

    def _wildcard_source_relation(scope_id: str, projection: dict[str, Any]) -> dict[str, Any] | None:
        expression = str(projection.get("expression") or "").strip()
        candidates = relations_by_scope.get(scope_id, [])
        if expression == "*":
            return candidates[0] if len(candidates) == 1 else None
        if expression.endswith(".*"):
            alias = expression[:-2].strip().strip('`"')
            matches = [
                item for item in candidates
                if alias.lower() in {
                    str(item.get("alias") or "").lower(),
                    str(item.get("relation_name") or "").lower(),
                    str(item.get("logical_name") or "").lower(),
                }
            ]
            return matches[0] if len(matches) == 1 else None
        return None

    def _resolve_intermediate(
        direct: dict[str, Any],
        relation: dict[str, Any],
        column: str,
        *,
        steps: list[dict[str, Any]],
        visited: frozenset[tuple[str, str]],
        depth: int,
    ) -> None:
        relation_id = str(relation.get("sql_relation_id") or "")
        state = (relation_id, _normalized(column))
        if state in visited:
            _add_gap(direct, "recursive_lineage_cycle", relation=relation, column=column, depth=depth, branch_path=steps)
            _emit_path(
                direct,
                terminal_kind="unresolved",
                terminal_relation=relation,
                terminal_column=column,
                steps=steps,
                recursion_depth=depth,
                recursive_resolution_status="partial",
                physical_origin_status="unresolved",
            )
            return
        if depth > max_depth:
            _add_gap(direct, "recursive_lineage_depth_exceeded", relation=relation, column=column, depth=depth, branch_path=steps)
            _emit_path(
                direct,
                terminal_kind="unresolved",
                terminal_relation=relation,
                terminal_column=column,
                steps=steps,
                recursion_depth=depth,
                recursive_resolution_status="partial",
                physical_origin_status="unresolved",
            )
            return
        definition_candidates = _projection_for_field(relation, column)
        if not definition_candidates:
            _add_gap(direct, "intermediate_definition_unavailable", relation=relation, column=column, depth=depth, branch_path=steps)
            _emit_path(
                direct,
                terminal_kind="unresolved",
                terminal_relation=relation,
                terminal_column=column,
                steps=steps,
                recursion_depth=depth,
                recursive_resolution_status="partial",
                physical_origin_status="unresolved",
            )
            return
        next_visited = visited | {state}
        for branch_ordinal, (scope_id, projection, mapping_basis) in enumerate(definition_candidates, 1):
            if projection is None:
                _add_gap(
                    direct,
                    "intermediate_projection_unresolved",
                    relation=relation,
                    column=column,
                    scope_id=scope_id,
                    depth=depth,
                    branch_path=steps,
                )
                unresolved_step = {
                    "intermediate_relation_id": relation.get("sql_relation_id"),
                    "intermediate_relation_name": relation.get("relation_name"),
                    "intermediate_relation_kind": relation.get("relation_kind"),
                    "referenced_column": column,
                    "definition_scope_id": scope_id,
                    "definition_branch_ordinal": branch_ordinal,
                    "projection_mapping_basis": mapping_basis,
                    "projection_id": None,
                    "projection_ordinal": None,
                    "projection_output_name": None,
                    "projection_expression": None,
                    "projection_expression_kind": None,
                    "source_usage_id": None,
                    "source_relation_id": None,
                    "source_relation_name": None,
                    "source_relation_kind": None,
                    "source_column": None,
                    "evidence": relation.get("evidence") or [],
                }
                _emit_path(
                    direct,
                    terminal_kind="unresolved",
                    terminal_relation=relation,
                    terminal_column=column,
                    steps=steps + [unresolved_step],
                    recursion_depth=depth,
                    recursive_resolution_status="partial",
                    physical_origin_status="unresolved",
                )
                continue
            if projection.get("is_wildcard"):
                wildcard_source = _wildcard_source_relation(scope_id, projection) if mapping_basis == "wildcard_passthrough" else None
                if wildcard_source is None:
                    _add_gap(
                        direct,
                        "intermediate_wildcard_unexpanded",
                        relation=relation,
                        column=column,
                        scope_id=scope_id,
                        projection=projection,
                        depth=depth,
                        branch_path=steps,
                    )
                    _emit_path(
                        direct,
                        terminal_kind="unresolved",
                        terminal_relation=relation,
                        terminal_column=column,
                        steps=steps,
                        recursion_depth=depth,
                        recursive_resolution_status="partial",
                        physical_origin_status="unresolved",
                    )
                    continue
                wildcard_step = {
                    "intermediate_relation_id": relation.get("sql_relation_id"),
                    "intermediate_relation_name": relation.get("relation_name"),
                    "intermediate_relation_kind": relation.get("relation_kind"),
                    "referenced_column": column,
                    "definition_scope_id": scope_id,
                    "definition_branch_ordinal": branch_ordinal,
                    "projection_mapping_basis": mapping_basis,
                    "projection_id": projection.get("sql_projection_id"),
                    "projection_ordinal": projection.get("projection_ordinal"),
                    "projection_output_name": projection.get("output_name"),
                    "projection_expression": projection.get("expression"),
                    "projection_expression_kind": projection.get("expression_kind"),
                    "source_usage_id": None,
                    "source_relation_id": wildcard_source.get("sql_relation_id"),
                    "source_relation_name": wildcard_source.get("relation_name"),
                    "source_relation_kind": wildcard_source.get("relation_kind"),
                    "source_column": column,
                    "evidence": projection.get("evidence") or [],
                }
                next_steps = steps + [wildcard_step]
                wildcard_kind = wildcard_source.get("relation_kind")
                if wildcard_kind in {"physical", "physical_template"}:
                    _emit_path(
                        direct,
                        terminal_kind="column",
                        terminal_relation=wildcard_source,
                        terminal_column=column,
                        steps=next_steps,
                        recursion_depth=depth,
                        recursive_resolution_status="resolved",
                        physical_origin_status="confirmed" if wildcard_kind == "physical" else "logical_template",
                    )
                elif wildcard_kind in {"cte", "derived"}:
                    _resolve_intermediate(
                        direct,
                        wildcard_source,
                        column,
                        steps=next_steps,
                        visited=next_visited,
                        depth=depth + 1,
                    )
                else:
                    _add_gap(direct, "recursive_source_relation_unresolved", relation=wildcard_source, column=column, scope_id=scope_id, projection=projection, depth=depth, branch_path=next_steps)
                    _emit_path(
                        direct,
                        terminal_kind="unresolved",
                        terminal_relation=wildcard_source,
                        terminal_column=column,
                        steps=next_steps,
                        recursion_depth=depth,
                        recursive_resolution_status="partial",
                        physical_origin_status="unresolved",
                    )
                continue
            usage_ids = list(projection.get("source_column_usage_ids") or [])
            base_step = {
                "intermediate_relation_id": relation.get("sql_relation_id"),
                "intermediate_relation_name": relation.get("relation_name"),
                "intermediate_relation_kind": relation.get("relation_kind"),
                "referenced_column": column,
                "definition_scope_id": scope_id,
                "definition_branch_ordinal": branch_ordinal,
                "projection_mapping_basis": mapping_basis,
                "projection_id": projection.get("sql_projection_id"),
                "projection_ordinal": projection.get("projection_ordinal"),
                "projection_output_name": projection.get("output_name"),
                "projection_expression": projection.get("expression"),
                "projection_expression_kind": projection.get("expression_kind"),
                "evidence": projection.get("evidence") or [],
            }
            if not usage_ids:
                _emit_path(
                    direct,
                    terminal_kind="expression_without_column",
                    terminal_relation=None,
                    terminal_column=None,
                    steps=steps + [{**base_step, "source_usage_id": None, "source_relation_id": None, "source_relation_name": None, "source_relation_kind": None, "source_column": None}],
                    recursion_depth=depth,
                    recursive_resolution_status="not_applicable",
                    physical_origin_status="not_applicable",
                    terminal_expression=projection,
                )
                continue
            for usage_id in usage_ids:
                usage = usage_by_id.get(str(usage_id))
                if usage is None:
                    _add_gap(direct, "recursive_column_usage_missing", relation=relation, column=column, scope_id=scope_id, projection=projection, depth=depth, branch_path=steps)
                    _emit_path(
                        direct,
                        terminal_kind="unresolved",
                        terminal_relation=relation,
                        terminal_column=column,
                        steps=steps + [base_step],
                        recursion_depth=depth,
                        recursive_resolution_status="partial",
                        physical_origin_status="unresolved",
                    )
                    continue
                source_relation = relation_by_id.get(str(usage.get("relation_id"))) if usage.get("relation_id") else None
                step = {
                    **base_step,
                    "source_usage_id": usage.get("sql_column_usage_id"),
                    "source_relation_id": (source_relation or {}).get("sql_relation_id"),
                    "source_relation_name": (source_relation or {}).get("relation_name"),
                    "source_relation_kind": (source_relation or {}).get("relation_kind"),
                    "source_column": usage.get("column_name"),
                }
                next_steps = steps + [step]
                if usage.get("resolution_status") == "semantic_parameter":
                    _emit_path(
                        direct,
                        terminal_kind="semantic_parameter",
                        terminal_relation=None,
                        terminal_column=usage.get("column_name"),
                        steps=next_steps,
                        recursion_depth=depth,
                        recursive_resolution_status="not_applicable",
                        physical_origin_status="not_applicable",
                        terminal_usage=usage,
                    )
                    continue
                if usage.get("resolution_status") != "resolved" or source_relation is None:
                    _add_gap(
                        direct,
                        "recursive_source_relation_ambiguous" if usage.get("resolution_status") == "ambiguous" else "recursive_source_relation_unresolved",
                        relation=relation,
                        column=usage.get("column_name"),
                        scope_id=scope_id,
                        projection=projection,
                        depth=depth,
                        branch_path=next_steps,
                    )
                    _emit_path(
                        direct,
                        terminal_kind="unresolved",
                        terminal_relation=None,
                        terminal_column=usage.get("column_name"),
                        steps=next_steps,
                        recursion_depth=depth,
                        recursive_resolution_status="partial",
                        physical_origin_status="unresolved",
                        terminal_usage=usage,
                    )
                    continue
                source_kind = source_relation.get("relation_kind")
                if source_kind in {"physical", "physical_template"}:
                    _emit_path(
                        direct,
                        terminal_kind="column",
                        terminal_relation=source_relation,
                        terminal_column=usage.get("column_name"),
                        steps=next_steps,
                        recursion_depth=depth,
                        recursive_resolution_status="resolved",
                        physical_origin_status="confirmed" if source_kind == "physical" else "logical_template",
                        terminal_usage=usage,
                    )
                elif source_kind in {"cte", "derived"}:
                    _resolve_intermediate(
                        direct,
                        source_relation,
                        str(usage.get("column_name") or ""),
                        steps=next_steps,
                        visited=next_visited,
                        depth=depth + 1,
                    )
                else:
                    _add_gap(direct, "recursive_source_relation_unresolved", relation=source_relation, column=usage.get("column_name"), scope_id=scope_id, projection=projection, depth=depth, branch_path=next_steps)
                    _emit_path(
                        direct,
                        terminal_kind="unresolved",
                        terminal_relation=source_relation,
                        terminal_column=usage.get("column_name"),
                        steps=next_steps,
                        recursion_depth=depth,
                        recursive_resolution_status="partial",
                        physical_origin_status="unresolved",
                        terminal_usage=usage,
                    )

    for direct in direct_lineage:
        source_kind = direct.get("source_kind")
        relation = relation_by_id.get(str(direct.get("source_relation_id"))) if direct.get("source_relation_id") else None
        relation_kind = (relation or {}).get("relation_kind")
        if source_kind == "expression_without_column":
            _emit_path(
                direct,
                terminal_kind="expression_without_column",
                terminal_relation=None,
                terminal_column=None,
                steps=[],
                recursion_depth=0,
                recursive_resolution_status="not_applicable",
                physical_origin_status="not_applicable",
                terminal_expression={"expression": direct.get("expression"), "expression_kind": direct.get("expression_kind")},
            )
        elif source_kind == "semantic_parameter":
            _emit_path(
                direct,
                terminal_kind="semantic_parameter",
                terminal_relation=None,
                terminal_column=direct.get("source_column"),
                steps=[],
                recursion_depth=0,
                recursive_resolution_status="not_applicable",
                physical_origin_status="not_applicable",
            )
        elif relation_kind in {"physical", "physical_template"}:
            _emit_path(
                direct,
                terminal_kind="column",
                terminal_relation=relation,
                terminal_column=direct.get("source_column"),
                steps=[],
                recursion_depth=0,
                recursive_resolution_status="resolved",
                physical_origin_status="confirmed" if relation_kind == "physical" else "logical_template",
                terminal_usage=usage_by_id.get(str(direct.get("source_column_usage_id"))),
            )
        elif relation_kind in {"cte", "derived"}:
            _resolve_intermediate(
                direct,
                relation,
                str(direct.get("source_column") or ""),
                steps=[],
                visited=frozenset(),
                depth=1,
            )
        else:
            _emit_path(
                direct,
                terminal_kind="unresolved",
                terminal_relation=relation,
                terminal_column=direct.get("source_column"),
                steps=[],
                recursion_depth=0,
                recursive_resolution_status="partial",
                physical_origin_status="unresolved",
                terminal_usage=usage_by_id.get(str(direct.get("source_column_usage_id"))),
            )
    unique_paths = {str(item.get("sql_recursive_column_lineage_id")): item for item in paths}
    unique_gaps = {str(item.get("sql_scoped_lineage_gap_id")): item for item in gaps}
    return list(unique_paths.values()), list(unique_gaps.values())



_SIMPLE_SCRIPT_PLACEHOLDER_RE = re.compile(
    r"\$\{\$?([A-Za-z_][A-Za-z0-9_.]*)\}|\$([A-Za-z_][A-Za-z0-9_.]*)"
)


def _apply_repository_materialized_relation_contracts(
    *,
    script_bindings: list[dict[str, Any]],
    queries: list[dict[str, Any]],
    scopes: list[dict[str, Any]],
    relations: list[dict[str, Any]],
    projections: list[dict[str, Any]],
    column_usages: list[dict[str, Any]],
    write_targets: list[dict[str, Any]],
) -> dict[str, int]:
    """Propagate repository-owned write schemas to later physical reads.

    The pass is deliberately narrow and facts-only:

    * only file-local literal/template bindings are evaluated;
    * every placeholder in the target identity must resolve;
    * target/read names must match exactly after resolution;
    * complete schemas come only from explicit DDL, CTAS/view output, or
      ``CREATE TABLE LIKE`` a relation with a complete schema;
    * ordinary INSERT statements remain observed writes, not full schemas;
    * all schema definitions for the same target must agree.

    No repository, schema, table, or naming convention is interpreted.
    """

    bindings_by_file_name: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for binding in script_bindings:
        bindings_by_file_name[(
            str(binding.get("file") or ""),
            str(binding.get("binding_name") or "").lower(),
        )].append(binding)
    for rows in bindings_by_file_name.values():
        rows.sort(key=lambda item: (int(item.get("line_start") or 0), str(item.get("sql_script_binding_id") or "")))

    def binding_value(file: str, name: str, before_line: int, stack: tuple[str, ...]) -> str | None:
        lowered = name.lower()
        if lowered in stack:
            return None
        candidates = [
            item for item in bindings_by_file_name.get((file, lowered), [])
            if int(item.get("line_start") or 0) <= before_line
        ]
        if not candidates:
            return None
        binding = candidates[-1]
        kind = str(binding.get("binding_kind") or "")
        raw = binding.get("scalar_value")
        if raw is None or kind not in {"literal", "template"}:
            return None
        value = str(raw)
        return resolve_template(file, value, int(binding.get("line_start") or before_line), (*stack, lowered))

    def resolve_template(file: str, text: str, before_line: int, stack: tuple[str, ...] = ()) -> str | None:
        current = str(text)
        for _ in range(16):
            unresolved = False

            def replace(match: re.Match[str]) -> str:
                nonlocal unresolved
                name = str(match.group(1) or match.group(2) or "")
                value = binding_value(file, name, before_line, stack)
                if value is None:
                    unresolved = True
                    return match.group(0)
                return value

            updated = _SIMPLE_SCRIPT_PLACEHOLDER_RE.sub(replace, current)
            if updated == current:
                if unresolved or _SIMPLE_SCRIPT_PLACEHOLDER_RE.search(updated):
                    return None
                return _canonical_object(updated)
            current = updated
        return None

    scope_by_id = {str(item.get("sql_select_scope_id")): item for item in scopes}
    query_by_id = {str(item.get("query_id")): item for item in queries}

    # A complete physical schema must come from a schema-defining statement:
    # explicit DDL, CTAS/view output, or CREATE TABLE LIKE a relation whose
    # schema is itself complete. Plain INSERT statements are observed writes,
    # not proof that the listed/projected columns are the whole table schema.
    definition_candidates: dict[str, list[dict[str, Any]]] = defaultdict(list)
    like_edges: list[dict[str, Any]] = []
    for target in write_targets:
        target["resolved_target_relation_name"] = None
        target["target_name_resolution_basis"] = "unresolved"
        target["observed_write_columns"] = []
        target["observed_write_contract_basis"] = None
        target["materialized_output_columns"] = []
        target["materialized_output_contract_status"] = "unavailable"
        target["materialized_output_contract_basis"] = None
        target["materialized_contract_definition_ids"] = []
        resolved_name = resolve_template(
            str(target.get("file") or ""),
            str(target.get("target_relation_name") or ""),
            int(target.get("line_start") or 0),
        )
        if not resolved_name:
            continue
        target["resolved_target_relation_name"] = resolved_name
        target["target_name_resolution_basis"] = str(
            target.get("target_name_resolution_basis_hint")
            or (
                "exact_identity" if resolved_name == target.get("target_relation_name")
                else "file_local_script_bindings"
            )
        )

        query = query_by_id.get(str(target.get("query_id") or "")) or {}
        operation = str(target.get("operation_kind") or "")
        explicit = [str(item) for item in target.get("explicit_target_columns") or [] if item]
        source_scope_ids = [str(item) for item in target.get("source_scope_ids") or []]
        source_contracts = [scope_by_id.get(item) for item in source_scope_ids]
        complete_source_columns: list[str] | None = None
        if source_contracts and all(
            contract is not None and contract.get("output_contract_status") == "complete"
            for contract in source_contracts
        ):
            first_columns = [str(item) for item in source_contracts[0].get("output_columns") or []]
            if first_columns and all(
                [str(item) for item in contract.get("output_columns") or []] == first_columns
                for contract in source_contracts
            ):
                complete_source_columns = first_columns

        if operation not in {"create_table", "create_view"}:
            observed = explicit or complete_source_columns or []
            if observed and len({item.lower() for item in observed}) == len(observed):
                target["observed_write_columns"] = observed
                target["observed_write_contract_basis"] = (
                    "explicit_insert_target_columns" if explicit
                    else "complete_insert_source_scope"
                )
            continue

        partition_columns = [str(item) for item in query.get("partition_fields") or [] if item]
        output_columns: list[str] | None = None
        definition_basis: str | None = None
        if explicit:
            output_columns = [*explicit, *partition_columns]
            definition_basis = "explicit_ddl_columns"
        elif complete_source_columns is not None:
            output_columns = [*complete_source_columns, *partition_columns]
            definition_basis = (
                "create_view_complete_source_scope"
                if operation == "create_view" else "ctas_complete_source_scope"
            )
        else:
            source_objects = [str(item) for item in query.get("source_objects") or [] if item]
            preview = str(query.get("statement_preview") or "")
            if (
                operation == "create_table"
                and not source_scope_ids
                and len(source_objects) == 1
                and re.search(r"(?i)\bLIKE\b", preview)
            ):
                resolved_source = resolve_template(
                    str(target.get("file") or ""),
                    source_objects[0],
                    int(target.get("line_start") or 0),
                )
                if resolved_source:
                    like_edges.append({
                        "target_name": resolved_name.lower(),
                        "source_name": resolved_source.lower(),
                        "write_target_id": target.get("sql_write_target_id"),
                        "file": target.get("file"),
                        "line_start": target.get("line_start"),
                    })

        if output_columns is None:
            continue
        if not output_columns or len({item.lower() for item in output_columns}) != len(output_columns):
            target["materialized_output_contract_status"] = "conflict"
            continue
        definition_candidates[resolved_name.lower()].append({
            "write_target_id": target.get("sql_write_target_id"),
            "target_relation_name": target.get("target_relation_name"),
            "resolved_target_relation_name": resolved_name,
            "output_columns": output_columns,
            "definition_basis": definition_basis,
            "file": target.get("file"),
            "line_start": target.get("line_start"),
            "inherited_definition_ids": [],
        })

    # Resolve direct definitions first, then propagate CREATE TABLE LIKE edges.
    materialized_contracts: dict[str, dict[str, Any]] = {}
    conflicts: set[str] = set()

    def refresh_contracts() -> bool:
        changed = False
        for normalized_name, candidates in definition_candidates.items():
            signatures = {
                tuple(str(item).lower() for item in candidate["output_columns"])
                for candidate in candidates
            }
            if len(signatures) != 1:
                if normalized_name not in conflicts:
                    conflicts.add(normalized_name)
                    materialized_contracts.pop(normalized_name, None)
                    changed = True
                continue
            if normalized_name in conflicts:
                continue
            columns = list(candidates[0]["output_columns"])
            definition_ids = sorted({
                str(identifier)
                for candidate in candidates
                for identifier in [
                    candidate.get("write_target_id"),
                    *(candidate.get("inherited_definition_ids") or []),
                ]
                if identifier
            })
            current = materialized_contracts.get(normalized_name)
            replacement = {
                "output_columns": columns,
                "definitions": candidates,
                "definition_ids": definition_ids,
            }
            if current != replacement:
                materialized_contracts[normalized_name] = replacement
                changed = True
        return changed

    refresh_contracts()
    propagated_edges: set[tuple[str, str, str]] = set()
    for _ in range(len(like_edges) + len(definition_candidates) + 1):
        added = False
        for edge in like_edges:
            source_contract = materialized_contracts.get(edge["source_name"])
            if source_contract is None or edge["target_name"] in conflicts:
                continue
            edge_key = (
                edge["target_name"],
                edge["source_name"],
                str(edge.get("write_target_id") or ""),
            )
            if edge_key in propagated_edges:
                continue
            propagated_edges.add(edge_key)
            definition_candidates[edge["target_name"]].append({
                "write_target_id": edge.get("write_target_id"),
                "target_relation_name": edge["target_name"],
                "resolved_target_relation_name": edge["target_name"],
                "output_columns": list(source_contract["output_columns"]),
                "definition_basis": "create_table_like_complete_relation",
                "source_relation_name": edge["source_name"],
                "file": edge.get("file"),
                "line_start": edge.get("line_start"),
                "inherited_definition_ids": list(source_contract.get("definition_ids") or []),
            })
            added = True
        changed = refresh_contracts()
        if not added and not changed:
            break

    for target in write_targets:
        normalized_name = str(target.get("resolved_target_relation_name") or "").lower()
        if not normalized_name:
            continue
        if normalized_name in conflicts:
            target["materialized_output_contract_status"] = "conflict"
            continue
        contract = materialized_contracts.get(normalized_name)
        if contract is None:
            if target.get("observed_write_columns"):
                target["materialized_output_contract_status"] = "observed_write_only"
            continue
        target["materialized_output_columns"] = list(contract["output_columns"])
        target["materialized_output_contract_status"] = "complete"
        own_definition = next((
            item for item in contract["definitions"]
            if item.get("write_target_id") == target.get("sql_write_target_id")
        ), None)
        target["materialized_output_contract_basis"] = (
            (own_definition or {}).get("definition_basis")
            or "repository_materialized_relation_contract"
        )
        target["materialized_contract_definition_ids"] = list(contract.get("definition_ids") or [])

    relation_by_id = {str(item.get("sql_relation_id")): item for item in relations}
    enriched_physical_relations = 0
    for relation in relations:
        if relation.get("relation_kind") not in {"physical", "physical_template"}:
            continue
        contract = materialized_contracts.get(str(relation.get("relation_name") or "").lower())
        if contract is None:
            continue
        relation["output_columns"] = list(contract["output_columns"])
        relation["output_contract_status"] = "complete"
        relation["output_contract_basis"] = "repository_write_target_contract"
        relation["output_contract_materialization_provenance"] = [
            {
                "write_target_id": item.get("write_target_id"),
                "target_relation_name": item.get("target_relation_name"),
                "resolved_target_relation_name": item.get("resolved_target_relation_name"),
                "contract_basis": item.get("definition_basis"),
                "source_relation_name": item.get("source_relation_name"),
                "file": item.get("file"),
                "line_start": item.get("line_start"),
            }
            for item in contract["definitions"]
        ]
        enriched_physical_relations += 1

    # Re-evaluate intermediate wildcard contracts whose physical source has just
    # gained a complete repository-owned contract.  Iterate for multi-level CTEs.
    enriched_intermediate_relations = 0
    for _ in range(len(relations) + 1):
        changed = False
        for relation in relations:
            if relation.get("relation_kind") not in {"cte", "derived"}:
                continue
            if relation.get("output_contract_status") == "complete":
                continue
            provenance = list(relation.get("output_contract_wildcard_provenance") or [])
            if not provenance:
                continue
            expanded = list(relation.get("output_columns") or [])
            updated_provenance: list[dict[str, Any]] = []
            complete = True
            for item in provenance:
                source_relation_id = str(item.get("source_relation_id") or "")
                if not source_relation_id:
                    updated_provenance.append(dict(item))
                    complete = False
                    continue
                source = relation_by_id.get(source_relation_id)
                source_complete = source is not None and source.get("output_contract_status") == "complete"
                updated = dict(item)
                if source_complete:
                    updated["resolution_status"] = "resolved"
                    if item.get("resolution_status") != "resolved":
                        updated["resolution_basis"] = "complete_relation_output_contract"
                else:
                    updated["resolution_status"] = "unresolved"
                    updated["resolution_basis"] = "source_output_contract_incomplete"
                updated_provenance.append(updated)
                if not source_complete:
                    complete = False
                    continue
                expanded.extend(str(column) for column in source.get("output_columns") or [])
            normalized = [item.lower() for item in expanded]
            duplicates = len(set(normalized)) != len(normalized)
            if not complete or duplicates:
                relation["output_contract_wildcard_provenance"] = updated_provenance
                continue
            relation["output_columns"] = list(dict.fromkeys(expanded))
            relation["output_contract_status"] = "complete"
            relation["output_contract_basis"] = "expanded_repository_materialized_wildcard"
            relation["output_contract_wildcard_provenance"] = updated_provenance
            relation.setdefault("output_contract_materialization_provenance", [])
            for item in updated_provenance:
                source = relation_by_id.get(str(item.get("source_relation_id") or ""))
                relation["output_contract_materialization_provenance"].extend(
                    list((source or {}).get("output_contract_materialization_provenance") or [])
                )
            for source_scope_id in relation.get("source_scope_ids") or []:
                scope = scope_by_id.get(str(source_scope_id))
                if scope is not None:
                    scope["output_columns"] = list(relation["output_columns"])
                    scope["output_contract_status"] = "complete"
                    scope["output_contract_basis"] = relation["output_contract_basis"]
                    scope["output_contract_wildcard_provenance"] = updated_provenance
            enriched_intermediate_relations += 1
            changed = True
        if not changed:
            break

    relations_by_scope: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for relation in relations:
        relations_by_scope[str(relation.get("scope_id"))].append(relation)
    resolved_usages = 0
    for usage in column_usages:
        if usage.get("resolution_basis") != "ambiguous_unqualified":
            continue
        primary = [
            item for item in relations_by_scope.get(str(usage.get("scope_id")), [])
            if item.get("relation_kind") != "generated"
        ]
        if not primary or not all(item.get("output_contract_status") == "complete" for item in primary):
            continue
        field = str(usage.get("column_name") or "").lower()
        owners = [
            item for item in primary
            if field in {str(column).lower() for column in item.get("output_columns") or []}
        ]
        if len(owners) != 1:
            continue
        owner = owners[0]
        usage["relation_id"] = owner.get("sql_relation_id")
        usage["relation_name"] = owner.get("relation_name")
        usage["relation_kind"] = owner.get("relation_kind")
        usage["resolution_status"] = "resolved"
        usage["resolution_basis"] = "unique_complete_relation_output_contract"
        usage["resolution_contract_status"] = owner.get("output_contract_status")
        usage["resolution_contract_basis"] = owner.get("output_contract_basis")
        usage.update(maturity_props({
            "sql_statement": "confirmed",
            "persistence_write": "not_applicable",
            "physical_storage": "confirmed" if owner.get("relation_kind") in {"physical", "physical_template"} else "not_applicable",
            "field_mapping": "confirmed",
            "source_boundary": "not_applicable",
            "end_to_end_trace": "not_applicable",
        }))
        resolved_usages += 1

    usage_by_id = {str(item.get("sql_column_usage_id")): item for item in column_usages}
    resolved_projections = 0
    for projection in projections:
        if projection.get("is_wildcard") or projection.get("resolution_status") != "partial":
            continue
        source_usages = [usage_by_id.get(str(item)) for item in projection.get("source_column_usage_ids") or []]
        if source_usages and all(
            item is not None and item.get("resolution_status") not in {"ambiguous", "unresolved"}
            for item in source_usages
        ):
            projection["resolution_status"] = "resolved"
            projection["resolution_basis"] = "scoped_ast_after_materialized_relation_contract"
            projection.update(maturity_props({
                "sql_statement": "confirmed",
                "persistence_write": "not_applicable",
                "physical_storage": "not_applicable",
                "field_mapping": "confirmed",
                "source_boundary": "not_applicable",
                "end_to_end_trace": "not_applicable",
            }))
            resolved_projections += 1

    return {
        "resolved_write_target_names": sum(1 for item in write_targets if item.get("resolved_target_relation_name")),
        "complete_materialized_targets": len(materialized_contracts),
        "enriched_physical_relations": enriched_physical_relations,
        "enriched_intermediate_relations": enriched_intermediate_relations,
        "resolved_column_usages": resolved_usages,
        "resolved_projections": resolved_projections,
    }

def _resolve_sql_with_file_local_bindings(
    statement: str,
    *,
    file: str,
    line_start: int,
    script_bindings: list[dict[str, Any]],
) -> tuple[str, list[dict[str, Any]]]:
    """Resolve exact file-local scalar bindings in one SQL fragment.

    Only bindings observed earlier in the same file participate.  Runtime or
    workflow placeholders remain untouched.  The returned diagnostics retain
    the binding ids/bases used so derived scoped SQL facts remain traceable to
    source evidence.
    """
    by_name: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for binding in script_bindings:
        if str(binding.get("file") or "") != str(file or ""):
            continue
        if int(binding.get("line_start") or 0) > int(line_start or 0):
            continue
        if binding.get("scalar_value") is None:
            continue
        by_name[str(binding.get("binding_name") or "").lower()].append(binding)
    for rows in by_name.values():
        rows.sort(key=lambda item: (int(item.get("line_start") or 0), str(item.get("sql_script_binding_id") or "")))

    placeholder_re = re.compile(
        r"\$\{\s*\$?(?P<braced>[A-Za-z_][A-Za-z0-9_.]*)\s*\}|"
        r"(?<![A-Za-z0-9$])\$(?P<bare>[A-Za-z_][A-Za-z0-9_.]*)"
    )
    current = str(statement or "")
    applied: dict[str, dict[str, Any]] = {}
    for _ in range(16):
        changed = False

        def replace(match: re.Match[str]) -> str:
            nonlocal changed
            name = str(match.group("braced") or match.group("bare") or "")
            rows = by_name.get(name.lower()) or []
            if not rows:
                return match.group(0)
            binding = rows[-1]
            value = binding.get("scalar_value")
            if value is None:
                return match.group(0)
            changed = True
            binding_id = str(binding.get("sql_script_binding_id") or "")
            applied[binding_id] = {
                "sql_script_binding_id": binding_id,
                "binding_name": binding.get("binding_name"),
                "binding_line_start": binding.get("line_start"),
                "scalar_resolution_basis": binding.get("scalar_resolution_basis") or "observed_scalar_binding",
            }
            return str(value)

        updated = placeholder_re.sub(replace, current)
        current = updated
        if not changed:
            break
    return current, [applied[key] for key in sorted(applied)]


def _build_repo_artifacts(repo: Path, repo_id: str, project_code: str, system_name: str, files: list[Path]) -> dict[str, Any]:
    sql_units, config_hints = _iter_sql_units(repo, files)
    workflow_bindings = _build_workflow_bindings(repo_id, config_hints)
    queries: list[dict[str, Any]] = []
    select_scopes: list[dict[str, Any]] = []
    scoped_relations: list[dict[str, Any]] = []
    scoped_projections: list[dict[str, Any]] = []
    scoped_column_usages: list[dict[str, Any]] = []
    scoped_write_targets: list[dict[str, Any]] = []
    scoped_target_projection_bindings: list[dict[str, Any]] = []
    scoped_join_edges: list[dict[str, Any]] = []
    script_statements: list[dict[str, Any]] = []
    raw_script_statements: dict[str, str] = {}
    sql_fragments: list[tuple[dict[str, Any], int, str]] = []
    comments: list[dict[str, Any]] = []
    for unit in sql_units:
        text = unit["sql"]
        comments.extend(_extract_comments(text, unit["file"], repo_id))
        statements = _split_sql_script_fragments(text) if unit["kind"] == "sql_file" else [(unit.get("line_start") or 1, text)]
        for local_line, stmt in statements:
            absolute_line = (unit.get("line_start") or 1) + local_line - 1
            classification = _classify_script_fragment(stmt)
            if classification["classification"] != "sql":
                script_fact = _script_statement_fact(
                    repo_id=repo_id,
                    file=unit["file"],
                    absolute_file=unit["absolute_file"],
                    line_start=absolute_line,
                    statement=stmt,
                    classification=classification,
                )
                script_statements.append(script_fact)
                raw_script_statements[str(script_fact.get("sql_script_statement_id") or "")] = stmt
                continue
            sql_fragments.append((unit, absolute_line, stmt))

    # File-local bindings are observed before SQL extraction so exact local
    # string templates can be substituted into later SQL statements.  This is
    # deliberately not workflow/config evaluation: only preceding bindings in
    # the same source file are eligible.
    script_calls = _build_script_calls(repo_id, script_statements)
    script_bindings = _build_script_bindings(
        repo_id,
        script_statements,
        raw_statements=raw_script_statements,
    )

    seq = 1
    for unit, absolute_line, stmt in sql_fragments:
        resolved_stmt, local_binding_resolution = _resolve_sql_with_file_local_bindings(
            stmt,
            file=unit["file"],
            line_start=absolute_line,
            script_bindings=script_bindings,
        )
        q = _extract_statement(
            resolved_stmt,
            repo=repo,
            repo_id=repo_id,
            file=unit["file"],
            absolute_file=unit["absolute_file"],
            line_start=absolute_line,
            seq=seq,
            unit_kind=unit["kind"],
            observed_sql=stmt,
            local_binding_resolution=local_binding_resolution,
        )
        if q:
            query_scopes = q.pop("select_scopes", [])
            query_relations = q.pop("scoped_relations", [])
            query_projections = q.pop("scoped_projections", [])
            query_column_usages = q.pop("scoped_column_usages", [])
            query_write_targets = q.pop("scoped_write_targets", [])
            query_target_bindings = q.pop("scoped_target_projection_bindings", [])
            query_join_edges = q.pop("scoped_join_edges", [])
            q["select_scope_ids"] = [item.get("sql_select_scope_id") for item in query_scopes]
            q["write_target_ids"] = [item.get("sql_write_target_id") for item in query_write_targets]
            select_scopes.extend(query_scopes)
            scoped_relations.extend(query_relations)
            scoped_projections.extend(query_projections)
            scoped_column_usages.extend(query_column_usages)
            scoped_write_targets.extend(query_write_targets)
            scoped_target_projection_bindings.extend(query_target_bindings)
            scoped_join_edges.extend(query_join_edges)
            queries.append(q)
            seq += 1
    materialized_relation_contract_summary = _apply_repository_materialized_relation_contracts(
        script_bindings=script_bindings,
        queries=queries,
        scopes=select_scopes,
        relations=scoped_relations,
        projections=scoped_projections,
        column_usages=scoped_column_usages,
        write_targets=scoped_write_targets,
    )
    embedded_sql = _build_embedded_sql_facts(repo_id, script_statements)
    script_invocations = _build_script_invocations(repo_id, script_statements, sql_units)
    scoped_direct_lineage, scoped_lineage_gaps = _build_scoped_direct_lineage(
        repo_id=repo_id,
        projections=scoped_projections,
        column_usages=scoped_column_usages,
        relations=scoped_relations,
        write_targets=scoped_write_targets,
        target_bindings=scoped_target_projection_bindings,
    )
    scoped_recursive_lineage, recursive_lineage_gaps = _build_scoped_recursive_lineage(
        repo_id=repo_id,
        direct_lineage=scoped_direct_lineage,
        projections=scoped_projections,
        column_usages=scoped_column_usages,
        relations=scoped_relations,
    )
    scoped_lineage_gaps.extend(recursive_lineage_gaps)
    for query in queries:
        missing_sources = list(query.get("scoped_ast_missing_source_candidates") or [])
        if not missing_sources:
            continue
        identity = "|".join([
            str(query.get("query_id") or ""),
            "scoped_ast_source_coverage_incomplete",
            *sorted(map(str, missing_sources)),
        ])
        scoped_lineage_gaps.append({
            "sql_scoped_lineage_gap_id": f"sql_scoped_lineage_gap_{repo_id}_{_hash(identity, n=16)}",
            "fact_type": "sql_scoped_lineage_gap",
            "repo_id": repo_id,
            "query_id": query.get("query_id"),
            "file": query.get("file"),
            "line_start": query.get("line_start"),
            "gap_kind": "scoped_ast_source_coverage_incomplete",
            "analysis_status": "partial",
            "impact": "source_inventory_partial",
            "missing_source_candidates": missing_sources,
            "evidence": query.get("evidence") or [],
            **maturity_props({
                "sql_statement": "confirmed",
                "persistence_write": "not_applicable",
                "physical_storage": "unresolved",
                "field_mapping": "unresolved",
                "source_boundary": "not_applicable",
                "end_to_end_trace": "unresolved",
            }),
        })
    objects: dict[str, dict[str, Any]] = {}
    columns: dict[tuple[str, str], dict[str, Any]] = {}
    table_lineage: list[dict[str, Any]] = []
    column_lineage: list[dict[str, Any]] = []
    patterns: list[dict[str, Any]] = []
    optimization_hints: list[dict[str, Any]] = []
    for q in queries:
        evidence = q.get("evidence") or []
        target = q.get("target_object")
        if target:
            obj = objects.setdefault(target, {
                "object_name": target,
                "repo_id": repo_id,
                "object_type": "table_or_view",
                "as_target_count": 0,
                "as_source_count": 0,
                "query_ids": [],
                "files": [],
                "evidence": evidence[:1],
            })
            obj["as_target_count"] += 1
            obj["query_ids"].append(q["query_id"])
            obj["files"].append(q["file"])
        for src in q.get("source_objects") or []:
            obj = objects.setdefault(src, {
                "object_name": src,
                "repo_id": repo_id,
                "object_type": "table_or_view",
                "as_target_count": 0,
                "as_source_count": 0,
                "query_ids": [],
                "files": [],
                "evidence": evidence[:1],
            })
            obj["as_source_count"] += 1
            obj["query_ids"].append(q["query_id"])
            obj["files"].append(q["file"])
            if target:
                table_lineage.append({
                    "lineage_id": f"tbl_{repo_id}_{_hash(q['query_id'] + src + target)}",
                    "repo_id": repo_id,
                    "query_id": q["query_id"],
                    "source_object": src,
                    "target_object": target,
                    "operation": q.get("operation") or q.get("statement_type"),
                    "file": q["file"],
                    "line_start": q["line_start"],
                    **maturity_props({"sql_statement": "confirmed", "field_mapping": "confirmed", "physical_storage": "confirmed" if target else "unresolved", "source_boundary": "not_applicable", "end_to_end_trace": "not_applicable"}),
                    "evidence": evidence[:1],
                })
        for col in q.get("target_columns") or []:
            cname = str(col.get("column") or "").strip()
            if not cname or not target:
                continue
            key = (target, cname.lower())
            info = columns.setdefault(key, {
                "repo_id": repo_id,
                "object_name": target,
                "column_name": cname,
                "normalized_column": normalize_name(cname),
                "classifiers": col.get("classifiers") or [],
                "expressions": [],
                "query_ids": [],
                "evidence": evidence[:1],
            })
            info["expressions"].append(col.get("expression"))
            info["query_ids"].append(q["query_id"])
            for src_col in col.get("source_columns") or []:
                column_lineage.append({
                    "lineage_id": f"col_{repo_id}_{_hash(q['query_id'] + str(src_col) + target + cname)}",
                    "repo_id": repo_id,
                    "query_id": q["query_id"],
                    "target_object": target,
                    "target_column": cname,
                    "source_column": src_col,
                    "expression": col.get("expression"),
                    "transformation_type": col.get("transformation_type"),
                    "file": q["file"],
                    "line_start": q["line_start"],
                    **maturity_props({"sql_statement": "confirmed", "field_mapping": "confirmed", "physical_storage": "confirmed", "source_boundary": "not_applicable", "end_to_end_trace": "not_applicable"}),
                    "evidence": evidence[:1],
                })
        for col in q.get("source_columns") or []:
            for src in q.get("source_objects") or [col.get("table_or_alias") or "unknown"]:
                cname = str(col.get("column") or "").strip()
                if not cname:
                    continue
                key = (str(src), cname.lower())
                info = columns.setdefault(key, {
                    "repo_id": repo_id,
                    "object_name": str(src),
                    "column_name": cname,
                    "normalized_column": normalize_name(cname),
                    "classifiers": col.get("classifiers") or [],
                    "expressions": [],
                    "query_ids": [],
                    "evidence": evidence[:1],
                })
                info["query_ids"].append(q["query_id"])
        for p in q.get("patterns") or []:
            patterns.append({**p, "repo_id": repo_id, "query_id": q["query_id"], "target_object": target, "file": q["file"], "line_start": q["line_start"], "evidence": evidence[:1]})
        for h in q.get("optimization_hints") or []:
            optimization_hints.append({**h, "repo_id": repo_id, "query_id": q["query_id"], "target_object": target, "file": q["file"], "line_start": q["line_start"], "evidence": evidence[:1]})
    # Normalize files/query_ids arrays and add object types.
    for obj in objects.values():
        obj["files"] = sorted(set(obj.get("files") or []))[:50]
        obj["query_ids"] = sorted(set(obj.get("query_ids") or []))[:200]
        if obj["as_target_count"] and obj["as_source_count"]:
            obj["role"] = "source_and_target"
        elif obj["as_target_count"]:
            obj["role"] = "target"
        else:
            obj["role"] = "source"
        low = obj["object_name"].lower()
        if "view" in low:
            obj["object_type"] = "view_or_table"
        elif any(tok in low for tok in ["tmp", "temp"]):
            obj["object_type"] = "temporary_or_intermediate"
        elif any(tok in low for tok in ["topic", "kafka"]):
            obj["object_type"] = "topic_like"
    for info in columns.values():
        info["query_ids"] = sorted(set(info.get("query_ids") or []))[:200]
        info["expressions"] = [x for x in dict.fromkeys(info.get("expressions") or []) if x][:20]
    attributes = []
    for c in columns.values():
        attributes.append({
            "repo_id": repo_id,
            "attribute_name": c["column_name"],
            "normalized_attribute": c["normalized_column"],
            "object_name": c["object_name"],
            "classifiers": c.get("classifiers") or [],
            "expressions": c.get("expressions") or [],
            "query_ids": c.get("query_ids") or [],
            "evidence": c.get("evidence") or [],
        })
    semantic_placeholders = _build_sql_semantic_placeholders(
        repo_id=repo_id,
        project_code=project_code,
        system_name=system_name,
        queries=queries,
        script_bindings=script_bindings,
    )
    counts = {
        "files_scanned": len(files),
        "sql_units": len(sql_units),
        "queries": len(queries),
        "select_scopes": len(select_scopes),
        "scoped_relations": len(scoped_relations),
        "scoped_projections": len(scoped_projections),
        "scoped_column_usages": len(scoped_column_usages),
        "resolved_column_usages": sum(1 for item in scoped_column_usages if item.get("resolution_status") in {"resolved", "projection_output"}),
        "scoped_write_targets": len(scoped_write_targets),
        "target_projection_bindings": len(scoped_target_projection_bindings),
        "confirmed_target_projection_bindings": sum(1 for item in scoped_target_projection_bindings if item.get("mapping_status") == "confirmed"),
        "scoped_join_edges": len(scoped_join_edges),
        "scoped_join_edges_confirmed": sum(1 for item in scoped_join_edges if item.get("resolution_status") == "confirmed"),
        "scoped_join_edges_partial": sum(1 for item in scoped_join_edges if item.get("resolution_status") == "partial"),
        "scoped_physical_joins_confirmed": sum(1 for item in scoped_join_edges if item.get("physical_join_confirmed")),
        "scoped_direct_column_lineage": len(scoped_direct_lineage),
        "scoped_direct_column_lineage_confirmed": sum(1 for item in scoped_direct_lineage if item.get("direct_lineage_status") == "confirmed_direct"),
        "scoped_direct_column_lineage_inferred_target": sum(1 for item in scoped_direct_lineage if item.get("direct_lineage_status") == "inferred_target"),
        "scoped_recursive_column_lineage": len(scoped_recursive_lineage),
        "scoped_recursive_column_lineage_confirmed": sum(1 for item in scoped_recursive_lineage if item.get("lineage_status") == "confirmed"),
        "scoped_recursive_column_lineage_inferred_target": sum(1 for item in scoped_recursive_lineage if item.get("lineage_status") == "inferred_target"),
        "scoped_recursive_column_lineage_partial": sum(1 for item in scoped_recursive_lineage if item.get("lineage_status") == "partial"),
        "scoped_recursive_physical_paths": sum(1 for item in scoped_recursive_lineage if item.get("physical_origin_status") in {"confirmed", "logical_template"}),
        "scoped_lineage_gaps": len(scoped_lineage_gaps),
        "recursive_lineage_gaps": len(recursive_lineage_gaps),
        "physical_relations": sum(1 for item in scoped_relations if item.get("relation_kind") in {"physical", "physical_template"}),
        "cte_relations": sum(1 for item in scoped_relations if item.get("relation_kind") == "cte"),
        "derived_relations": sum(1 for item in scoped_relations if item.get("relation_kind") == "derived"),
        "intermediate_relations_resolved": sum(1 for item in scoped_relations if item.get("relation_kind") in {"cte", "derived"} and item.get("definition_status") == "resolved"),
        "intermediate_relations_unresolved": sum(1 for item in scoped_relations if item.get("relation_kind") in {"cte", "derived"} and item.get("definition_status") != "resolved"),
        "intermediate_definition_branches": sum(len(item.get("source_scope_ids") or []) for item in scoped_relations if item.get("relation_kind") in {"cte", "derived"}),
        "script_statements": len(script_statements),
        "script_calls": len(script_calls),
        "script_bindings": len(script_bindings),
        "script_bindings_scalar": sum(1 for item in script_bindings if item.get("scalar_value") is not None),
        "script_statements_with_embedded_sql": sum(1 for item in script_statements if item.get("contains_embedded_sql")),
        "script_embedded_sql": len(embedded_sql),
        "script_invocations": len(script_invocations),
        "script_invocations_resolved": sum(1 for item in script_invocations if item.get("resolution_status") == "resolved"),
        "objects": len(objects),
        "columns": len(columns),
        "table_lineage_edges": len(table_lineage),
        "column_lineage_edges": len(column_lineage),
        "comments": len(comments),
        "config_hints": len(config_hints),
        "workflow_bindings": len(workflow_bindings),
        "workflow_bindings_literal": sum(1 for item in workflow_bindings if item.get("resolution_status") == "literal"),
        "workflow_bindings_template": sum(1 for item in workflow_bindings if item.get("resolution_status") == "template"),
        "optimization_hints": len(optimization_hints),
        "patterns": len(patterns),
    }
    artifacts = {
        "repository": {
            "repo_id": repo_id,
            "repo_path": str(repo),
            "system_name": system_name,
            "project_code": project_code,
            "analysis_profile": "external-profile-required",
        },
        "counts": counts,
        "sql_files": [{"repo_id": repo_id, "file": u["file"], "absolute_file": u["absolute_file"], "kind": u["kind"], "line_start": u.get("line_start")} for u in sql_units],
        "config_hints": config_hints,
        "workflow_bindings": workflow_bindings,
        "queries": queries,
        "select_scopes": select_scopes,
        "scoped_relations": scoped_relations,
        "scoped_projections": scoped_projections,
        "scoped_column_usages": scoped_column_usages,
        "scoped_write_targets": scoped_write_targets,
        "scoped_target_projection_bindings": scoped_target_projection_bindings,
        "scoped_join_edges": scoped_join_edges,
        "scoped_direct_lineage": scoped_direct_lineage,
        "scoped_recursive_lineage": scoped_recursive_lineage,
        "scoped_lineage_gaps": scoped_lineage_gaps,
        "script_statements": script_statements,
        "script_calls": script_calls,
        "script_bindings": script_bindings,
        "materialized_relation_contract_summary": materialized_relation_contract_summary,
        "script_embedded_sql": embedded_sql,
        "script_invocations": script_invocations,
        "objects": sorted(objects.values(), key=lambda x: x["object_name"]),
        "columns": sorted(columns.values(), key=lambda x: (x["object_name"], x["column_name"])),
        "attributes": sorted(attributes, key=lambda x: (x["normalized_attribute"], x["object_name"])),
        "table_lineage": table_lineage,
        "column_lineage": column_lineage,
        "comments": comments,
        "patterns": patterns,
        "optimization_hints": optimization_hints,
        "semantic_placeholders": semantic_placeholders,
    }
    return sanitize_public_payload(artifacts)



def _portable_sql_value(value: Any) -> Any:
    """Remove machine-local paths while preserving repository-relative evidence."""
    if isinstance(value, list):
        return [_portable_sql_value(item) for item in value]
    if not isinstance(value, dict):
        return value
    relative_file = value.get("relative_file")
    result: dict[str, Any] = {}
    for key, item in value.items():
        if key in {"absolute_file", "repo_path", "analysis_out", "static_analysis_output"}:
            continue
        if key == "file" and isinstance(item, str) and Path(item).is_absolute():
            if relative_file:
                result[key] = relative_file
            continue
        result[key] = _portable_sql_value(item)
    return result


SQL_COMPACT_OMIT_KEYS = {
    "project_code",
    "system_name",
    "evidence_maturity_dimensions",
    "evidence_maturity_blockers",
    "evidence_maturity_notes",
    "evidence_maturity_policy",
    "unresolved_gap_lifecycle",
    "source_inspection_required",
    "strict_evidence_contract",
    "strict_evidence_policy",
    "candidate_signals",
}


def _compact_sql_fact(value: Any) -> Any:
    """Project verbose diagnostic facts into the canonical ingestion contract."""
    portable = _portable_sql_value(value)
    if isinstance(portable, list):
        return [_compact_sql_fact(item) for item in portable]
    if not isinstance(portable, dict):
        return portable
    return {
        key: _compact_sql_fact(item)
        for key, item in portable.items()
        if key not in SQL_COMPACT_OMIT_KEYS
    }


def _canonical_sql_statements(queries: list[dict[str, Any]]) -> list[dict[str, Any]]:
    statements: list[dict[str, Any]] = []
    for query in queries:
        query_id = str(query.get("query_id") or "")
        statements.append(_compact_sql_fact({
            "sql_statement_id": query_id,
            "fact_type": "sql_statement",
            "repo_id": query.get("repo_id"),
            "query_id": query_id,
            "file": query.get("file"),
            "line_start": query.get("line_start"),
            "line_end": query.get("line_end"),
            "unit_kind": query.get("unit_kind"),
            "statement_type": query.get("statement_type"),
            "operation": query.get("operation"),
            "target_relation_name": query.get("target_object"),
            "statement_hash": query.get("statement_hash"),
            "select_scope_ids": query.get("select_scope_ids") or [],
            "write_target_ids": query.get("write_target_ids") or [],
            "semantic_placeholders": query.get("semantic_placeholders") or [],
            "scoped_source_coverage_status": query.get("scoped_source_coverage_status"),
            "scoped_source_candidate_count": query.get("scoped_source_candidate_count"),
            "scoped_source_count": query.get("scoped_source_count"),
            "scoped_ast_missing_source_candidates": query.get("scoped_ast_missing_source_candidates") or [],
            "evidence": query.get("evidence") or [],
            **maturity_props({
                "sql_statement": "confirmed",
                "persistence_write": "confirmed" if query.get("target_object") else "not_applicable",
                "physical_storage": "not_applicable",
                "field_mapping": "not_applicable",
                "source_boundary": "not_applicable",
                "end_to_end_trace": "not_applicable",
            }),
        }))
    return statements


def _canonical_sql_dependencies(artifacts: dict[str, Any]) -> list[dict[str, Any]]:
    dependencies: list[dict[str, Any]] = []
    for item in artifacts.get("table_lineage") or []:
        source = item.get("source_object")
        target = item.get("target_object")
        if not source or not target:
            continue
        identity = "|".join([
            str(item.get("repo_id") or artifacts.get("repository", {}).get("repo_id") or ""),
            str(item.get("query_id") or ""),
            str(source),
            str(target),
            str(item.get("operation") or ""),
        ])
        dependencies.append(_compact_sql_fact({
            "sql_object_dependency_id": f"sql_object_dependency_{_hash(identity, n=20)}",
            "fact_type": "sql_object_dependency",
            "repo_id": item.get("repo_id") or artifacts.get("repository", {}).get("repo_id"),
            "query_id": item.get("query_id"),
            "source_relation_name": source,
            "target_relation_name": target,
            "dependency_kind": "write_from_read",
            "operation": item.get("operation"),
            "file": item.get("file"),
            "line_start": item.get("line_start"),
            "evidence": item.get("evidence") or [],
            **maturity_props({
                "sql_statement": "confirmed",
                "persistence_write": "confirmed",
                "physical_storage": "not_applicable",
                "field_mapping": "not_applicable",
                "source_boundary": "not_applicable",
                "end_to_end_trace": "confirmed",
            }),
        }))
    unique = {str(item["sql_object_dependency_id"]): item for item in dependencies}
    return list(unique.values())


def _canonical_sql_fact_sets(artifacts: dict[str, Any]) -> dict[str, list[dict[str, Any]]]:
    fact_sets = {
        "sql_statement": _canonical_sql_statements(artifacts.get("queries") or []),
        "sql_script_statement": artifacts.get("script_statements") or [],
        "sql_script_call": artifacts.get("script_calls") or [],
        "sql_script_binding": artifacts.get("script_bindings") or [],
        "sql_script_embedded_sql": artifacts.get("script_embedded_sql") or [],
        "sql_script_invocation": artifacts.get("script_invocations") or [],
        "sql_semantic_placeholder": artifacts.get("semantic_placeholders") or [],
        "sql_workflow_binding": artifacts.get("workflow_bindings") or [],
        "sql_select_scope": artifacts.get("select_scopes") or [],
        "sql_relation": artifacts.get("scoped_relations") or [],
        "sql_column_usage": artifacts.get("scoped_column_usages") or [],
        "sql_projection": artifacts.get("scoped_projections") or [],
        "sql_write_target": artifacts.get("scoped_write_targets") or [],
        "sql_target_projection_binding": artifacts.get("scoped_target_projection_bindings") or [],
        "sql_join_edge": artifacts.get("scoped_join_edges") or [],
        "sql_direct_column_lineage": artifacts.get("scoped_direct_lineage") or [],
        "sql_recursive_column_lineage": artifacts.get("scoped_recursive_lineage") or [],
        "sql_object_dependency": _canonical_sql_dependencies(artifacts),
        "sql_scoped_lineage_gap": artifacts.get("scoped_lineage_gaps") or [],
    }
    return {
        fact_type: [_compact_sql_fact(item) for item in fact_sets.get(fact_type, [])]
        for fact_type, _ in SQL_CANONICAL_FACTS
    }


def _write_canonical_jsonl(path: Path, records: list[dict[str, Any]], id_field: str) -> dict[str, Any]:
    path.parent.mkdir(parents=True, exist_ok=True)
    ordered = sorted(
        records,
        key=lambda item: (
            str(item.get(id_field) or ""),
            str(item.get("file") or ""),
            int(item.get("line_start") or 0),
        ),
    )
    digest = hashlib.sha256()
    with path.open("wb") as handle:
        for item in ordered:
            payload = json.dumps(item, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8") + b"\n"
            handle.write(payload)
            digest.update(payload)
    return {
        "record_count": len(ordered),
        "sha256": digest.hexdigest(),
        "byte_size": path.stat().st_size,
    }


def _status_counts(records: list[dict[str, Any]], field: str) -> dict[str, int]:
    return dict(sorted(Counter(str(item.get(field) or "unknown") for item in records).items()))


def _column_usage_inventory_coverage(usages: list[dict[str, Any]]) -> dict[str, Any]:
    """Report source-field coverage without treating generated/parameter values as failures."""
    semantic_parameters = [
        item for item in usages
        if item.get("resolution_status") == "semantic_parameter"
        or item.get("resolution_basis") == "semantic_parameter"
    ]
    generated_values = [
        item for item in usages
        if item.get("relation_kind") == "generated"
        or str(item.get("resolution_basis") or "").startswith("generated_alias")
    ]
    non_source_ids = {
        str(item.get("sql_column_usage_id") or id(item))
        for item in semantic_parameters + generated_values
    }
    source_candidates = [
        item for item in usages
        if str(item.get("sql_column_usage_id") or id(item)) not in non_source_ids
    ]
    resolved = [
        item for item in source_candidates
        if item.get("resolution_status") == "resolved" and item.get("relation_id")
    ]
    unresolved = [item for item in source_candidates if item not in resolved]
    candidate_count = len(source_candidates)
    resolved_count = len(resolved)
    return {
        "status": "complete" if not unresolved else "partial",
        "total_observed_usages": len(usages),
        "source_field_candidate_usages": candidate_count,
        "resolved_source_field_usages": resolved_count,
        "unresolved_source_field_usages": len(unresolved),
        "source_field_resolution_rate": round(resolved_count / candidate_count, 6) if candidate_count else 1.0,
        "resolved_by_relation_kind": dict(sorted(Counter(
            str(item.get("relation_kind") or "unknown") for item in resolved
        ).items())),
        "unresolved_by_status": _status_counts(unresolved, "resolution_status"),
        "unresolved_by_basis": _status_counts(unresolved, "resolution_basis"),
        "non_source_values": {
            "semantic_parameter_usages": len(semantic_parameters),
            "generated_value_usages": len(generated_values),
        },
        "policy": (
            "semantic parameters and generated LATERAL/EXPLODE values are reported separately "
            "and do not reduce source-field resolution"
        ),
    }


def _build_sql_analysis_coverage(artifacts: dict[str, Any], fact_sets: dict[str, list[dict[str, Any]]]) -> dict[str, Any]:
    relations = fact_sets["sql_relation"]
    usages = fact_sets["sql_column_usage"]
    projections = fact_sets["sql_projection"]
    joins = fact_sets["sql_join_edge"]
    write_targets = fact_sets["sql_write_target"]
    target_bindings = fact_sets["sql_target_projection_binding"]
    direct = fact_sets["sql_direct_column_lineage"]
    recursive = fact_sets["sql_recursive_column_lineage"]
    gaps = fact_sets["sql_scoped_lineage_gap"]
    placeholders = fact_sets["sql_semantic_placeholder"]
    invocations = fact_sets["sql_script_invocation"]
    partial = bool(
        gaps
        or any(item.get("definition_status") == "unresolved" for item in relations)
        or any(item.get("resolution_status") in {"partial", "ambiguous", "unresolved"} for item in usages)
        or any(item.get("resolution_status") in {"partial", "unresolved"} for item in projections)
        or any(item.get("resolution_status") in {"partial", "unresolved"} for item in write_targets)
        or any(item.get("mapping_status") == "unresolved" for item in target_bindings)
        or any(item.get("resolution_status") in {"partial", "unresolved"} for item in joins)
        or any(item.get("direct_lineage_status") == "partial" for item in direct)
        or any(item.get("lineage_status") == "partial" for item in recursive)
        or any(item.get("resolution_status") == "unbound_semantic" for item in placeholders)
        or any(item.get("resolution_status") == "unresolved" for item in invocations)
    )
    return {
        "artifact": "sql_analysis_coverage",
        "schema_version": SQL_ANALYSIS_SCHEMA_VERSION,
        "analysis_status": "partial" if partial else "complete",
        "source_inventory": {
            "files_scanned": artifacts.get("counts", {}).get("files_scanned", 0),
            "sql_units": artifacts.get("counts", {}).get("sql_units", 0),
            "sql_statements": len(fact_sets["sql_statement"]),
            "script_statements": len(fact_sets["sql_script_statement"]),
        },
        "fact_counts": {fact_type: len(records) for fact_type, records in fact_sets.items()},
        "relations": {
            "by_kind": dict(sorted(Counter(str(item.get("relation_kind") or "unknown") for item in relations).items())),
            "by_definition_status": _status_counts(relations, "definition_status"),
        },
        "column_usages": {
            "by_resolution_status": _status_counts(usages, "resolution_status"),
            "source_inventory": _column_usage_inventory_coverage(usages),
        },
        "projections": {"by_resolution_status": _status_counts(projections, "resolution_status")},
        "write_targets": {"by_resolution_status": _status_counts(write_targets, "resolution_status")},
        "target_projection_bindings": {"by_mapping_status": _status_counts(target_bindings, "mapping_status")},
        "script_invocations": {"by_resolution_status": _status_counts(invocations, "resolution_status")},
        "joins": {
            "by_type": dict(sorted(Counter(str(item.get("join_type") or "unknown") for item in joins).items())),
            "by_resolution_status": _status_counts(joins, "resolution_status"),
            "physical_join_confirmed": sum(1 for item in joins if item.get("physical_join_confirmed")),
        },
        "direct_lineage": {"by_status": _status_counts(direct, "direct_lineage_status")},
        "recursive_lineage": {
            "by_status": _status_counts(recursive, "lineage_status"),
            "by_terminal_source_kind": _status_counts(recursive, "terminal_source_kind"),
        },
        "semantic_placeholders": {"by_resolution_status": _status_counts(placeholders, "resolution_status")},
        "gaps": {
            "total": len(gaps),
            "by_kind": dict(sorted(Counter(str(item.get("gap_kind") or "unknown") for item in gaps).items())),
        },
        "coverage_policy": "partial_facts_are_published_with_localized_resolution_status_and_gaps",
    }


def _write_sql_analysis_artifact(out: Path, artifacts: dict[str, Any], started_at: str) -> dict[str, Any]:
    root = out / "sql-analysis"
    fact_sets = _canonical_sql_fact_sets(artifacts)
    shard_entries: list[dict[str, Any]] = []
    for fact_type, id_field in SQL_CANONICAL_FACTS:
        relative_path = Path("facts") / f"{fact_type}.jsonl"
        metrics = _write_canonical_jsonl(root / relative_path, fact_sets[fact_type], id_field)
        shard_entries.append({
            "fact_type": fact_type,
            "id_field": id_field,
            "path": relative_path.as_posix(),
            **metrics,
        })

    coverage = _build_sql_analysis_coverage(artifacts, fact_sets)
    coverage_path = root / "coverage.json"
    coverage_bytes = (json.dumps(coverage, ensure_ascii=False, sort_keys=True, indent=2) + "\n").encode("utf-8")
    coverage_path.write_bytes(coverage_bytes)
    coverage_sha256 = hashlib.sha256(coverage_bytes).hexdigest()
    content_fingerprint = sql_analysis_content_fingerprint(shard_entries, coverage_sha256)
    repository = artifacts.get("repository") or {}
    manifest = {
        "artifact": "sql_analysis",
        "contract_version": SQL_ANALYSIS_CONTRACT_VERSION,
        "schema_version": SQL_ANALYSIS_SCHEMA_VERSION,
        "created_at": started_at,
        "analysis_status": coverage["analysis_status"],
        "repository": {
            "repo_id": repository.get("repo_id"),
            "system_name": repository.get("system_name"),
            "project_code": repository.get("project_code"),
            "analysis_profile": repository.get("analysis_profile"),
        },
        "producer": {
            "name": "code-analyzer-core",
            "version": CORE_VERSION,
            "sql_profile_version": SQL_PROFILE_VERSION,
        },
        "facts": shard_entries,
        "coverage": {
            "path": "coverage.json",
            "sha256": coverage_sha256,
            "byte_size": len(coverage_bytes),
        },
        "content_fingerprint": content_fingerprint,
        "evidence_path_policy": "repository_relative_only",
        "serialization": {
            "format": "jsonl",
            "encoding": "utf-8",
            "canonical_json": "sorted_keys_compact_one_record_per_line",
            "record_order": "deterministic_by_fact_id",
        },
        "compaction_policy": {
            "kept": ["typed identities", "resolution statuses", "expressions", "repository-relative evidence"],
            "omitted": ["repeated generic maturity dimensions", "global policy strings", "machine-local paths"],
        },
        "excluded_noncanonical_outputs": [
            "aggregate SQL summaries",
            "navigation samples",
            "full diagnostic query payloads",
        ],
    }
    write_json(root / "manifest.json", manifest)
    return manifest
