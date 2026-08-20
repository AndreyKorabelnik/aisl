from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

import yaml

EVIDENCE = re.compile(r"\[(evidence_[a-f0-9]{20})\]")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dataset", required=True)
    parser.add_argument("--report", required=True)
    parser.add_argument("--expectations", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()

    dataset = json.loads(Path(args.dataset).read_text(encoding="utf-8"))
    report = Path(args.report).read_text(encoding="utf-8")
    expectations = yaml.safe_load(Path(args.expectations).read_text(encoding="utf-8")) or {}
    sections = dataset["sections"]
    metadata = sections["change_metadata"]
    classification = sections["classification"]
    delta = sections["data_and_lineage_delta"]
    risk = sections["risk_signals"]
    quality = sections["quality_evidence"]
    policy = dataset["interpretation_policy"]
    encoded = json.dumps(dataset, ensure_ascii=False)

    checks = {
        "neutral_change_metadata": bool(metadata.get("repo_id") and metadata.get("commit_range")),
        "no_raw_emails": "@" not in json.dumps(metadata.get("authors") or []) and "@" not in json.dumps(metadata.get("committers") or []),
        "no_person_evaluation": policy.get("assess_change_not_person") is True and "производительност" not in report.lower(),
        "executive_summary": "## Краткое резюме изменения" in report,
        "technical_complexity_classification": bool(classification.get("technical_complexity", {}).get("classification")),
        "data_impact_classification": bool(classification.get("data_impact", {}).get("classification")),
        "overall_risk_classification": bool(classification.get("overall_risk", {}).get("classification")),
        "quality_evidence_classification": bool(classification.get("quality_evidence", {}).get("classification")),
        "evidence_confidence": bool(classification.get("evidence_confidence", {}).get("classification")),
        "changed_file_groups": bool(sections.get("changed_file_groups")),
        "mechanical_vs_semantic_distinction": "semantic_delta_items" in sections.get("executive_summary_inputs", {}),
        "schema_delta": "table_delta" in delta.get("items", {}) and "column_delta" in delta.get("items", {}),
        "lineage_delta": "lineage_delta" in delta.get("items", {}),
        "transformation_delta": "transformation_delta" in delta.get("items", {}),
        "flow_delta": "flow_delta" in delta.get("items", {}),
        "event_source_delta": "event_source_delta" in delta.get("items", {}),
        "runtime_config_risk": any(item.get("risk") == "runtime_config" for item in risk.get("risk_items", [])),
        "compatibility_contract_risk": any(item.get("risk") == "schema_contract" for item in risk.get("risk_items", [])),
        "migration_backfill_status": risk.get("migration_or_backfill_required") == "not_established",
        "tests_evidence": "test_files" in quality,
        "documentation_evidence": "documentation_files" in quality,
        "validation_execution_not_inferred": any("not proof that tests passed" in value for value in quality.get("limitations", [])),
        "practical_review_focus": bool(sections.get("review_focus")),
        "gaps_and_limitations": bool(sections.get("gaps_and_limitations", {}).get("items")),
        "coverage_delta_as_confidence_only": "coverage" in policy.get("score_hints", "").lower() or "coverage_changed" in classification.get("quality_evidence", {}),
        "changed_lines_not_primary": "never the primary" in policy.get("line_count_policy", ""),
        "exact_evidence_refs": bool(EVIDENCE.findall(report)),
        "no_internal_runtime_paths": "/mnt/data/" not in encoded and "/mnt/data/" not in report,
        "no_invented_business_context": policy.get("business_context", "").startswith("Business criticality"),
    }
    required = list(expectations.get("required_capabilities") or [])
    missing = [name for name in required if not checks.get(name)]
    result = {
        "schema_version": "git_change_report_migration_gate/v1",
        "status": "accepted_with_known_differences" if not missing else "failed",
        "source_profiles": expectations.get("source_profiles") or [],
        "historical_old_report_available": False,
        "checks": checks,
        "required_capabilities": required,
        "missing_capabilities": missing,
        "intentional_differences": expectations.get("intentional_differences") or [],
        "new_architecture": {
            "preliminary_llm_analysis_executed": False,
            "final_response_json_used": False,
            "dataset_bytes": dataset.get("validation", {}).get("dataset_bytes"),
            "renderer_prompt_role": "narrative_only",
        },
    }
    target = Path(args.output)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"status": result["status"], "checks": len(checks), "missing": missing}, ensure_ascii=False, indent=2))
    if missing:
        raise SystemExit(2)


if __name__ == "__main__":
    main()
