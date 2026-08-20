from __future__ import annotations

import re
import ast
from pathlib import Path
from typing import Any

from .helpers import read_text, line_for_offset, snippet_lines

SKIP_PARTS = {".git", "target", "build", ".gradle", ".idea", ".venv", "node_modules", "__pycache__"}
TEXT_SUFFIXES = {".java", ".xml", ".yml", ".yaml", ".properties", ".sql", ".json", ".kt", ".scala", ".py"}


def iter_text_files(repo: Path):
    for p in repo.rglob("*"):
        if not p.is_file() or any(part in SKIP_PARTS for part in p.parts):
            continue
        if p.suffix.lower() in TEXT_SUFFIXES:
            yield p


def find_symbol_files(repo: Path, symbol_name: str) -> list[Path]:
    simple = symbol_name.split(".")[-1]
    direct = list(repo.rglob(f"{simple}.java")) + list(repo.rglob(f"{simple}.py")) + list(repo.rglob(f"{simple}.sql"))
    if direct:
        return [p for p in direct if not any(part in SKIP_PARTS for part in p.parts)]
    out: list[Path] = []
    class_re = re.compile(rf"\b(class|interface|enum|record)\s+{re.escape(simple)}\b")
    for p in iter_text_files(repo):
        try:
            text = read_text(p)
        except Exception:
            continue
        if class_re.search(text[:30000]) or simple in text[:30000]:
            out.append(p)
    return out


def extract_callables(text: str) -> list[dict[str, Any]]:
    method_re = re.compile(
        r"(?P<annotations>(?:\s*@[^\n]+\n)*)"
        r"\s*(?P<modifiers>(?:public|protected|private|static|final|synchronized|abstract|native|default|strictfp)\s+)*"
        r"(?P<return>[A-Za-z_$][A-Za-z0-9_$<>, ?\.\[\]]+)\s+"
        r"(?P<name>[A-Za-z_$][A-Za-z0-9_$]*)\s*\((?P<params>[^)]*)\)\s*"
        r"(?:throws\s+[^\{;]+)?(?P<end>[\{;])",
        re.MULTILINE,
    )
    out: list[dict[str, Any]] = []
    # Python callables first. This is safe for Java text: ast.parse will fail fast.
    try:
        tree = ast.parse(text)
        parents: dict[ast.AST, ast.AST] = {}
        for node in ast.walk(tree):
            for child in ast.iter_child_nodes(node):
                parents[child] = node
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                line = getattr(node, "lineno", 1)
                if isinstance(node, ast.ClassDef):
                    sig = f"class {node.name}"
                    name = node.name
                else:
                    args = [a.arg for a in (list(node.args.posonlyargs) + list(node.args.args) + list(node.args.kwonlyargs))]
                    cls = parents.get(node)
                    prefix = f"{cls.name}." if isinstance(cls, ast.ClassDef) else ""
                    name = f"{prefix}{node.name}"
                    sig = f"{'async ' if isinstance(node, ast.AsyncFunctionDef) else ''}def {name}({', '.join(args)})"
                decorators = []
                if hasattr(node, "decorator_list"):
                    for d in getattr(node, "decorator_list") or []:
                        try:
                            decorators.append("@" + ast.unparse(d))
                        except Exception:
                            pass
                out.append({"name": name, "line": line, "signature": sig[:500], "annotations": decorators[:10], "language": "python"})
    except SyntaxError:
        pass

    for m in method_re.finditer(text):
        name = m.group("name")
        if name in {"if", "for", "while", "switch", "catch", "return", "new"}:
            continue
        line = line_for_offset(text, m.start())
        signature = " ".join(text[m.start():m.end()].strip().split())
        if signature.endswith(("{", ";")):
            signature = signature[:-1].strip()
        annotations = [x.strip() for x in (m.group("annotations") or "").splitlines() if x.strip().startswith("@")]
        out.append({"name": name, "line": line, "signature": signature[:500], "annotations": annotations[:10], "language": "java"})
    seen = set(); unique = []
    for item in out:
        key = (item["name"], item["line"])
        if key not in seen:
            seen.add(key); unique.append(item)
    return unique


def find_matching_brace(text: str, open_pos: int) -> int:
    depth = 0; in_str = False; esc = False; quote = ""
    for i in range(open_pos, len(text)):
        ch = text[i]
        if in_str:
            if esc: esc = False
            elif ch == "\\": esc = True
            elif ch == quote: in_str = False
            continue
        if ch in {'"', "'"}:
            in_str = True; quote = ch; continue
        if ch == "{": depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return i
    return min(len(text), open_pos + 12000)


def extract_callable_body(text: str, callable_name: str) -> dict[str, Any] | None:
    # Python source: use AST line ranges. Supports both "func" and "Class.func" tokens.
    try:
        tree = ast.parse(text)
        parents: dict[ast.AST, ast.AST] = {}
        for node in ast.walk(tree):
            for child in ast.iter_child_nodes(node):
                parents[child] = node
        lines = text.splitlines()
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                if isinstance(node, ast.ClassDef):
                    full_name = node.name
                else:
                    cls = parents.get(node)
                    full_name = f"{cls.name}.{node.name}" if isinstance(cls, ast.ClassDef) else node.name
                if callable_name not in {full_name, getattr(node, "name", "")} :
                    continue
                start = int(getattr(node, "lineno", 1))
                end = int(getattr(node, "end_lineno", start))
                return {"line_start": start, "line_end": end, "snippet": "\n".join(lines[start-1:end])}
    except SyntaxError:
        pass

    method_re = re.compile(rf"(?:public|protected|private)?\s+[A-Za-z0-9_<>, ?.\[\].]+\s+{re.escape(callable_name)}\s*\([^)]*\)\s*(?:throws [^{{]+)?\{{", re.DOTALL)
    m = method_re.search(text)
    if not m:
        return None
    end = find_matching_brace(text, m.end() - 1)
    return {
        "line_start": line_for_offset(text, m.start()),
        "line_end": line_for_offset(text, end),
        "snippet": text[m.start():end + 1],
    }


def search_repo(repo: Path, token: str, *, max_results: int = 30, context: int = 2) -> list[dict[str, Any]]:
    q = token.lower()
    hits: list[dict[str, Any]] = []
    for p in iter_text_files(repo):
        if len(hits) >= max_results:
            break
        try:
            text = read_text(p)
        except Exception:
            continue
        idx = text.lower().find(q)
        if idx < 0:
            continue
        line = line_for_offset(text, idx)
        hits.append({"file": str(p), "line": line, "snippet": snippet_lines(text, line, radius=context)})
    return hits



def _is_inside_repo(repo: Path, path: Path) -> bool:
    try:
        path.resolve().relative_to(repo.resolve())
        return True
    except Exception:
        return False


def source_open_bundle(
    repo: Path,
    file_or_token: str,
    *,
    line: int | None = None,
    start_line: int | None = None,
    end_line: int | None = None,
    context: int = 8,
    max_chars: int = 20000,
    max_candidates: int = 20,
) -> dict[str, Any]:
    """Open a narrow source slice by file path/name and optional line range.

    This is the iterative follow-up counterpart of source_inspection_bundle.
    The LLM may use it after a first source-inspect reveals that the answer moved
    to a concrete file/line, converter, mapper, or DAO implementation snippet.
    It is deliberately read-only and refuses paths outside the analyzed repo.
    """
    token = (file_or_token or "").strip()
    if not token:
        return {
            "token": token,
            "status": "missing_file_or_token",
            "policy": "read_only_targeted_source_inspection",
        }

    candidates: list[Path] = []
    raw = Path(token)
    direct = raw if raw.is_absolute() else repo / raw
    if direct.exists() and direct.is_file() and _is_inside_repo(repo, direct):
        candidates = [direct]
    else:
        normalized = token.replace("\\", "/")
        for p in iter_text_files(repo):
            rel = str(p.relative_to(repo)).replace("\\", "/")
            if rel == normalized or rel.endswith(normalized) or p.name == token:
                candidates.append(p)
                if len(candidates) >= max_candidates:
                    break

    if not candidates:
        return {
            "token": token,
            "status": "file_not_resolved",
            "candidate_files": [],
            "search_hits": search_repo(repo, token, max_results=max_candidates, context=context),
            "follow_up_hint": "Use source-inspect <Class.method> or search <token> if the exact file path is unknown.",
            "policy": "read_only_targeted_source_inspection",
        }

    if len(candidates) > 1:
        return {
            "token": token,
            "status": "ambiguous_file",
            "candidate_files": [str(p) for p in candidates[:max_candidates]],
            "follow_up_hint": "Repeat source-open with a more specific relative path from candidate_files.",
            "policy": "read_only_targeted_source_inspection",
        }

    path = candidates[0]
    text = read_text(path)
    lines = text.splitlines()
    total = len(lines)
    if start_line is not None or end_line is not None:
        start = max(1, int(start_line or 1))
        end = min(total, int(end_line or total))
    elif line is not None:
        center = max(1, int(line))
        start = max(1, center - max(0, context))
        end = min(total, center + max(0, context))
    else:
        start = 1
        end = total

    if end < start:
        start, end = end, start
    snippet = "\n".join(lines[start - 1:end])
    truncated = len(snippet) > max_chars
    return {
        "token": token,
        "status": "opened",
        "file": str(path),
        "relative_file": str(path.relative_to(repo)),
        "line_start": start,
        "line_end": end,
        "total_lines": total,
        "snippet": snippet[:max_chars],
        "truncated": truncated,
        "next_step_hint": "If this snippet points to another converter/helper/DAO/mapper, request another targeted source-inspect/source-open/find-implementations call for that concrete target.",
        "policy": "read_only_targeted_source_inspection",
    }


def find_possible_implementations(repo: Path, target: str, *, max_results: int = 20, context: int = 4) -> list[dict[str, Any]]:
    """Best-effort source search for a Java implementation of Interface.method.

    This deliberately returns snippets, not conclusions.  It is for controlled
    LLM source inspection when analyzer evidence stops at a custom DAO boundary.
    """
    target = (target or "").strip()
    if "." in target:
        type_name, method_name = target.rsplit(".", 1)
    else:
        type_name, method_name = target, ""
    simple_type = type_name.split(".")[-1]
    hits: list[dict[str, Any]] = []
    impl_re = re.compile(rf"\b(class|interface)\s+[A-Za-z_][A-Za-z0-9_]*[^{{;\n]]*\b(implements|extends)\s+[^{{;\n]]*\b{re.escape(simple_type)}\b", re.MULTILINE)
    method_re = re.compile(rf"\b{re.escape(method_name)}\s*\(") if method_name else None
    for p in iter_text_files(repo):
        if len(hits) >= max_results:
            break
        try:
            text = read_text(p)
        except Exception:
            continue
        low = text.lower()
        candidate = simple_type.lower() in low or (method_name and method_name.lower() in low)
        if not candidate:
            continue
        line = 1
        observations: list[str] = []
        mi = impl_re.search(text)
        if mi:
            line = line_for_offset(text, mi.start())
            observations.append("implements_or_extends_target_type")
        if method_re:
            mm = method_re.search(text)
            if mm:
                line = line_for_offset(text, mm.start())
                observations.append("contains_target_method")
        if simple_type.lower() in low:
            observations.append("mentions_target_type")
        if not observations:
            continue
        hits.append({
            "file": str(p),
            "line": line,
            "observed_match_kinds": observations,
            "snippet": snippet_lines(text, line, radius=context),
        })
    return sorted(hits, key=lambda x: (str(x.get("file") or ""), int(x.get("line") or 0)))[:max_results]


def source_inspection_bundle(repo: Path, token: str, *, max_results: int = 20, context: int = 4, max_chars: int = 20000) -> dict[str, Any]:
    """Return a compact source-inspection bundle for a token/symbol/method.

    Used by prompts as a read-only targeted inspection step.  It combines symbol
    discovery, callable body extraction when token looks like Class.method, and
    source search hits.
    """
    token = (token or "").strip()
    symbol_name = token.rsplit(".", 1)[0] if "." in token else token
    callable_name = token.rsplit(".", 1)[1] if "." in token else ""
    symbol_files = find_symbol_files(repo, symbol_name)[:max_results] if symbol_name else []
    callables: list[dict[str, Any]] = []
    snippets: list[dict[str, Any]] = []
    for f in symbol_files[:5]:
        try:
            text = read_text(f)
        except Exception:
            continue
        file_callables = extract_callables(text)
        callables.extend({**c, "file": str(f)} for c in file_callables[:30])
        if callable_name:
            body = extract_callable_body(text, callable_name)
            if body:
                sn = str(body.get("snippet") or "")[:max_chars]
                snippets.append({"file": str(f), "callable": callable_name, "line_start": body.get("line_start"), "line_end": body.get("line_end"), "snippet": sn})
    return {
        "token": token,
        "symbol_candidates": [str(p) for p in symbol_files[:max_results]],
        "callables": callables[:max_results],
        "callable_snippets": snippets[:5],
        "search_hits": search_repo(repo, token, max_results=max_results, context=context) if token else [],
        "policy": "read_only_targeted_source_inspection",
    }
