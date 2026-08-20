from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Mapping

import yaml

_HEADING = re.compile(r"^##\s+(.+?)\s*$", re.MULTILINE)
_EVIDENCE = re.compile(r"\[(evidence_[a-f0-9]{20}|ev_[a-f0-9]{20})\]")
_NUMBER = re.compile(r"\b\d[\d\s  ,.]*\b")


def report_features(text: str) -> dict[str, Any]:
    return {
        "chars": len(text),
        "headings": _HEADING.findall(text),
        "evidence_ids": sorted(set(_EVIDENCE.findall(text))),
        "mermaid_blocks": text.count("```mermaid"),
        "table_rows": sum(1 for line in text.splitlines() if line.strip().startswith("|") and line.strip().endswith("|")),
        "numeric_tokens": sorted(set(match.group(0) for match in _NUMBER.finditer(text))),
    }


def compare_reports(*, old_report: str, new_report: str, dataset: Mapping[str, Any], expectations_path: Path | None = None) -> dict[str, Any]:
    old = report_features(old_report)
    new = report_features(new_report)
    expected: dict[str, Any] = {}
    if expectations_path:
        expected = yaml.safe_load(expectations_path.read_text(encoding="utf-8")) or {}
    required = list(expected.get("required_capabilities") or [])
    capability_checks = {
        "explicit_scope": "Область" in new_report or "Scope" in new_report,
        "executive_summary": "Резюме" in new_report,
        "apparent_business_purpose": "Назначение" in new_report,
        "functional_capabilities": "Основные функциональные возможности" in new_report,
        "project_structure": "Техническая архитектура" in new_report or "Состав" in new_report,
        "technologies": any(token in new_report.lower() for token in ("технолог", "spring boot", "gradle", "liquibase")),
        "inbound_interfaces": "Входящие интерфейсы" in new_report,
        "outbound_integrations": "Исходящие интеграции" in new_report or "Интеграции" in new_report,
        "data_and_storage": "Данные и хранение" in new_report,
        "gaps_and_limitations": "Надёжность выводов и ограничения" in new_report or "Пробелы" in new_report,
        "exact_evidence_refs": bool(new["evidence_ids"]),
        "representative_journeys": "Репрезентативные сценарии" in new_report or "journey" in new_report.lower(),
        "diagram_ready_relations": bool((dataset.get("sections") or {}).get("diagrams")),
        "owner_questions": "Вопросы владельцу" in new_report,
    }
    missing_capabilities = [item for item in required if not capability_checks.get(item, False)]
    return {
        "schema_version": "report_regression/v1",
        "old": old,
        "new": new,
        "dataset": {
            "schema_version": dataset.get("schema_version"),
            "evidence_count": len(dataset.get("evidence_index") or {}),
            "section_names": sorted((dataset.get("sections") or {}).keys()),
        },
        "capability_checks": capability_checks,
        "missing_capabilities": missing_capabilities,
        "passed": not missing_capabilities,
    }


def write_comparison_markdown(result: Mapping[str, Any]) -> str:
    lines = ["# Report architecture regression", "", f"Status: **{'PASS' if result.get('passed') else 'FAIL'}**", ""]
    lines += ["## Metrics", "", "| Metric | Old | New |", "|---|---:|---:|",
              f"| Characters | {result['old']['chars']} | {result['new']['chars']} |",
              f"| Evidence IDs | {len(result['old']['evidence_ids'])} | {len(result['new']['evidence_ids'])} |",
              f"| Mermaid blocks | {result['old']['mermaid_blocks']} | {result['new']['mermaid_blocks']} |",
              f"| Table rows | {result['old']['table_rows']} | {result['new']['table_rows']} |", ""]
    lines += ["## Capability checks", ""]
    for name, ok in sorted(result.get("capability_checks", {}).items()):
        lines.append(f"- [{'x' if ok else ' '}] `{name}`")
    if result.get("missing_capabilities"):
        lines += ["", "## Missing capabilities", ""] + [f"- `{item}`" for item in result["missing_capabilities"]]
    return "\n".join(lines).rstrip() + "\n"
