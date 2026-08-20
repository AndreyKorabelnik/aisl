from __future__ import annotations

from pathlib import Path

import code_evidence.access as access


def test_source_inspect_catalog_symbol_is_routed_to_backend_token(monkeypatch, tmp_path: Path) -> None:
    captured: dict[str, object] = {}

    def fake_source_inspect(analysis_out: Path, token: str, max_results: int = 20):
        captured["analysis_out"] = analysis_out
        captured["token"] = token
        captured["max_results"] = max_results
        return {"policy": "read_only_targeted_source_inspection", "token": token}

    monkeypatch.setattr(access, "_catalog_commands", lambda: {"source_inspect": {"command_id": "source_inspect"}})
    monkeypatch.setattr(access.commands, "source_inspect", fake_source_inspect)

    result = access.execute_evidence_request(
        {
            "command_id": "source_inspect",
            "arguments": {"symbol": "Service.process", "max_results": "5"},
        },
        static_analysis_output=tmp_path,
    )

    assert result["token"] == "Service.process"
    assert captured == {
        "analysis_out": tmp_path,
        "token": "Service.process",
        "max_results": 5,
    }
