from pathlib import Path
from types import SimpleNamespace

from aisl_reporting.contracts import PreparedReport, ReportRequest
from aisl_reporting.pipeline import _required_headings, build_report


class _Renderer:
    description = "test renderer"

    def render(self, *, prompt, dataset):
        return "# Не полностью структурированный отчёт\n\nПолезный текст.\n"


def _prepared(tmp_path: Path) -> PreparedReport:
    request = ReportRequest(
        report_type="system-description",
        report_version="v1",
        api_url="http://knowledge-api.test",
        system_id="fixture",
        output_name="report.md",
    )
    dataset = {
        "request": {"include_evidence": True},
        "evidence_index": {},
        "validation": {"valid": True, "dataset_bytes": 10, "evidence_count": 0},
    }
    return PreparedReport(request=request, dataset=dataset, renderer_prompt="Render", profile_dir=tmp_path)


def test_build_report_preserves_report_and_returns_warnings(monkeypatch, tmp_path):
    prepared = _prepared(tmp_path)
    monkeypatch.setattr("aisl_reporting.pipeline.prepare_report", lambda *args, **kwargs: prepared)
    monkeypatch.setattr(
        "aisl_reporting.pipeline.load_profile",
        lambda profile_id: SimpleNamespace(text=lambda name: "required_headings:\n  - Резюме\n"),
    )
    events = []
    manifest = build_report(
        prepared.request,
        tmp_path / "out",
        _Renderer(),
        progress=lambda level, message: events.append((level, message)),
        heartbeat_sec=0,
    )
    assert manifest.status == "completed_with_warnings"
    assert manifest.report_path.is_file()
    assert manifest.validation_path.is_file()
    assert manifest.warnings
    assert any("Rendered report saved" in message for _, message in events)


def test_validation_warnings_never_fail_report_build(monkeypatch, tmp_path):
    prepared = _prepared(tmp_path)
    monkeypatch.setattr("aisl_reporting.pipeline.prepare_report", lambda *args, **kwargs: prepared)
    monkeypatch.setattr(
        "aisl_reporting.pipeline.load_profile",
        lambda profile_id: SimpleNamespace(text=lambda name: "required_headings:\n  - Резюме\n"),
    )
    output = tmp_path / "out-warning"

    manifest = build_report(prepared.request, output, _Renderer(), heartbeat_sec=0)

    assert manifest.report_path.exists()
    assert manifest.status == "completed_with_warnings"
    assert manifest.validation["report"]["errors"] == []
    assert manifest.validation["report"]["warnings"]

def test_required_headings_include_business_specific_opening(tmp_path):
    request = ReportRequest(
        report_type="system-description",
        report_version="v1",
        api_url="http://knowledge-api.test",
        system_id="fixture",
        audience="business",
    )
    contract = {
        "required_headings": ["Краткий вывод"],
        "audience_required_headings": {
            "business": ["О системе"],
            "engineering": ["Технический контекст"],
        },
    }

    assert _required_headings(contract, request) == ["О системе", "Краткий вывод"]


def test_required_headings_do_not_apply_other_audience_opening(tmp_path):
    request = ReportRequest(
        report_type="system-description",
        report_version="v1",
        api_url="http://knowledge-api.test",
        system_id="fixture",
        audience="architecture",
    )
    contract = {
        "required_headings": ["Краткий вывод"],
        "audience_required_headings": {"business": ["О системе"]},
    }

    assert _required_headings(contract, request) == ["Краткий вывод"]


class _CorrectingRenderer:
    description = "correcting test renderer"
    supports_correction = True

    def __init__(self, *, valid_correction: bool = True) -> None:
        self.calls = 0
        self.valid_correction = valid_correction

    def render(self, *, prompt, dataset):
        self.calls += 1
        if self.calls == 1:
            return "## Краткий вывод\n\nФизическая модель извлечена.\n\n## ER-диаграммы\n\nДиаграмма пока не сформирована.\n"
        assert dataset["schema_version"] == "er_correction_dataset/v1"
        assert dataset["required_layers"] == ["physical_er"]
        if not self.valid_correction:
            return "## ER-диаграммы\n\nКоррекция без Mermaid.\n"
        return """## ER-диаграммы

### Физическая модель

```mermaid
erDiagram
    CUSTOMER {
        bigint id PK
    }
```
"""


def _prepared_er(tmp_path: Path) -> PreparedReport:
    request = ReportRequest(
        report_type="data-model-report",
        report_version="v1",
        api_url="http://knowledge-api.test",
        system_id="fixture",
        output_name="report.md",
        include_evidence=False,
    )
    dataset = {
        "profile_id": "data-model-report/v1",
        "request": {"include_evidence": False},
        "coverage": {"report_mode": "physical_only"},
        "sections": {
            "diagrams": {
                "logical_er": {"status": "not_observed", "entities": [], "relationships": []},
                "physical_er": {
                    "status": "observed",
                    "mode": "entity_only",
                    "tables": [{"name": "customer", "qualified_name": "customer", "attributes": [{"name": "id", "type": "bigint", "primary_key": True}]}],
                    "relationships": [],
                },
                "observed_usage": {"status": "not_observed", "relationships": []},
            }
        },
        "evidence_index": {},
        "validation": {"valid": True, "dataset_bytes": 10, "evidence_count": 0},
    }
    return PreparedReport(request=request, dataset=dataset, renderer_prompt="Render", profile_dir=tmp_path)


def _mock_data_model_profile(monkeypatch) -> None:
    monkeypatch.setattr(
        "aisl_reporting.pipeline.load_profile",
        lambda profile_id: SimpleNamespace(
            text=lambda name: "required_headings:\n  - Краткий вывод\n  - ER-диаграммы\n"
        ),
    )


def test_build_report_applies_deterministic_er_without_second_model_call(monkeypatch, tmp_path):
    prepared = _prepared_er(tmp_path)
    monkeypatch.setattr("aisl_reporting.pipeline.prepare_report", lambda *args, **kwargs: prepared)
    _mock_data_model_profile(monkeypatch)
    renderer = _CorrectingRenderer()

    manifest = build_report(prepared.request, tmp_path / "out-er", renderer, heartbeat_sec=0)

    assert renderer.calls == 1
    assert manifest.status == "completed"
    report = manifest.report_path.read_text(encoding="utf-8")
    assert "```mermaid\nerDiagram" in report
    assert "Диаграмма пока не сформирована" not in report
    assert not (tmp_path / "out-er" / "report-er-correction.md").exists()
    assert manifest.validation["report"]["deterministic_er"]["applied"] is True
    assert manifest.validation["report"]["er_correction"]["status"] == "not_required"


def test_failed_er_correction_keeps_original_report_when_deterministic_generation_is_unavailable(monkeypatch, tmp_path):
    prepared = _prepared_er(tmp_path)
    monkeypatch.setattr("aisl_reporting.pipeline.prepare_report", lambda *args, **kwargs: prepared)
    monkeypatch.setattr(
        "aisl_reporting.pipeline.apply_deterministic_er_section",
        lambda report, dataset: (report, {"applicable": False, "applied": False, "reason": "forced_test"}),
    )
    _mock_data_model_profile(monkeypatch)
    renderer = _CorrectingRenderer(valid_correction=False)

    manifest = build_report(prepared.request, tmp_path / "out-er-failed", renderer, heartbeat_sec=0)

    assert renderer.calls == 2
    assert manifest.status == "completed_with_warnings"
    report = manifest.report_path.read_text(encoding="utf-8")
    assert "Диаграмма пока не сформирована" in report
    assert "```mermaid" not in report
    warning_codes = {item["code"] for item in manifest.validation["report"]["warnings"]}
    assert "missing_required_er_diagram" in warning_codes
    assert "er_diagram_correction_rejected" in warning_codes
    assert manifest.validation["report"]["er_correction"]["status"] == "rejected"
