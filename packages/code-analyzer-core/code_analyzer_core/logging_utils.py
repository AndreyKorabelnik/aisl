from __future__ import annotations

import json
import os
import re
import resource
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from rich.console import Console

console = Console()


def process_memory_metrics() -> dict[str, int]:
    """Return bounded process memory metrics without external dependencies."""
    metrics: dict[str, int] = {}
    try:
        usage = resource.getrusage(resource.RUSAGE_SELF)
        # Linux reports KiB; macOS reports bytes. The project runtime is Linux.
        metrics["max_rss_kb"] = int(usage.ru_maxrss)
    except Exception:
        pass
    try:
        status = Path(f"/proc/{os.getpid()}/status").read_text(encoding="utf-8", errors="replace")
        for line in status.splitlines():
            if line.startswith("VmRSS:"):
                metrics["rss_kb"] = int(line.split()[1])
            elif line.startswith("VmHWM:"):
                metrics["high_water_rss_kb"] = int(line.split()[1])
    except Exception:
        pass
    return metrics

_STATUS_MAP = {
    "start": "running",
    "done": "ready",
    "warn": "warning",
    "error": "failed",
}

_SEVERITY_MAP = {
    "start": "info",
    "done": "info",
    "warn": "warning",
    "error": "error",
}

_DENIED_DETAIL_PARTS = ("path", "dir", "file", "token", "secret", "cert", "key", "password")

_PHASE_COPY: dict[str, tuple[str, str, str]] = {
    "analysis": (
        "Статический анализ",
        "Запущен статический анализ репозитория",
        "Статический анализ репозитория завершён",
    ),
    "scan_files": (
        "Поиск файлов",
        "Сканируется состав репозитория и определяется технологический стек",
        "Состав репозитория определён",
    ),
    "config_scan": (
        "Анализ конфигурации",
        "Извлекаются подтверждённые факты из конфигурационных файлов",
        "Анализ конфигурации завершён",
    ),
    "openapi_scan": (
        "Анализ API-контрактов",
        "Извлекаются интерфейсы и схемы из OpenAPI и Swagger",
        "Анализ API-контрактов завершён",
    ),
    "java_structural_scan": (
        "Анализ Java-кода",
        "Извлекаются структурные факты из Java-кода",
        "Структурный анализ Java-кода завершён",
    ),
    "java_system_interaction_enrichment": (
        "Поиск системных взаимодействий",
        "Сопоставляются HTTP-вызовы, конфигурация и границы системы",
        "Факты о системных взаимодействиях подготовлены",
    ),
    "sql_scan": (
        "Анализ SQL",
        "Извлекаются SQL-запросы, обращения к таблицам и преобразования данных",
        "Анализ SQL завершён",
    ),
    "db_schema_scan": (
        "Построение физической модели данных",
        "Извлекаются таблицы, колонки, связи и индексы",
        "Физическая модель данных подготовлена",
    ),
    "java_data_flow_build": (
        "Построение потоков данных",
        "Строятся подтверждённые связи от источников данных к точкам использования",
        "Потоки данных построены",
    ),
    "java_field_flow_build": (
        "Прослеживание атрибутов",
        "Строятся локальные и межпроцедурные связи отдельных атрибутов",
        "Связи атрибутов построены",
    ),
    "java_traceability_build": (
        "Построение трасс",
        "Связываются входные интерфейсы, вызовы и операции с хранилищами",
        "Трассы выполнения построены",
    ),
    "java_persistence_lineage_build": (
        "Прослеживание записи данных",
        "Строятся подтверждённые цепочки от входных данных до хранилищ",
        "Цепочки записи данных построены",
    ),
    "java_data_model_lineage_build": (
        "Построение lineage модели данных",
        "Извлекаются атрибуты, маппинги и преобразования модели данных",
        "Lineage модели данных построен",
    ),
    "declared_value_scan": (
        "Поиск объявленных наборов значений",
        "Извлекаются явно заданные в коде наборы значений без семантической классификации",
        "Объявленные наборы значений извлечены",
    ),
    "declared_value_summary_scan": (
        "Подготовка сводки наборов значений",
        "Формируются компактные сводки явно заданных значений",
        "Сводки наборов значений подготовлены",
    ),
    "system_description_enrichment": (
        "Подготовка фактов для описания системы",
        "Формируется компактный набор подтверждённых фактов о системе",
        "Факты для описания системы подготовлены",
    ),
    "reference_data_fact_base": (
        "Подготовка фактов о справочных значениях",
        "Формируется фактическая база объявленных значений и их использования",
        "Фактическая база объявленных значений подготовлена",
    ),
    "core_output": (
        "Формирование основного результата",
        "Записывается компактный машинный результат анализа",
        "Основной результат анализа записан",
    ),
    "normalize_facts": (
        "Нормализация фактов",
        "Формируются нормализованные индексы доказательной базы",
        "Нормализованные индексы фактов записаны",
    ),
    "normalized_fact_store": (
        "Нормализация фактов",
        "Формируются нормализованные индексы доказательной базы",
        "Нормализованные индексы фактов записаны",
    ),
    "compact_package": (
        "Подготовка навигации по evidence",
        "Формируется компактная навигация по результатам анализа",
        "Навигация по evidence подготовлена",
    ),
    "compact_navigation": (
        "Подготовка навигации по evidence",
        "Формируется компактная навигация по результатам анализа",
        "Навигация по evidence подготовлена",
    ),
    "python_ast_scan": (
        "Анализ Python-кода",
        "Извлекаются структурные факты из Python-кода",
        "Структурный анализ Python-кода завершён",
    ),
}

_METRIC_LABELS = {
    "files found": "файлов",
    "facts": "фактов",
    "config facts": "фактов конфигурации",
    "contracts": "контрактов",
    "schemas": "схем",
    "interfaces": "интерфейсов",
    "relations": "связей",
    "mappers": "мапперов",
    "interfaces_added": "добавленных интерфейсов",
    "composed_calls": "составных вызовов",
    "sql_facts": "SQL-фактов",
    "tables": "таблиц",
    "columns": "колонок",
    "relationships": "связей",
    "flows": "потоков",
    "occurrences": "вхождений атрибутов",
    "edges": "связей атрибутов",
    "field_occurrences": "вхождений атрибутов",
    "field_edges": "связей атрибутов",
    "traces": "трасс",
    "lineages": "цепочек lineage",
    "attributes": "атрибутов",
    "mappings": "маппингов",
    "sets": "наборов значений",
    "entities": "сущностей",
    "physical_assets": "физических объектов",
    "normalized facts": "нормализованных фактов",
    "persisted": "сохранённых фактов",
}


def _safe_details(value: Any, *, depth: int = 0) -> Any:
    """Return a bounded, path-free runtime detail payload."""
    if depth > 3:
        return None
    if value is None or isinstance(value, (bool, int, float)):
        return value
    if isinstance(value, str):
        text = value.replace("\n", " ").replace("\r", " ").strip()
        if text.startswith("/") or ":\\" in text:
            return None
        return text[:300]
    if isinstance(value, list):
        return [item for item in (_safe_details(v, depth=depth + 1) for v in value[:20]) if item is not None]
    if isinstance(value, dict):
        result: dict[str, Any] = {}
        for raw_key, raw_value in list(value.items())[:40]:
            key = str(raw_key)
            lowered = key.lower()
            if any(part in lowered for part in _DENIED_DETAIL_PARTS):
                continue
            safe = _safe_details(raw_value, depth=depth + 1)
            if safe is not None:
                result[key] = safe
        return result
    return str(value)[:200]


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(path)


def _extract_metrics(message: str) -> dict[str, Any]:
    metrics: dict[str, Any] = {}
    for part in message.split(","):
        segment = part.strip()
        match = re.match(r"^([A-Za-z_][A-Za-z0-9_ ]*)\s*[:=]\s*([^,]+)$", segment)
        if not match:
            continue
        key = match.group(1).strip().lower()
        raw_value = match.group(2).strip()
        if raw_value.lower() in {"none", "null"}:
            value: Any = None
        elif raw_value.lower() in {"true", "false"}:
            value = raw_value.lower() == "true"
        elif re.fullmatch(r"-?\d+", raw_value):
            value = int(raw_value)
        elif re.fullmatch(r"-?\d+\.\d+", raw_value):
            value = float(raw_value)
        else:
            continue
        metrics[key] = value
    return metrics


def _metrics_suffix(metrics: dict[str, Any]) -> str:
    parts: list[str] = []
    for key, value in metrics.items():
        if value is None or isinstance(value, bool):
            continue
        label = _METRIC_LABELS.get(key)
        if label:
            parts.append(f"{label}: {value}")
        if len(parts) >= 4:
            break
    return "; ".join(parts)


def _public_copy(stage: str, status: str, technical_message: str, details: dict[str, Any]) -> tuple[str, str]:
    title, running_message, ready_message = _PHASE_COPY.get(
        stage,
        ("Выполнение анализа", "Выполняется этап статического анализа", "Этап статического анализа завершён"),
    )
    normalized_status = _STATUS_MAP.get(status, status)
    if normalized_status == "running":
        return title, running_message
    if normalized_status == "ready":
        suffix = _metrics_suffix(details.get("metrics") or {})
        return title, f"{ready_message}: {suffix}" if suffix else ready_message
    if normalized_status == "warning":
        return title, "Этап завершён с предупреждениями; подробности сохранены в диагностике"
    if normalized_status == "failed":
        return title, "Этап завершился с ошибкой; технические подробности сохранены в диагностике"
    return title, running_message


class RunLogger:
    """Analyzer logger with technical and consumer-facing live streams.

    `analysis_log.jsonl` remains the technical diagnostic log.
    `runtime_events.jsonl` and `runtime_progress.json` are bounded public
    execution views with ready-to-display Russian text. Consumers must display
    `title` and `message` without interpreting technical phase names.
    """

    def __init__(self, out_dir: Path, verbose: bool = False):
        self.out_dir = out_dir
        self.verbose = verbose
        self.out_dir.mkdir(parents=True, exist_ok=True)
        self.path = self.out_dir / "analysis_log.jsonl"
        self.runtime_events_path = self.out_dir / "runtime_events.jsonl"
        self.runtime_progress_path = self.out_dir / "runtime_progress.json"
        self._start_times: dict[str, float] = {}
        self._sequence = 0
        self._started_at = datetime.now(timezone.utc).isoformat()
        self.path.write_text("", encoding="utf-8")
        self.runtime_events_path.write_text("", encoding="utf-8")
        _write_json(self.runtime_progress_path, {
            "format": "framework_runtime_progress",
            "format_version": "1.0",
            "component": "code_analyzer_core",
            "started_at": self._started_at,
            "updated_at": self._started_at,
            "status": "created",
            "phase": "created",
            "events_count": 0,
        })

    def event(self, stage: str, status: str, message: str = "", **data: Any) -> None:
        ts = datetime.now(timezone.utc).isoformat()
        runtime = process_memory_metrics()
        rec = {
            "ts": ts,
            "stage": stage,
            "status": status,
            "message": message,
            "data": data,
            "runtime": runtime,
        }
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")

        self._sequence += 1
        safe_details = _safe_details(data) or {}
        if runtime:
            safe_details["runtime"] = runtime
        metrics = _extract_metrics(message)
        if metrics:
            safe_details["metrics"] = metrics
        title, public_message = _public_copy(stage, status, message, safe_details)
        normalized_status = _STATUS_MAP.get(status, status)
        runtime_event = {
            "format": "framework_runtime_event",
            "format_version": "1.0",
            "component": "code_analyzer_core",
            "ts": ts,
            "seq": self._sequence,
            "event_code": f"code_analyzer_core.{stage}.{normalized_status}",
            "phase": stage,
            "status": normalized_status,
            "severity": _SEVERITY_MAP.get(status, "info"),
            "title": title,
            "message": public_message,
            "details": safe_details,
            "visibility": "user",
        }
        with self.runtime_events_path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(runtime_event, ensure_ascii=False) + "\n")
        _write_json(self.runtime_progress_path, {
            "format": "framework_runtime_progress",
            "format_version": "1.0",
            "component": "code_analyzer_core",
            "started_at": self._started_at,
            "updated_at": ts,
            "status": runtime_event["status"],
            "phase": stage,
            "events_count": self._sequence,
            "latest_event": runtime_event,
            "artifacts": {
                "runtime_events": "diagnostics/runtime_events.jsonl",
                "runtime_progress": "diagnostics/runtime_progress.json",
                "technical_log": "diagnostics/analysis_log.jsonl",
            },
        })

        if status == "start":
            console.print(f"[cyan]▶ {stage}[/cyan] {message}")
        elif status == "done":
            console.print(f"[green]✓ {stage}[/green] {message}")
        elif status == "warn":
            console.print(f"[yellow]⚠ {stage}[/yellow] {message}")
        elif status == "error":
            console.print(f"[red]✗ {stage}[/red] {message}")
        elif self.verbose:
            console.print(f"[dim]{stage}: {status} {message}[/dim]")

    def start(self, stage: str, message: str = "", **data: Any) -> None:
        self._start_times[stage] = time.time()
        self.event(stage, "start", message, **data)

    def done(self, stage: str, message: str = "", **data: Any) -> None:
        elapsed = None
        if stage in self._start_times:
            elapsed = round(time.time() - self._start_times[stage], 3)
        self.event(stage, "done", message, elapsed_sec=elapsed, **data)

    def warn(self, stage: str, message: str = "", **data: Any) -> None:
        self.event(stage, "warn", message, **data)

    def error(self, stage: str, message: str = "", **data: Any) -> None:
        self.event(stage, "error", message, **data)
