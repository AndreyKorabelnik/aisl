from __future__ import annotations

import hashlib
import json
import re
from typing import Any, Iterable

from code_analyzer_core.models import Fact


def _stable_id(*parts: Any) -> str:
    raw = "|".join(json.dumps(part, sort_keys=True, ensure_ascii=False, default=str) for part in parts)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:24]


def _property_value(properties: dict[str, Any], path: str) -> Any:
    current: Any = properties
    for token in path.split("."):
        if not isinstance(current, dict) or token not in current:
            return None
        current = current[token]
    return current


def _matches_condition(actual: Any, condition: Any) -> bool:
    if isinstance(condition, dict):
        if "equals" in condition and actual != condition["equals"]:
            return False
        if "in" in condition and actual not in condition["in"]:
            return False
        if "contains" in condition:
            expected = condition["contains"]
            if isinstance(actual, (list, tuple, set)):
                if expected not in actual:
                    return False
            elif expected not in str(actual or ""):
                return False
        if "regex" in condition and re.search(str(condition["regex"]), str(actual or "")) is None:
            return False
        if condition.get("exists") is True and actual is None:
            return False
        if condition.get("exists") is False and actual is not None:
            return False
        return True
    return actual == condition


def fact_matches_rule(fact: Fact, rule: dict[str, Any]) -> bool:
    fact_types = rule.get("fact_types") or ([rule["fact_type"]] if rule.get("fact_type") else [])
    if fact_types and fact.fact_type not in fact_types:
        return False
    name_condition = rule.get("name")
    if name_condition is not None and not _matches_condition(fact.name, name_condition):
        return False
    for path, condition in (rule.get("properties") or {}).items():
        if not _matches_condition(_property_value(fact.properties, str(path)), condition):
            return False
    return True


def apply_framework_pattern_rules(
    facts: Iterable[Fact],
    rules: Iterable[dict[str, Any]],
) -> tuple[list[Fact], dict[str, Any]]:
    """Apply declarative framework-pattern rules to already extracted observations.

    The engine only publishes matched technical observations. It does not assign
    confidence, semantic equivalence, physical-table meaning, keys, relations,
    or domain verdicts.
    """
    source_facts = list(facts)
    emitted: list[Fact] = []
    rule_counts: dict[str, int] = {}

    for raw_rule in rules:
        rule = dict(raw_rule)
        rule_id = str(rule.get("rule_id") or "").strip()
        if not rule_id:
            raise ValueError("framework pattern rule requires non-empty rule_id")
        output_kind = str(rule.get("output_kind") or "framework_pattern_match")
        matches = [fact for fact in source_facts if fact_matches_rule(fact, rule.get("match") or {})]
        rule_counts[rule_id] = len(matches)
        for source in matches:
            source_observation_id = source.properties.get("observation_id")
            emitted.append(Fact(
                fact_type="framework_pattern_observation",
                name=f"{rule_id}:{source.name}",
                properties={
                    "observation_id": _stable_id("framework_pattern", rule_id, source.fact_type, source.name, source_observation_id),
                    "rule_id": rule_id,
                    "output_kind": output_kind,
                    "source_fact_type": source.fact_type,
                    "source_fact_name": source.name,
                    "source_observation_id": source_observation_id,
                    "captured_properties": {
                        key: _property_value(source.properties, path)
                        for key, path in (rule.get("capture") or {}).items()
                    },
                    "rule_metadata": dict(rule.get("metadata") or {}),
                    "observation_policy": "declarative technical pattern match only; no confidence, semantic equivalence, key, relation, storage, or domain verdict",
                },
                evidence=list(source.evidence),
            ))

    status = {
        "status": "completed",
        "rules_evaluated": len(rule_counts),
        "source_facts_evaluated": len(source_facts),
        "observations_emitted": len(emitted),
        "matches_by_rule": dict(sorted(rule_counts.items())),
        "facts_only_policy": "matches preserve source provenance and remain technical observations without confidence or verdict",
    }
    return emitted, status
