import json

import pytest

from aisl_cli import cli


def test_parser_exposes_generic_commands():
    parser = cli.build_parser()
    ns = parser.parse_args([
        "tools", "--api-url", "http://example", "--system-id", "s"
    ])
    assert ns.command == "tools"
    assert ns.profile == "data-model/v1"


def test_parser_exposes_data_model_object_projection():
    parser = cli.build_parser()
    ns = parser.parse_args([
        "project", "data-model-object",
        "--api-url", "http://example", "--system-id", "s", "--object", "com.acme.Individual"
    ])
    assert ns.command == "project"
    assert ns.projection == "data-model-object"
    assert ns.object == "com.acme.Individual"


def test_headers_reject_invalid_format():
    with pytest.raises(ValueError):
        cli._headers(["broken"])


def test_data_model_projection_is_public_sdk_not_cli_private_helper():
    assert not hasattr(cli, "_relationship_projection")
    assert hasattr(cli, "project_data_model_object")
