from __future__ import annotations

import re
from typing import Any, Mapping


_HEADING = re.compile(r"^(?P<marks>#{1,6})\s+(?P<title>.+?)\s*$", re.MULTILINE)
_ER_TITLE = re.compile(r"\ber[- ]?диаграм", re.IGNORECASE)
_APPENDIX_TITLE = re.compile(r"^приложение\s+[A-DА-Г]\b", re.IGNORECASE)


ER_CORRECTION_PROMPT = """Ты выполняешь единственную корректировку уже сформированного отчёта по модели данных.

Используй только `ER_CORRECTION_DATASET_JSON`. Верни только готовый Markdown-фрагмент раздела `## ER-диаграммы` без вступления и заключения.

Правила:

1. Сформируй ровно столько непустых fenced Mermaid-блоков `erDiagram`, сколько указано в `required_layers`.
2. Для `logical_er` используй только `diagrams.logical_er.entities` и `diagrams.logical_er.relationships`.
3. Для `physical_er` используй только `diagrams.physical_er.tables` и `diagrams.physical_er.relationships`.
4. Наблюдаемые SQL/JOOQ/data-movement связи из `diagrams.observed_usage` не рисуй как declared FK. Их можно кратко перечислить после ER-блоков как наблюдаемые связи использования.
5. Не добавляй сущности, таблицы, атрибуты или рёбра, которых нет в dataset.
6. Если слой имеет `mode=entity_only`, всё равно построй `erDiagram` с сущностями/таблицами без рёбер.
7. Первая непустая строка каждого Mermaid-блока должна быть `erDiagram`.
8. Используй безопасные Mermaid identifiers, но сохраняй точные исходные имена в подписях или комментариях рядом с диаграммой.
9. Не переписывай остальные разделы отчёта.
"""


def correction_dataset(dataset: Mapping[str, Any], required_layers: list[str]) -> dict[str, Any]:
    sections = dataset.get("sections") if isinstance(dataset.get("sections"), Mapping) else {}
    diagrams = sections.get("diagrams") if isinstance(sections, Mapping) else {}
    return {
        "schema_version": "er_correction_dataset/v1",
        "profile_id": dataset.get("profile_id"),
        "report_mode": (dataset.get("coverage") or {}).get("report_mode") if isinstance(dataset.get("coverage"), Mapping) else None,
        "required_layers": list(required_layers),
        "diagrams": {
            layer: dict(diagrams.get(layer) or {})
            for layer in ("logical_er", "physical_er", "observed_usage")
            if isinstance(diagrams, Mapping)
        },
    }


def _section_span(markdown: str) -> tuple[int, int] | None:
    matches = list(_HEADING.finditer(markdown))
    for index, match in enumerate(matches):
        title = match.group("title").strip().strip("`*_ ")
        if not _ER_TITLE.search(title):
            continue
        level = len(match.group("marks"))
        end = len(markdown)
        for following in matches[index + 1 :]:
            if len(following.group("marks")) <= level:
                end = following.start()
                break
        return match.start(), end
    return None


def _normalize_fragment(fragment: str) -> str:
    text = str(fragment or "").strip()
    if not text:
        return ""
    span = _section_span(text)
    if span:
        text = text[span[0] : span[1]].strip()
    elif not text.lstrip().startswith("## ER-диаграммы"):
        text = "## ER-диаграммы\n\n" + text
    return text.rstrip() + "\n"


def merge_er_section(report: str, correction_fragment: str) -> str:
    """Replace only the ER section, or insert it immediately before appendices."""
    fragment = _normalize_fragment(correction_fragment)
    if not fragment:
        raise ValueError("ER correction fragment is empty")
    report_text = str(report or "").rstrip() + "\n"
    span = _section_span(report_text)
    if span:
        prefix = report_text[: span[0]].rstrip()
        suffix = report_text[span[1] :].lstrip("\n")
        return prefix + "\n\n" + fragment + ("\n" + suffix if suffix else "")

    for match in _HEADING.finditer(report_text):
        title = match.group("title").strip().strip("`*_ ")
        if _APPENDIX_TITLE.match(title):
            prefix = report_text[: match.start()].rstrip()
            suffix = report_text[match.start() :].lstrip("\n")
            return prefix + "\n\n" + fragment + "\n" + suffix
    return report_text.rstrip() + "\n\n" + fragment
