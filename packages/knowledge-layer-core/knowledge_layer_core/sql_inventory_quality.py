from __future__ import annotations

import argparse
import hashlib
import json
import re
from collections import defaultdict
from pathlib import Path
from typing import Any, Iterable

from prepared_knowledge_runtime.database import connect_database

SCHEMA_VERSION = "sql-source-inventory-quality-report/v1"
FIXTURE_SCHEMA_VERSION = "sql-source-inventory-quality/v1"
DEFAULT_TARGET_GATES = {
    "relation_precision": 0.99,
    "relation_recall": 0.98,
    "classification_accuracy": 0.98,
    "field_precision": 0.98,
    "field_recall": 0.98,
    "field_role_accuracy": 0.98,
}


def normalize_identifier(value: Any) -> str:
    text = str(value or "").strip().replace("`", "").replace('"', "")
    return re.sub(r"\s+", "", text).lower()


def _safe_ratio(numerator: int, denominator: int) -> float:
    return 1.0 if denominator == 0 else numerator / denominator


def load_quality_fixture(path: str | Path) -> dict[str, Any]:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if payload.get("schema_version") != FIXTURE_SCHEMA_VERSION:
        raise ValueError(
            f"unsupported fixture schema: {payload.get('schema_version')!r}; "
            f"expected {FIXTURE_SCHEMA_VERSION!r}"
        )
    cases = payload.get("cases")
    if not isinstance(cases, list) or not cases:
        raise ValueError("quality fixture must contain a non-empty cases list")
    return payload


def collect_actual_inventory(
    artifact: str | Path,
    *,
    repo_id: str,
    files: Iterable[str],
) -> dict[str, dict[str, Any]]:
    selected_files = sorted({str(item) for item in files})
    if not selected_files:
        return {}
    placeholders = ",".join("?" for _ in selected_files)
    actual: dict[str, dict[str, Any]] = {
        file: {"relations": {}, "unresolved_column_usages": 0, "column_usages": 0}
        for file in selected_files
    }
    with connect_database(Path(artifact), read_only=True) as connection:
        relation_rows = connection.execute(
            f"""
            SELECT r.file,
                   r.relation_kind,
                   coalesce(nullif(r.template_name,''), r.relation_name) AS relation_identity,
                   sr.hidden_by_default,
                   sr.semantic_role,
                   sr.classification_status,
                   u.column_name,
                   u.usage_role
              FROM sql_relation r
              LEFT JOIN sql_relation_semantic_role sr
                ON sr.repo_id=r.repo_id
               AND sr.relation_kind=r.relation_kind
               AND sr.relation_identity=coalesce(nullif(r.template_name,''), r.relation_name)
              LEFT JOIN sql_column_usage u
                ON u.repo_id=r.repo_id AND u.relation_id=r.sql_relation_id
             WHERE r.repo_id=?
               AND r.file IN ({placeholders})
               AND r.relation_kind IN ('physical','physical_template','temporary')
             ORDER BY r.file, relation_identity, r.relation_kind, u.column_name, u.usage_role
            """,
            [repo_id, *selected_files],
        ).fetchall()
        for (
            file,
            relation_kind,
            relation_identity,
            hidden_by_default,
            semantic_role,
            classification_status,
            column_name,
            usage_role,
        ) in relation_rows:
            file_key = str(file)
            identity = normalize_identifier(relation_identity)
            relation_key = (str(relation_kind), identity)
            relation = actual[file_key]["relations"].setdefault(
                relation_key,
                {
                    "identity": str(relation_identity),
                    "normalized_identity": identity,
                    "relation_kind": str(relation_kind),
                    "view": "technical" if bool(hidden_by_default) else "business_sources",
                    "semantic_role": str(semantic_role or "unknown"),
                    "classification_status": str(classification_status or "unresolved"),
                    "fields": defaultdict(set),
                },
            )
            if column_name:
                relation["fields"][normalize_identifier(column_name)].add(str(usage_role or "unknown"))

        usage_rows = connection.execute(
            f"""
            SELECT file,
                   count(*) AS total_count,
                   count(*) FILTER (
                       WHERE relation_id IS NULL OR relation_id='' OR resolution_status!='resolved'
                   ) AS unresolved_count
              FROM sql_column_usage
             WHERE repo_id=? AND file IN ({placeholders})
             GROUP BY file
            """,
            [repo_id, *selected_files],
        ).fetchall()
        for file, total_count, unresolved_count in usage_rows:
            actual[str(file)]["column_usages"] = int(total_count or 0)
            actual[str(file)]["unresolved_column_usages"] = int(unresolved_count or 0)
    for case in actual.values():
        for relation in case["relations"].values():
            relation["fields"] = {
                name: sorted(roles) for name, roles in sorted(relation["fields"].items())
            }
    return actual


def evaluate_inventory(
    fixture: dict[str, Any],
    actual_by_file: dict[str, dict[str, Any]],
    *,
    repository_root: str | Path | None = None,
    target_gates: dict[str, float] | None = None,
) -> dict[str, Any]:
    relation_tp = relation_fp = relation_fn = 0
    classification_correct = classification_total = 0
    field_tp = field_fp = field_fn = 0
    role_correct = role_total = 0
    hash_mismatches: list[dict[str, str]] = []
    case_reports: list[dict[str, Any]] = []
    unresolved_total = column_usage_total = 0
    root = Path(repository_root) if repository_root else None

    for case in fixture["cases"]:
        file = str(case["file"])
        actual_case = actual_by_file.get(
            file, {"relations": {}, "unresolved_column_usages": 0, "column_usages": 0}
        )
        actual_relations = actual_case.get("relations", {})
        expected_relations = {
            (str(item["relation_kind"]), normalize_identifier(item["identity"])): item
            for item in case.get("expected_relations", [])
        }
        actual_keys = set(actual_relations)
        expected_keys = set(expected_relations)
        matched = actual_keys & expected_keys
        missing = expected_keys - actual_keys
        unexpected = actual_keys - expected_keys
        relation_tp += len(matched)
        relation_fn += len(missing)
        relation_fp += len(unexpected)

        classification_mismatches: list[dict[str, str]] = []
        for key in sorted(matched):
            classification_total += 1
            expected_view = str(expected_relations[key]["expected_view"])
            actual_view = str(actual_relations[key]["view"])
            if expected_view == actual_view:
                classification_correct += 1
            else:
                classification_mismatches.append(
                    {
                        "relation": actual_relations[key]["identity"],
                        "expected_view": expected_view,
                        "actual_view": actual_view,
                    }
                )

        field_mismatches: list[dict[str, Any]] = []
        for field_expectation in case.get("field_expectations", []):
            normalized_relation = normalize_identifier(field_expectation["relation_identity"])
            relation_key = next(
                (key for key in actual_keys if key[1] == normalized_relation), None
            )
            actual_fields = (
                actual_relations[relation_key]["fields"] if relation_key is not None else {}
            )
            expected_fields = {
                normalize_identifier(item["name"]): sorted(set(map(str, item.get("roles", []))))
                for item in field_expectation.get("fields", [])
            }
            expected_field_names = set(expected_fields)
            actual_field_names = set(actual_fields)
            matched_fields = expected_field_names & actual_field_names
            missing_fields = expected_field_names - actual_field_names
            extra_fields = (
                actual_field_names - expected_field_names
                if field_expectation.get("mode", "subset") == "exact"
                else set()
            )
            field_tp += len(matched_fields)
            field_fn += len(missing_fields)
            field_fp += len(extra_fields)
            role_mismatches: list[dict[str, Any]] = []
            for field_name in sorted(matched_fields):
                role_total += 1
                expected_roles = expected_fields[field_name]
                actual_roles = sorted(set(actual_fields[field_name]))
                if expected_roles == actual_roles:
                    role_correct += 1
                else:
                    role_mismatches.append(
                        {
                            "field": field_name,
                            "expected_roles": expected_roles,
                            "actual_roles": actual_roles,
                        }
                    )
            if missing_fields or extra_fields or role_mismatches or relation_key is None:
                field_mismatches.append(
                    {
                        "relation": field_expectation["relation_identity"],
                        "mode": field_expectation.get("mode", "subset"),
                        "relation_found": relation_key is not None,
                        "missing_fields": sorted(missing_fields),
                        "unexpected_fields": sorted(extra_fields),
                        "role_mismatches": role_mismatches,
                    }
                )

        source_hash_status = "not_checked"
        if root is not None:
            source_path = root / file
            if not source_path.is_file():
                source_hash_status = "missing"
                hash_mismatches.append({"file": file, "status": "missing"})
            else:
                digest = hashlib.sha256(source_path.read_bytes()).hexdigest()
                expected_digest = str(case.get("source_sha256") or "")
                source_hash_status = "matched" if digest == expected_digest else "mismatched"
                if digest != expected_digest:
                    hash_mismatches.append(
                        {
                            "file": file,
                            "status": "mismatched",
                            "expected": expected_digest,
                            "actual": digest,
                        }
                    )

        unresolved = int(actual_case.get("unresolved_column_usages", 0))
        total_usages = int(actual_case.get("column_usages", 0))
        unresolved_total += unresolved
        column_usage_total += total_usages
        case_reports.append(
            {
                "file": file,
                "tags": list(case.get("tags", [])),
                "source_hash_status": source_hash_status,
                "expected_relation_count": len(expected_keys),
                "actual_relation_count": len(actual_keys),
                "missing_relations": [
                    {
                        "relation_kind": key[0],
                        "identity": expected_relations[key]["identity"],
                        "expected_view": expected_relations[key]["expected_view"],
                    }
                    for key in sorted(missing)
                ],
                "unexpected_relations": [
                    {
                        "relation_kind": key[0],
                        "identity": actual_relations[key]["identity"],
                        "actual_view": actual_relations[key]["view"],
                    }
                    for key in sorted(unexpected)
                ],
                "classification_mismatches": classification_mismatches,
                "field_mismatches": field_mismatches,
                "column_usages": total_usages,
                "unresolved_column_usages": unresolved,
                "status": (
                    "passed"
                    if not missing
                    and not unexpected
                    and not classification_mismatches
                    and not field_mismatches
                    else "failed"
                ),
            }
        )

    metrics = {
        "relation_true_positive": relation_tp,
        "relation_false_positive": relation_fp,
        "relation_false_negative": relation_fn,
        "relation_precision": _safe_ratio(relation_tp, relation_tp + relation_fp),
        "relation_recall": _safe_ratio(relation_tp, relation_tp + relation_fn),
        "classification_correct": classification_correct,
        "classification_total": classification_total,
        "classification_accuracy": _safe_ratio(classification_correct, classification_total),
        "field_true_positive": field_tp,
        "field_false_positive": field_fp,
        "field_false_negative": field_fn,
        "field_precision": _safe_ratio(field_tp, field_tp + field_fp),
        "field_recall": _safe_ratio(field_tp, field_tp + field_fn),
        "field_role_correct": role_correct,
        "field_role_total": role_total,
        "field_role_accuracy": _safe_ratio(role_correct, role_total),
        "column_usages": column_usage_total,
        "unresolved_column_usages": unresolved_total,
        "column_resolution_rate": _safe_ratio(
            column_usage_total - unresolved_total, column_usage_total
        ),
        "case_count": len(case_reports),
        "passed_cases": sum(1 for item in case_reports if item["status"] == "passed"),
        "failed_cases": sum(1 for item in case_reports if item["status"] == "failed"),
    }
    gates = dict(DEFAULT_TARGET_GATES)
    if target_gates:
        gates.update(target_gates)
    gate_results = {
        name: {
            "target": float(target),
            "actual": float(metrics[name]),
            "passed": float(metrics[name]) >= float(target),
        }
        for name, target in gates.items()
    }
    return {
        "schema_version": SCHEMA_VERSION,
        "fixture_id": fixture.get("fixture_id"),
        "repo_id": fixture.get("repo_id"),
        "metrics": metrics,
        "target_gates": gate_results,
        "target_status": (
            "passed" if all(item["passed"] for item in gate_results.values()) else "failed"
        ),
        "source_hash_mismatches": hash_mismatches,
        "cases": case_reports,
    }


def render_markdown_report(report: dict[str, Any]) -> str:
    metrics = report["metrics"]
    lines = [
        "# SQL Source Inventory Quality Report",
        "",
        f"- Fixture: `{report.get('fixture_id')}`",
        f"- Repository: `{report.get('repo_id')}`",
        f"- Target status: **{report.get('target_status')}**",
        "",
        "## Metrics",
        "",
        "| Metric | Value |",
        "|---|---:|",
        f"| Relation precision | {metrics['relation_precision']:.4f} |",
        f"| Relation recall | {metrics['relation_recall']:.4f} |",
        f"| Classification accuracy | {metrics['classification_accuracy']:.4f} |",
        f"| Field precision | {metrics['field_precision']:.4f} |",
        f"| Field recall | {metrics['field_recall']:.4f} |",
        f"| Field-role accuracy | {metrics['field_role_accuracy']:.4f} |",
        f"| Column resolution rate | {metrics['column_resolution_rate']:.4f} |",
        f"| Cases passed | {metrics['passed_cases']} / {metrics['case_count']} |",
        "",
        "## Target gates",
        "",
        "| Gate | Target | Actual | Status |",
        "|---|---:|---:|---|",
    ]
    for name, gate in report["target_gates"].items():
        lines.append(
            f"| {name} | {gate['target']:.4f} | {gate['actual']:.4f} | "
            f"{'passed' if gate['passed'] else 'failed'} |"
        )
    failed_cases = [case for case in report["cases"] if case["status"] != "passed"]
    lines.extend(["", "## Failed cases", ""])
    if not failed_cases:
        lines.append("None.")
    else:
        for case in failed_cases:
            lines.append(f"### `{case['file']}`")
            if case["missing_relations"]:
                lines.append("- Missing relations: " + ", ".join(
                    f"`{item['identity']}`" for item in case["missing_relations"]
                ))
            if case["unexpected_relations"]:
                lines.append("- Unexpected relations: " + ", ".join(
                    f"`{item['identity']}`" for item in case["unexpected_relations"]
                ))
            if case["classification_mismatches"]:
                lines.append("- Classification mismatches: " + ", ".join(
                    f"`{item['relation']}` ({item['actual_view']} != {item['expected_view']})"
                    for item in case["classification_mismatches"]
                ))
            if case["field_mismatches"]:
                lines.append(f"- Field expectation failures: {len(case['field_mismatches'])}")
            lines.append(
                f"- Unresolved column usages: {case['unresolved_column_usages']} / "
                f"{case['column_usages']}"
            )
            lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Evaluate SQL source inventory against a curated fixture")
    parser.add_argument("--artifact", required=True, help="Path to knowledge-layer.duckdb")
    parser.add_argument("--fixture", required=True, help="Path to quality fixture JSON")
    parser.add_argument("--repository-root", help="Repository root used to verify source SHA-256 values")
    parser.add_argument("--output-json", required=True)
    parser.add_argument("--output-markdown")
    parser.add_argument("--fail-on-target-gates", action="store_true")
    args = parser.parse_args(argv)

    fixture = load_quality_fixture(args.fixture)
    files = [str(case["file"]) for case in fixture["cases"]]
    actual = collect_actual_inventory(args.artifact, repo_id=str(fixture["repo_id"]), files=files)
    report = evaluate_inventory(
        fixture,
        actual,
        repository_root=args.repository_root,
    )
    output_json = Path(args.output_json)
    output_json.parent.mkdir(parents=True, exist_ok=True)
    output_json.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    if args.output_markdown:
        output_markdown = Path(args.output_markdown)
        output_markdown.parent.mkdir(parents=True, exist_ok=True)
        output_markdown.write_text(render_markdown_report(report), encoding="utf-8")
    return 2 if args.fail_on_target_gates and report["target_status"] != "passed" else 0


if __name__ == "__main__":
    raise SystemExit(main())
