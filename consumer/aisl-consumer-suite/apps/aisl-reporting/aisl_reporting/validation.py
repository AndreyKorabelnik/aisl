from __future__ import annotations

import json
import re
from importlib.resources.abc import Traversable
from typing import Any, Mapping

import jsonschema

from .files import canonical_json

_EVIDENCE_TOKEN = re.compile(r"\[((?:evidence_|ev_)[a-f0-9]{20}|sql_(?:relation|column_usage)_[A-Za-z0-9_:-]+)\]")
_MARKDOWN_HEADING = re.compile(r"^\s{0,3}#{1,6}\s+(.+?)\s*#*\s*$")
_LEADING_NUMBER = re.compile(r"^\s*(?:\d+(?:\.\d+)*[.)]?|[IVXLCDM]+[.)])\s*[-–—:]?\s*", re.IGNORECASE)
_MARKDOWN_DECORATION = re.compile(r"[*_`]+")
_WHITESPACE = re.compile(r"\s+")
_MERMAID_BLOCK = re.compile(
    r"(^|\n)(`{3,}|~{3,})[ \t]*mermaid[ \t]*\r?\n([\s\S]*?)\r?\n\2[ \t]*(?=\n|$)",
    re.IGNORECASE,
)


def _normalize_heading(value: str) -> str:
    value = _MARKDOWN_DECORATION.sub("", str(value or ""))
    value = _LEADING_NUMBER.sub("", value)
    value = value.strip().rstrip(":.;,–—-").strip()
    return _WHITESPACE.sub(" ", value).casefold()


def _observed_headings(report: str) -> list[str]:
    headings: list[str] = []
    for line in report.splitlines():
        match = _MARKDOWN_HEADING.match(line)
        if match:
            headings.append(match.group(1).strip())
    return headings


def _er_diagram_blocks(report: str) -> list[str]:
    blocks: list[str] = []
    for match in _MERMAID_BLOCK.finditer(report):
        body = str(match.group(3) or "").strip()
        lines = [line.strip() for line in body.splitlines() if line.strip() and not line.strip().startswith("%%")]
        if not lines or lines[0].casefold() != "erdiagram":
            continue
        if any(line.casefold() != "erdiagram" for line in lines[1:]):
            blocks.append(body)
    return blocks


def _required_er_layers(dataset: Mapping[str, Any]) -> list[str]:
    if str(dataset.get("profile_id") or "") != "data-model-report/v1":
        return []
    coverage = dataset.get("coverage") if isinstance(dataset.get("coverage"), Mapping) else {}
    if str(coverage.get("report_mode") or "") == "not_observed":
        return []
    diagrams = ((dataset.get("sections") or {}).get("diagrams") or {}) if isinstance(dataset.get("sections"), Mapping) else {}
    layers: list[str] = []
    logical = diagrams.get("logical_er") if isinstance(diagrams, Mapping) else {}
    physical = diagrams.get("physical_er") if isinstance(diagrams, Mapping) else {}
    if isinstance(logical, Mapping) and logical.get("status") == "observed" and logical.get("entities"):
        layers.append("logical_er")
    if isinstance(physical, Mapping) and physical.get("status") == "observed" and physical.get("tables"):
        layers.append("physical_er")
    return layers

def validate_dataset(dataset: Mapping[str, Any], schema_resource: Traversable, *, max_bytes: int) -> dict[str, Any]:
    schema = json.loads(schema_resource.read_text(encoding="utf-8"))
    jsonschema.validate(dict(dataset), schema)
    size = len(canonical_json(dataset).encode("utf-8"))
    if size > max_bytes:
        raise ValueError(f"dataset exceeds profile budget: {size} > {max_bytes} bytes")
    evidence = dict(dataset.get("evidence_index") or ((dataset.get("data_evidence") or {}).get("evidence_ref_index") or {}))
    dangling: list[str] = []

    def visit(value: Any) -> None:
        if isinstance(value, dict):
            for key, item in value.items():
                if key == "evidence_ids" and isinstance(item, list):
                    dangling.extend(str(v) for v in item if str(v) not in evidence)
                else:
                    visit(item)
        elif isinstance(value, list):
            for item in value:
                visit(item)

    for key, value in dataset.items():
        if key not in {"evidence_index", "validation"}:
            visit(value)
    if dangling:
        raise ValueError(f"dataset contains dangling evidence IDs: {sorted(set(dangling))[:10]}")
    return {"valid": True, "dataset_bytes": size, "evidence_count": len(evidence), "dangling_evidence_ids": []}


def validate_markdown_report(
    report: str,
    dataset: Mapping[str, Any],
    required_headings: list[str],
) -> dict[str, Any]:
    """Validate a rendered report without rejecting the generated Markdown.

    Report-quality findings are advisory. Once the renderer returned a non-empty
    report, missing sections, missing journeys and citation inconsistencies are
    surfaced as warnings and recorded in ``report-validation.json``. Dataset and
    schema validation remain strict before rendering.
    """

    observed = _observed_headings(report)
    observed_normalized = {_normalize_heading(value) for value in observed}
    missing = [heading for heading in required_headings if _normalize_heading(heading) not in observed_normalized]

    evidence_index = dict(dataset.get("evidence_index") or {})
    cited = sorted(set(_EVIDENCE_TOKEN.findall(report)))
    unknown = [item for item in cited if item not in evidence_index]
    evidence_required = bool(dataset.get("request", {}).get("include_evidence", True))
    warnings: list[dict[str, Any]] = []

    if missing:
        warnings.append(
            {
                "code": "missing_required_headings",
                "message": f"report is missing required headings: {missing}",
                "details": {"missing": missing, "observed": observed},
            }
        )
    if unknown:
        warnings.append(
            {
                "code": "unknown_evidence_ids",
                "message": f"report cites unknown evidence IDs: {unknown}",
                "details": {"unknown": unknown},
            }
        )
    if evidence_required and evidence_index and not cited:
        warnings.append(
            {
                "code": "missing_evidence_citations",
                "message": "report does not cite any evidence ID",
                "details": {},
            }
        )

    required_er_layers = _required_er_layers(dataset)
    er_blocks = _er_diagram_blocks(report)
    if len(er_blocks) < len(required_er_layers):
        warnings.append(
            {
                "code": "missing_required_er_diagram",
                "message": (
                    "report does not contain the required non-empty ER diagram blocks: "
                    f"required={len(required_er_layers)}, observed={len(er_blocks)}, layers={required_er_layers}"
                ),
                "details": {
                    "required_layers": required_er_layers,
                    "required_count": len(required_er_layers),
                    "observed_count": len(er_blocks),
                },
            }
        )


    return {
        "valid": True,
        "conforms": not warnings,
        "required_heading_count": len(required_headings),
        "observed_heading_count": len(observed),
        "observed_headings": observed,
        "missing_required_headings": missing,
        "evidence_citation_count": len(cited),
        "unknown_evidence_ids": unknown,
        "required_er_diagram_layers": required_er_layers,
        "required_er_diagram_count": len(required_er_layers),
        "observed_er_diagram_count": len(er_blocks),
        "warnings": warnings,
        "errors": [],
    }
