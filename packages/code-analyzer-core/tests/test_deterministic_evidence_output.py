from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys

from code_analyzer_core.models import Fact
from code_analyzer_core.navigation import _attribute_derivation_brief_from_fact
from code_analyzer_core.scanners.java_trace_builder import _find_origin_path


def test_origin_path_relation_chain_matches_forward_call_path() -> None:
    origins = {
        "Controller.receive": [
            {
                "origin_id": "origin_1",
                "operation": "Controller.receive",
                "operation_id": "Controller.receive",
                "payload_parameter": "request",
            }
        ]
    }
    calls = {
        "Service.store": [
            {
                "call_id": "call_1",
                "caller_operation_id": "Controller.receive",
                "callee_operation_id": "Service.store",
                "argument_bindings": [
                    {
                        "argument_index": 0,
                        "callee_parameter": "dto",
                        "caller_source_parameter": "request",
                        "relation": "field_extracted",
                    }
                ],
            }
        ],
        "Repository.save": [
            {
                "call_id": "call_2",
                "caller_operation_id": "Service.store",
                "callee_operation_id": "Repository.save",
                "argument_bindings": [
                    {
                        "argument_index": 0,
                        "callee_parameter": "entity",
                        "caller_source_parameter": "dto",
                        "relation": "derived_object",
                    }
                ],
            }
        ],
    }

    origin, call_path, relation_chain = _find_origin_path(
        target_operation="Repository.save",
        target_parameter="entity",
        origins_by_operation=origins,
        reverse_calls=calls,
    )

    assert origin and origin["origin_id"] == "origin_1"
    assert [item["call_id"] for item in call_path] == ["call_1", "call_2"]
    assert relation_chain == ["field_extracted", "derived_object"]


def test_origin_path_selection_is_stable_for_unsorted_candidates() -> None:
    origins = {
        "Controller.receive": [
            {"origin_id": "origin_b", "operation": "Controller.receive", "payload_parameter": "request"},
            {"origin_id": "origin_a", "operation": "Controller.receive", "payload_parameter": "request"},
        ]
    }
    calls = {
        "Service.store": [
            {
                "call_id": "call_b",
                "caller_operation_id": "Controller.receive",
                "callee_operation_id": "Service.store",
                "argument_bindings": [
                    {
                        "argument_index": 1,
                        "callee_parameter": "dto",
                        "caller_source_parameter": "other",
                        "relation": "same_object",
                    },
                    {
                        "argument_index": 0,
                        "callee_parameter": "dto",
                        "caller_source_parameter": "request",
                        "relation": "field_extracted",
                    },
                ],
            },
            {
                "call_id": "call_a",
                "caller_operation_id": "Controller.receive",
                "callee_operation_id": "Service.store",
                "argument_bindings": [
                    {
                        "argument_index": 0,
                        "callee_parameter": "dto",
                        "caller_source_parameter": "request",
                        "relation": "same_object",
                    }
                ],
            },
        ]
    }

    origin, call_path, relation_chain = _find_origin_path(
        target_operation="Service.store",
        target_parameter="dto",
        origins_by_operation=origins,
        reverse_calls=calls,
    )

    assert origin and origin["origin_id"] == "origin_a"
    assert [item["call_id"] for item in call_path] == ["call_a"]
    assert relation_chain == ["same_object"]


def _derivation_id() -> str:
    fact = Fact(
        fact_type="attribute_derivation",
        name="CustomerMapper.map",
        properties={
            "operation": "CustomerMapper.map",
            "source_fields": ["source.birthDate"],
            "target_field": "target.birthDate",
        },
    )
    item = _attribute_derivation_brief_from_fact(fact)
    assert item is not None
    return str(item["attribute_derivation_id"])


def test_attribute_derivation_fallback_id_is_stable_in_process() -> None:
    assert _derivation_id() == _derivation_id()
    assert _derivation_id().startswith("derived_")
    assert len(_derivation_id()) == len("derived_") + 12


def test_attribute_derivation_fallback_id_is_stable_across_hash_seeds() -> None:
    root = Path(__file__).resolve().parents[1]
    script = """
import json
from code_analyzer_core.models import Fact
from code_analyzer_core.navigation import _attribute_derivation_brief_from_fact
fact = Fact(
    fact_type='attribute_derivation',
    name='CustomerMapper.map',
    properties={
        'operation': 'CustomerMapper.map',
        'source_fields': ['source.birthDate'],
        'target_field': 'target.birthDate',
    },
)
print(json.dumps(_attribute_derivation_brief_from_fact(fact)['attribute_derivation_id']))
"""
    values: list[str] = []
    for seed in ("1", "777"):
        env = os.environ.copy()
        env["PYTHONHASHSEED"] = seed
        env["PYTHONPATH"] = str(root)
        completed = subprocess.run(
            [sys.executable, "-c", script],
            cwd=root,
            env=env,
            check=True,
            capture_output=True,
            text=True,
        )
        values.append(json.loads(completed.stdout.strip()))
    assert values[0] == values[1]


def test_assignment_source_prefers_field_extraction_over_generic_parameter_reference() -> None:
    from code_analyzer_core.scanners.java_flow_builder import _assignment_map_from_syntax
    from code_analyzer_core.scanners.java_syntax import parse_java_text

    parsed = parse_java_text(
        """
        class Handler {
          void change(String urn, PhoneBlock phoneBlock) {
            PhoneBlockDto blockDto = PhoneBlockDto.builder()
                .phoneNumber(phoneBlock.getPhoneNumber())
                .urn(urn)
                .build();
          }
        }
        """
    )
    method = parsed.methods[0]
    assignments = _assignment_map_from_syntax(method.assignments, {"urn", "phoneBlock"})

    assert assignments["blockDto"]["source_parameter"] == "phoneBlock"
    assert assignments["blockDto"]["source_field"] == "phoneNumber"
