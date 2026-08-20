#!/usr/bin/env python3
"""Export S2T CSV from prepared ``sql-target-source-mapping`` knowledge.

The exporter is a thin consumer of prepared KLC knowledge. It never reruns
Core/Runner and never invents lineage. Two projections are supported:

* default technical branch-aware CSV for diagnostics/provenance;
* ``--standard-s2t``: the human 26-column S2T layout used by downstream users.
  One row represents one target field in one observed query/set branch. Multiple
  sources inside the same branch stay in that row. UNION itself is structural
  context and is not written as a field transformation.
"""
from __future__ import annotations

import argparse
import csv
import json
from collections import defaultdict
from pathlib import Path
from typing import Any, Iterable

import duckdb

BRANCH_AWARE_FIELDS = [
    "target_table",
    "target_column",
    "source_branch",
    "branch_relation",
    "driver_relation",
    "driver_relation_status",
    "driver_relation_basis",
    "driver_relation_candidates",
    "source_relation_role",
    "source_relation_role_basis",
    "source_relation",
    "source_column",
    "transformation",
    "mapping_status",
    "knowledge_class",
    "mapping_basis",
    "producer_hop_count",
    "workflow_context",
    "source_sql_file",
]

LEGACY_FIELDS = [
    "target_table",
    "target_column",
    "source_relation",
    "source_column",
    "transformation",
    "mapping_status",
    "knowledge_class",
    "mapping_basis",
    "producer_hop_count",
    "workflow_context",
    "source_sql_file",
]

STANDARD_S2T_FIELDS = [
    "T-trg-platform",
    "T-trg-instance",
    "T-trg-schema",
    "T-trg",
    "UserName",
    "T-trg-f",
    "target_data_relevance",
    "target_data_hist",
    "target_data_freq",
    "T-src-platform",
    "T-src-instance",
    "T-src-schema",
    "T-src",
    "T-src-main",
    "T-src-f-name",
    "T-src-f",
    "T-src-join",
    "T-src-join-on",
    "T-src-where",
    "T-src-group",
    "T-k",
    "T-hist-type",
    "T-hist-role",
    "codeDatamart",
    "Datamart.description_source",
    "Table.description_source",
]

STANDARD_S2T_DESCRIPTIONS = [
    "Наименование платформы где лежит целевая таблица",
    "Наименование инстанса, где лежит таблица-приемник",
    "Наименование схемы приемника",
    "Наименование таблицы приемника",
    "Ответственный за конкретную таблицу (почта в домене Альфа)",
    "Наименование поля приемника\n*рекомендовано к заполнению, обязательно для заполнения в случае связи 1:1",
    "Актуальность данных(T-N, актуальность данных в таблице) ",
    "Историчность(дата начала расчета данных в таблице) ",
    "Частота расчёта таблицы ",
    "Наименование платформы где лежит таблица-источник",
    "Наименование инстанса, где лежит таблица-источник",
    "Наименование схемы источника",
    "Наименование таблицы источника",
    "Наименование главной таблицы",
    "Наименование поля источника\n*рекомендовано к заполнению, обязательно для заполнения в случае связи 1:1",
    "Трансформация поля источника",
    "Дополнительная таблица-источник",
    "Условия соединения с дополнительной таблицей",
    "Условия фильтрации исходного набора",
    "Группировка",
    "K-таблица",
    "СОД",
    "Роль в истории",
    "ID Витрины",
    "Источник расчёта(Бизнес-описание источников расчета на уровне витрин) ",
    "Источник расчёта(Бизнес-описание источников расчета на уровне таблиц) ",
]

OPTIONAL_MAPPING_COLUMNS = {
    "branch_relation_name": "branch_relation_name",
    "driver_relation_status": "driver_relation_status",
    "driver_relation_basis": "driver_relation_basis",
    "driver_relation_candidates_json": "driver_relation_candidates_json",
}


def _mapping_query(available: set[str]) -> str:
    def col(name: str, alias: str | None = None) -> str:
        target = alias or name
        return name if name in available and target == name else (f"{name} AS {target}" if name in available else f"NULL AS {target}")

    fields = [
        col("workflow_target_logical_name"),
        col("target_column"),
        col("source_branch"),
        col("source_branch_scope_id"),
        col("source_branch_ordinal"),
        col("branch_relation_name"),
        col("driver_relation_name"),
        col("driver_relation_status"),
        col("driver_relation_basis"),
        col("driver_relation_candidates_json"),
        col("source_relation_role"),
        col("source_relation_role_basis"),
        col("source_sql_relation_name"),
        col("source_sql_column"),
        col("root_expression"),
        col("local_transformation_path_json"),
        col("mapping_status"),
        col("knowledge_class"),
        col("mapping_basis"),
        col("producer_hop_count"),
        col("workflow_context_file"),
        col("source_sql_file"),
    ]
    return "SELECT\n    " + ",\n    ".join(fields) + "\nFROM sql_target_source_mapping\nORDER BY workflow_target_logical_name, target_column, source_branch_ordinal NULLS LAST, source_branch NULLS LAST, source_sql_relation_name NULLS LAST, source_sql_column NULLS LAST"



def _text(value: Any) -> str:
    return "" if value is None else str(value)


def _driver_candidates(value: Any) -> str:
    if value is None or value == "":
        return ""
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
        except Exception:
            return value
    else:
        parsed = value
    if not isinstance(parsed, list):
        return _text(parsed)
    return ";".join(sorted({_text(item) for item in parsed if item not in (None, "")}))


def _branch_aware_rows(database: Path) -> Iterable[dict[str, Any]]:
    connection = duckdb.connect(str(database), read_only=True)
    try:
        available = {row[1] for row in connection.execute("PRAGMA table_info('sql_target_source_mapping')").fetchall()}
        cursor = connection.execute(_mapping_query(available))
        columns = [description[0] for description in cursor.description]
        for values in cursor.fetchall():
            row = dict(zip(columns, values))
            yield {
                "target_table": row["workflow_target_logical_name"],
                "target_column": row["target_column"],
                "source_branch": row["source_branch"],
                "branch_relation": row["branch_relation_name"],
                "driver_relation": row["driver_relation_name"],
                "driver_relation_status": row["driver_relation_status"],
                "driver_relation_basis": row["driver_relation_basis"],
                "driver_relation_candidates": _driver_candidates(row["driver_relation_candidates_json"]),
                "source_relation_role": row["source_relation_role"],
                "source_relation_role_basis": row["source_relation_role_basis"],
                "source_relation": row["source_sql_relation_name"],
                "source_column": row["source_sql_column"],
                "transformation": row["root_expression"],
                "_local_transformation_path_json": row["local_transformation_path_json"],
                "mapping_status": row["mapping_status"],
                "knowledge_class": row["knowledge_class"],
                "mapping_basis": row["mapping_basis"],
                "producer_hop_count": row["producer_hop_count"],
                "workflow_context": row["workflow_context_file"],
                "source_sql_file": row["source_sql_file"],
            }
    finally:
        connection.close()


def _deduplicate(rows: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    seen: set[tuple[str, ...]] = set()
    for row in rows:
        marker = tuple(_text(row.get(field)) for field in BRANCH_AWARE_FIELDS) + (_text(row.get("_local_transformation_path_json")),)
        if marker in seen:
            continue
        seen.add(marker)
        result.append(row)
    return result


def _unique(values: Iterable[Any]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        text = _text(value).strip()
        if text and text not in seen:
            seen.add(text)
            result.append(text)
    return result


def _split_relation(relation: Any) -> tuple[str, str]:
    value = _text(relation).strip()
    if not value:
        return "", ""
    if "." not in value:
        return "", value
    schema, table = value.rsplit(".", 1)
    return schema, table


def _is_simple_passthrough_expression(expression: str) -> bool:
    import re

    value = expression.strip()
    if not value or value == "*" or value.endswith(".*"):
        return True
    # A plain column reference, optionally renamed with AS, is source selection,
    # not a business transformation in the conventional S2T field.
    return bool(re.fullmatch(r"[A-Za-z_$][\w$]*(?:\.[A-Za-z_$][\w$]*)?(?:\s+AS\s+[A-Za-z_$][\w$]*)?", value, flags=re.I))


def _meaningful_transformations(row: dict[str, Any]) -> list[str]:
    result: list[str] = []
    raw = row.get("_local_transformation_path_json")
    if raw:
        try:
            path = json.loads(raw) if isinstance(raw, str) else raw
        except Exception:
            path = []
        if isinstance(path, list):
            for item in path:
                if not isinstance(item, dict):
                    continue
                expression = _text(item.get("expression")).strip()
                kind = _text(item.get("expression_kind")).strip()
                if not expression or kind == "direct_column" or _is_simple_passthrough_expression(expression):
                    continue
                if expression not in result:
                    result.append(expression)
    root = _text(row.get("transformation")).strip()
    if root and not _is_simple_passthrough_expression(root) and root not in result:
        result.append(root)
    return result


def _standard_s2t_rows(
    rows: Iterable[dict[str, Any]],
    *,
    target_platform: str,
    source_platform: str,
    target_instance: str,
    source_instance: str,
    target_schema: str,
    datamart_id: str,
) -> list[dict[str, str]]:
    """Project technical lineage into the conventional human S2T table.

    Branch is part of row identity, not a transformation. This intentionally
    produces several rows for one target field when the observed SQL contains
    several source/query branches (for example UNION/UNION ALL branches).
    """
    groups: dict[tuple[str, str, str], list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        groups[(
            _text(row.get("target_table")),
            _text(row.get("target_column")),
            _text(row.get("source_branch")),
        )].append(row)

    result: list[dict[str, str]] = []
    for (target_table, target_column, _source_branch), items in sorted(groups.items()):
        source_schemas: list[str] = []
        source_tables: list[str] = []
        source_fields: list[str] = []
        main_tables: list[str] = []
        join_tables: list[str] = []
        transformations: list[str] = []

        for item in items:
            schema, table = _split_relation(item.get("source_relation"))
            if schema and schema not in source_schemas:
                source_schemas.append(schema)
            if table and table not in source_tables:
                source_tables.append(table)

            column = _text(item.get("source_column")).strip()
            if table and column:
                qualified_field = f"{table}.{column}"
                if qualified_field not in source_fields:
                    source_fields.append(qualified_field)

            for transformation in _meaningful_transformations(item):
                if transformation not in transformations:
                    transformations.append(transformation)

        output = {field: "" for field in STANDARD_S2T_FIELDS}
        output.update({
            "T-trg-platform": target_platform,
            "T-trg-instance": target_instance,
            "T-trg-schema": target_schema,
            "T-trg": target_table,
            "T-trg-f": target_column,
            "T-src-platform": source_platform,
            "T-src-instance": source_instance,
            "T-src-schema": "; ".join(source_schemas),
            "T-src": "; ".join(source_tables),
            "T-src-main": "",
            "T-src-f-name": "; ".join(source_fields),
            "T-src-f": " ; ".join(transformations),
            "T-src-join": "",
            "codeDatamart": datamart_id,
        })
        result.append(output)
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description="Export S2T CSV from prepared sql-target-source-mapping knowledge")
    parser.add_argument("--database", required=True, type=Path, help="knowledge-layer.duckdb for sql-target-source-mapping")
    parser.add_argument("--output", required=True, type=Path, help="output CSV")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument(
        "--legacy-columns",
        action="store_true",
        help="emit the previous 11-column technical projection; branch/driver metadata is omitted",
    )
    mode.add_argument(
        "--standard-s2t",
        action="store_true",
        help="emit the conventional 26-column human S2T layout; one row per target field per observed branch",
    )
    parser.add_argument("--target-platform", default="", help="standard S2T metadata; left blank unless explicitly known")
    parser.add_argument("--source-platform", default="", help="standard S2T metadata; left blank unless explicitly known")
    parser.add_argument("--target-instance", default="", help="standard S2T metadata; left blank unless explicitly known")
    parser.add_argument("--source-instance", default="", help="standard S2T metadata; left blank unless explicitly known")
    parser.add_argument("--target-schema", default="", help="standard S2T metadata; left blank unless explicitly known")
    parser.add_argument("--datamart-id", default="", help="standard S2T metadata; left blank unless explicitly known")
    args = parser.parse_args()

    if not args.database.is_file():
        raise SystemExit(f"database not found: {args.database}")

    rows = _deduplicate(_branch_aware_rows(args.database))
    args.output.parent.mkdir(parents=True, exist_ok=True)

    if args.standard_s2t:
        standard_rows = _standard_s2t_rows(
            rows,
            target_platform=args.target_platform,
            source_platform=args.source_platform,
            target_instance=args.target_instance,
            source_instance=args.source_instance,
            target_schema=args.target_schema,
            datamart_id=args.datamart_id,
        )
        with args.output.open("w", encoding="utf-8-sig", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=STANDARD_S2T_FIELDS, extrasaction="ignore")
            writer.writeheader()
            writer.writerow(dict(zip(STANDARD_S2T_FIELDS, STANDARD_S2T_DESCRIPTIONS)))
            writer.writerows(standard_rows)
        targets = len({row["T-trg"] for row in standard_rows})
        target_fields = len({(row["T-trg"], row["T-trg-f"]) for row in standard_rows})
        payload = {
            "database": str(args.database),
            "output": str(args.output),
            "row_count": len(standard_rows),
            "target_table_count": targets,
            "target_field_count": target_fields,
            "mode": "standard-s2t",
        }
    else:
        fields = LEGACY_FIELDS if args.legacy_columns else BRANCH_AWARE_FIELDS
        with args.output.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
            writer.writeheader()
            for row in rows:
                writer.writerow({field: _text(row.get(field)) for field in fields})
        targets = len({row["target_table"] for row in rows})
        target_fields = len({(row["target_table"], row["target_column"]) for row in rows})
        payload = {
            "database": str(args.database),
            "output": str(args.output),
            "row_count": len(rows),
            "target_table_count": targets,
            "target_field_count": target_fields,
            "mode": "legacy" if args.legacy_columns else "branch-aware",
        }

    print(json.dumps(payload, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
