from __future__ import annotations

import re
from typing import Any

from code_analyzer_core.scanners.java_flow_builder import _clean_expression

def _jooq_field_constant_to_column(raw: str | None) -> str | None:
    value = _clean_expression(raw)
    if not value:
        return None
    value = value.strip('"\'')
    token = value.split(".")[-1].strip()
    token = re.sub(r"[^A-Za-z0-9_]", "_", token).strip("_")
    return token or None


def _jooq_table_constant(raw: str | None) -> str | None:
    value = _clean_expression(raw)
    if not value:
        return None
    token = value.split(".")[-1].strip()
    token = re.sub(r"[^A-Za-z0-9_]", "_", token).strip("_")
    return token or None


def _jooq_bind_placeholder(value: str | None) -> bool:
    text = _clean_expression(value).lower()
    if not text:
        return False
    return bool(
        re.search(r"(?:^|[\s(])null(?:[\s)]|$)", text)
        or "?" in text
        or re.search(r"(?:^|[\s.(])(?:dsl\.)?param\s*\(", text)
    )


def _jooq_set_slots_from_chain(chain: str, *, bindable_only: bool = False) -> list[dict[str, Any]]:
    slots: list[dict[str, Any]] = []
    text = chain or ""
    pat = re.compile(r"\.\s*set\s*\(\s*(?P<field>[A-Za-z_][A-Za-z0-9_.$]*)\s*,", re.DOTALL)
    matches = list(pat.finditer(text))
    for idx, sm in enumerate(matches):
        next_starts = [m.start() for m in matches[idx + 1:idx + 2]]
        for token in [".where", ".and", ".onConflict", ".returning", ".execute", ".fetch"]:
            pos = text.find(token, sm.end())
            if pos >= 0:
                next_starts.append(pos)
        stop = min(next_starts) if next_starts else min(len(text), sm.end() + 240)
        value = _clean_expression(text[sm.end():stop]).rstrip(") ;")
        if bindable_only and not _jooq_bind_placeholder(value):
            continue
        col = _jooq_field_constant_to_column(sm.group("field"))
        if col:
            slots.append({
                "field": col,
                "field_ref": sm.group("field"),
                "role": "write_target_field",
                "value_expression": value,
                "bind_placeholder": _jooq_bind_placeholder(value),
            })
    return slots


def _jooq_where_slots_from_chain(chain: str, *, bindable_only: bool = False) -> list[dict[str, Any]]:
    slots: list[dict[str, Any]] = []
    text = chain or ""
    pat = re.compile(r"(?:\.\s*where|\.\s*and)\s*\(\s*(?P<field>[A-Za-z_][A-Za-z0-9_.$]*)\s*\.\s*[A-Za-z_][A-Za-z0-9_]*\s*\(", re.DOTALL)
    matches = list(pat.finditer(text))
    for idx, wm in enumerate(matches):
        next_starts = [m.start() for m in matches[idx + 1:idx + 2]]
        for token in [".and", ".or", ".execute", ".fetch", ".returning"]:
            pos = text.find(token, wm.end())
            if pos >= 0:
                next_starts.append(pos)
        stop = min(next_starts) if next_starts else min(len(text), wm.end() + 240)
        value = _clean_expression(text[wm.end():stop]).rstrip(") ;")
        if bindable_only and not _jooq_bind_placeholder(value):
            continue
        col = _jooq_field_constant_to_column(wm.group("field"))
        if col:
            slots.append({
                "field": col,
                "field_ref": wm.group("field"),
                "role": "where_key_field",
                "value_expression": value,
                "bind_placeholder": _jooq_bind_placeholder(value),
            })
    return slots


def _jooq_update_statement_slots(body: str, *, bindable_only: bool = False) -> dict[str, dict[str, Any]]:
    """Return statement variable -> jOOQ update/insert batch slot evidence.

    This helper is invoked from deep persistence lineage on every Java method.
    Keep a very cheap token prefilter before the DOTALL regexes: without jOOQ
    update/insert markers there cannot be any statement slots to extract.

    This is a deterministic pattern extractor for common jOOQ prepared batch code:
      var step = dsl.update(TABLE).set(TABLE.COL, null).where(TABLE.ID.eq(null));
      var step = dsl.insertInto(TABLE).set(TABLE.COL, (String) null);
      BatchBindStep batch = dsl.batch(step);
      batch.bind(src.getCol(), src.getId());

    With bindable_only=True it exposes only slots backed by null/? placeholders;
    generated/default values such as sequences/current timestamp are not mapped to
    bind arguments.
    """
    out: dict[str, dict[str, Any]] = {}
    text = body or ""
    if ".update" not in text and "update(" not in text and ".insertInto" not in text and "insertInto(" not in text:
        return out
    patterns = [
        ("update", re.compile(
            r"(?:(?:final\s+)?[A-Za-z_][A-Za-z0-9_<>?,.\s]*\s+)?(?P<var>[A-Za-z_][A-Za-z0-9_]*)\s*=\s*[^;]*?\.\s*update\s*\(\s*(?P<table>[A-Za-z_][A-Za-z0-9_.$]*)\s*\)(?P<chain>.*?);",
            re.DOTALL,
        )),
        ("insert", re.compile(
            r"(?:(?:final\s+)?[A-Za-z_][A-Za-z0-9_<>?,.\s]*\s+)?(?P<var>[A-Za-z_][A-Za-z0-9_]*)\s*=\s*[^;]*?\.\s*insertInto\s*\(\s*(?P<table>[A-Za-z_][A-Za-z0-9_.$]*)\s*\)(?P<chain>.*?);",
            re.DOTALL,
        )),
    ]
    for statement_kind, stmt_pat in patterns:
        for m in stmt_pat.finditer(text):
            chain = m.group("chain") or ""
            slots = _jooq_set_slots_from_chain(chain, bindable_only=bindable_only)
            if statement_kind == "update":
                slots.extend(_jooq_where_slots_from_chain(chain, bindable_only=bindable_only))
            out[m.group("var")] = {
                "statement_variable": m.group("var"),
                "statement_kind": statement_kind,
                "table": _jooq_table_constant(m.group("table")),
                "table_ref": m.group("table"),
                "slots": slots,
                "statement_expression": _clean_expression(m.group(0)),
            }
    return out


def _jooq_inline_statement_from_expression(expr: str | None, *, bindable_only: bool = False) -> dict[str, Any] | None:
    text = _clean_expression(expr)
    if not text:
        return None
    m = re.search(r"\.\s*(?P<kind>insertInto|update)\s*\(\s*(?P<table>[A-Za-z_][A-Za-z0-9_.$]*)\s*\)(?P<chain>.*)$", text, re.DOTALL)
    if not m:
        return None
    kind = "insert" if m.group("kind") == "insertInto" else "update"
    chain = m.group("chain") or ""
    slots = _jooq_set_slots_from_chain(chain, bindable_only=bindable_only)
    if kind == "update":
        slots.extend(_jooq_where_slots_from_chain(chain, bindable_only=bindable_only))
    return {
        "statement_variable": None,
        "statement_kind": kind,
        "table": _jooq_table_constant(m.group("table")),
        "table_ref": m.group("table"),
        "slots": slots,
        "statement_expression": text,
    }


def _jooq_batch_variable_links(body: str) -> tuple[dict[str, str], dict[str, dict[str, Any]]]:
    links: dict[str, str] = {}
    inline: dict[str, dict[str, Any]] = {}
    text = body or ""
    if ".batch" not in text and "batch(" not in text:
        return links, inline
    pat = re.compile(r"(?:(?:final\s+)?[A-Za-z_][A-Za-z0-9_<>?,.\s]*\s+)?(?P<batch>[A-Za-z_][A-Za-z0-9_]*)\s*=\s*[^;]*?\.\s*batch\s*\(\s*(?P<stmt>[A-Za-z_][A-Za-z0-9_]*)\s*\)\s*;", re.DOTALL)
    for m in pat.finditer(text):
        links[m.group("batch")] = m.group("stmt")

    inline_pat = re.compile(r"(?:(?:final\s+)?[A-Za-z_][A-Za-z0-9_<>?,.\s]*\s+)?(?P<batch>[A-Za-z_][A-Za-z0-9_]*)\s*=\s*[^;]*?\.\s*batch\s*\(\s*(?P<stmt>.*?)\s*\)\s*;", re.DOTALL)
    for m in inline_pat.finditer(text):
        stmt_expr = m.group("stmt") or ""
        if re.match(r"^[A-Za-z_][A-Za-z0-9_]*$", stmt_expr.strip()):
            continue
        stmt = _jooq_inline_statement_from_expression(stmt_expr, bindable_only=True)
        if stmt:
            inline[m.group("batch")] = stmt
    return links, inline


