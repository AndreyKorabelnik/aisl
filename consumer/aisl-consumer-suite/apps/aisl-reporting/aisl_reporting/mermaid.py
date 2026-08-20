from __future__ import annotations

import re
from dataclasses import dataclass

_MERMAID_FENCE = re.compile(
    r"(^|\n)(`{3,}|~{3,})[ \t]*mermaid[ \t]*\r?\n([\s\S]*?)\r?\n\2[ \t]*(?=\n|$)",
    re.IGNORECASE,
)
_FLOW_NODE = re.compile(r"\b([A-Za-z_][A-Za-z0-9_-]*)\[([^\]\n]+)\]")
_FLOW_EDGE_LABEL = re.compile(r"(-->|---|-.->|==>)\s+\|([^|\n]+)\|\s*")
_ER_RELATION = re.compile(r"^(\s*)(\S+)\s+([|}{o.\\-]+)\s+(\S+)\s*:\s*(.+?)\s*$")
_SAFE_ER_ID = re.compile(r"^[A-Za-z_][A-Za-z0-9_-]*$")


@dataclass(frozen=True)
class MermaidNormalization:
    block_count: int
    changed_block_count: int

    def to_dict(self) -> dict[str, int]:
        return {
            "block_count": self.block_count,
            "changed_block_count": self.changed_block_count,
        }


def _quote_flow_label(value: str) -> str:
    stripped = value.strip()
    if len(stripped) >= 2 and (
        (stripped[0] == stripped[-1] == '"')
        or (stripped[0] == stripped[-1] == "'")
        or stripped.startswith("`\"")
    ):
        return value
    escaped = stripped.replace('"', '#quot;')
    return f'"{escaped}"'


def _quote_er_entity(value: str) -> str:
    stripped = value.strip()
    if len(stripped) >= 2 and stripped[0] == stripped[-1] == '"':
        return stripped
    if _SAFE_ER_ID.fullmatch(stripped):
        return stripped
    return '"' + stripped.replace('"', '#quot;') + '"'


def _normalize_flowchart(source: str) -> str:
    normalized = _FLOW_EDGE_LABEL.sub(lambda match: f"{match.group(1)}|{match.group(2).strip()}| ", source)

    def replace_node(match: re.Match[str]) -> str:
        return f"{match.group(1)}[{_quote_flow_label(match.group(2))}]"

    return _FLOW_NODE.sub(replace_node, normalized)


def _normalize_er(source: str) -> str:
    lines: list[str] = []
    for line in source.splitlines():
        match = _ER_RELATION.match(line)
        if not match:
            lines.append(line)
            continue
        indent, left, relation, right, label = match.groups()
        lines.append(
            f"{indent}{_quote_er_entity(left)} {relation} {_quote_er_entity(right)} : {label}"
        )
    return "\n".join(lines)


def normalize_mermaid_source(source: str) -> str:
    text = str(source or "").replace("\r\n", "\n").strip()
    first = next((line.strip() for line in text.splitlines() if line.strip()), "")
    if first.startswith(("flowchart ", "graph ")):
        return _normalize_flowchart(text)
    if first == "erDiagram":
        return _normalize_er(text)
    return text


def normalize_mermaid_markdown(markdown: str) -> tuple[str, MermaidNormalization]:
    block_count = 0
    changed = 0

    def replace(match: re.Match[str]) -> str:
        nonlocal block_count, changed
        block_count += 1
        prefix, fence, source = match.groups()
        normalized = normalize_mermaid_source(source)
        original = source.replace("\r\n", "\n").strip()
        if normalized != original:
            changed += 1
        return f"{prefix}{fence}mermaid\n{normalized}\n{fence}"

    result = _MERMAID_FENCE.sub(replace, str(markdown or ""))
    return result, MermaidNormalization(block_count=block_count, changed_block_count=changed)
