from pathlib import Path

from code_analyzer_core.scanners.data_model_candidate_scanner import scan_data_model_candidate


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def test_strong_model_library_is_detected_without_full_data_model_analysis(tmp_path: Path) -> None:
    root = tmp_path / "model-lib"
    for index in range(8):
        _write(
            root / "src/main/java/com/example/domain/model" / f"Customer{index}.java",
            f"""
            package com.example.domain.model;
            @DomainEntity
            public class Customer{index} {{
                private String id;
                private String name;
                private Address address;
            }}
            """,
        )
    files = list(root.rglob("*"))
    profile, facts, status = scan_data_model_candidate(
        root,
        files,
        repo_id="model-lib",
        project_code="P",
        system_name="model-lib",
        core_version="test",
    )
    assert profile["candidate_status"] == "strong"
    assert profile["score"] >= 60
    assert profile["signals"]["annotated_model_type_count"] == 8
    assert profile["coverage"]["full_data_model_analysis_performed"] is False
    assert facts
    assert status["status"] == "success"
    assert all(not item["path"].startswith("/") for item in profile["evidence"])


def test_model_tooling_repository_is_detected_as_candidate(tmp_path: Path) -> None:
    root = tmp_path / "model-tooling"
    names = [
        "DataModelParser",
        "MetaModelGenerator",
        "ModelClass",
        "ModelProperty",
        "SchemaCompiler",
    ]
    for name in names:
        _write(
            root / "model-plugin/src/main/java/com/example/metamodel" / f"{name}.java",
            f"""
            package com.example.metamodel;
            public class {name} {{
                private String name;
                private String version;
            }}
            """,
        )
    profile, _, _ = scan_data_model_candidate(
        root,
        list(root.rglob("*")),
        repo_id="model-tooling",
        project_code="P",
        system_name="model-tooling",
        core_version="test",
    )
    assert profile["candidate_status"] in {"strong", "possible"}
    assert profile["signals"]["model_tooling_type_count"] >= 3


def test_executable_application_without_strong_model_signals_is_not_strong(tmp_path: Path) -> None:
    root = tmp_path / "application"
    for index in range(12):
        _write(
            root / "src/main/java/com/example/service" / f"OrderService{index}.java",
            f"""
            package com.example.service;
            @Service
            public class OrderService{index} {{
                private String value;
                public void run() {{}}
            }}
            """,
        )
    _write(
        root / "src/main/java/com/example/model/OrderDto.java",
        """
        package com.example.model;
        public class OrderDto {
            private String id;
            private String status;
        }
        """,
    )
    profile, _, _ = scan_data_model_candidate(
        root,
        list(root.rglob("*")),
        repo_id="application",
        project_code="P",
        system_name="application",
        core_version="test",
    )
    assert profile["candidate_status"] != "strong"
    assert any(item["component"] == "application_shape_penalty" for item in profile["score_components"])


def test_sql_only_repository_can_publish_data_model_candidate_evidence(tmp_path: Path) -> None:
    root = tmp_path / "sql-model"
    for index in range(20):
        _write(
            root / "model" / "migrations" / f"{index:03d}_create_table.sql",
            f"create table customer_{index} (id bigint primary key, name varchar(100));",
        )
    profile, facts, status = scan_data_model_candidate(
        root,
        list(root.rglob("*")),
        repo_id="sql-model",
        project_code="P",
        system_name="sql-model",
        core_version="test",
    )
    assert profile["signals"]["java_file_count"] == 0
    assert profile["signals"]["physical_schema_file_count"] == 20
    assert profile["candidate_status"] != "not_candidate"
    assert any(item["kind"] == "physical_schema" for item in profile["evidence"])
    assert facts
    assert status["status"] == "success"
