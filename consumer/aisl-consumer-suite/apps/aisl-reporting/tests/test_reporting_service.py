from __future__ import annotations

from pathlib import Path

import pytest

from aisl_reporting.service import ReportService, ReportingServiceConfig
from test_knowledge_api_reporting import _transport


def _response(path: Path) -> Path:
    headings = [
        "Краткий вывод", "Область отчёта", "Резюме модели данных", "ER-диаграммы",
        "Каталог объектов", "Детальное описание ключевых объектов", "Атрибуты и наследование",
        "Ключи", "Связи и правила JOIN", "Справочники", "Межрепозиторные соответствия",
        "Физическая модель", "Архитектурные и бизнес-выводы",
        "Приложение A. Полнота анализа и ограничения доказательности",
        "Приложение B. Неоднозначности и вопросы для уточнения",
        "Приложение C. Технические доказательства и provenance",
    ]
    path.write_text("\n\n".join(f"# {h}\n\nТест." for h in headings), encoding="utf-8")
    return path


def test_service_requires_concrete_revision(tmp_path: Path) -> None:
    service = ReportService(ReportingServiceConfig(api_url="http://knowledge-api.test", runs_root=tmp_path / "runs"))
    with pytest.raises(ValueError, match="revision_id"):
        service.create_run({"system_id":"client-profile","profile":"data-model-report/v1","mode":"prepare"})


def test_service_report_runs_are_independent_from_revision(tmp_path: Path) -> None:
    database = tmp_path / "effective.duckdb"; database.write_bytes(b"fixture")
    service = ReportService(
        ReportingServiceConfig(api_url="http://knowledge-api.test", runs_root=tmp_path / "runs", response_file=_response(tmp_path / "response.md")),
        api_transport=_transport(database),
    )
    payload = {"system_id":"client-profile","revision_id":"rev-1","profile":"data-model-report/v1"}
    prepared = service.create_run({**payload,"mode":"prepare"})
    built = service.create_run({**payload,"mode":"build"})
    assert prepared["run_id"] != built["run_id"]
    assert prepared["source"]["revision_id"] == built["source"]["revision_id"] == "rev-1"
    assert prepared["has_report"] is False
    assert built["has_report"] is True
    assert "Краткий вывод" in service.content(built["run_id"], "report")[0]
    assert service.get_run(built["run_id"])["run_id"] == built["run_id"]
    assert len(service.list_runs()["items"]) == 2
