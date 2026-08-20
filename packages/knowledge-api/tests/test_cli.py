from __future__ import annotations

import pytest

from knowledge_api.cli import build_parser


def test_cli_exposes_execution_result_publication() -> None:
    parser = build_parser()
    help_text = parser.format_help()
    for command in ("serve", "validate", "publish", "import", "system", "revision", "consumer-kit"):
        assert command in help_text

    publish = parser.parse_args(
        [
            "publish",
            "--system-id",
            "ucp",
            "--execution-result",
            "outputs/ucp/knowledge_execution_result.json",
            "--database",
            "outputs/knowledge-api.sqlite3",
            "--base-revision-id",
            "rev-base",
        ]
    )
    assert publish.command == "publish"
    assert publish.activate is True
    assert publish.base_revision_id == "rev-base"
    assert str(publish.execution_result).endswith("knowledge_execution_result.json")
    assert not hasattr(publish, "knowledge_layer")
    assert not hasattr(publish, "source_manifest")

    delete = parser.parse_args(["system", "delete", "--system-id", "ucp", "--yes"])
    assert delete.system_command == "delete"
    assert delete.yes is True


def test_legacy_publication_flags_are_rejected() -> None:
    parser = build_parser()
    with pytest.raises(SystemExit):
        parser.parse_args(
            [
                "publish",
                "--system-id",
                "ucp",
                "--knowledge-layer",
                "legacy.duckdb",
            ]
        )


def test_cli_parses_consumer_kit_export() -> None:
    parser = build_parser()
    args = parser.parse_args([
        "consumer-kit",
        "--system", "ucp",
        "--revision-id", "rev-1",
        "--profile", "attribute-addition-plan/v1",
        "--output", "consumer-kit",
    ])
    assert args.command == "consumer-kit"
    assert args.system_id == "ucp"
    assert args.revision_id == "rev-1"
    assert args.profile_id == "attribute-addition-plan/v1"
    assert str(args.output) == "consumer-kit"


def test_cli_parses_publication_bundle_import() -> None:
    parser = build_parser()
    args = parser.parse_args(["import", "--bundle", "ucp.aisl.zip", "--database", "server.sqlite3"])
    assert args.command == "import"
    assert str(args.bundle) == "ucp.aisl.zip"
    assert args.activate is None
