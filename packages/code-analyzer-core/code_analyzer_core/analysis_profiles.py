from __future__ import annotations

from copy import deepcopy
from pathlib import Path
from typing import Any

import yaml

PROFILE_SUFFIXES = {".yaml", ".yml"}


def _stage_id(item: Any) -> str:
    if isinstance(item, str) and item.strip():
        return item.strip()
    if isinstance(item, dict) and item.get("id"):
        return str(item["id"]).strip()
    raise ValueError(f"Invalid stage entry in analysis profile: {item!r}")


def _merge_unique(base: list[Any], child: list[Any]) -> list[Any]:
    out: list[Any] = []
    for item in [*base, *child]:
        if item not in out:
            out.append(deepcopy(item))
    return out


def _deep_merge(base: Any, child: Any) -> Any:
    if isinstance(base, dict) and isinstance(child, dict):
        result = deepcopy(base)
        for key, value in child.items():
            result[key] = _deep_merge(result[key], value) if key in result else deepcopy(value)
        return result
    return deepcopy(child)


def _merge_stage_lists(base: list[Any], child: list[Any]) -> list[Any]:
    """Merge stages by id while preserving the first declared position.

    A child may override the options of an inherited stage without executing it
    twice. New stages are appended deterministically. This is intentionally a
    small composition model: static profiles remain explicit runtime YAML and
    do not become a plugin language.
    """
    result: list[Any] = [deepcopy(item) for item in base]
    positions = {_stage_id(item): idx for idx, item in enumerate(result)}
    for item in child:
        sid = _stage_id(item)
        if sid in positions:
            idx = positions[sid]
            previous = result[idx]
            if isinstance(previous, dict) and isinstance(item, dict):
                result[idx] = _deep_merge(previous, item)
            else:
                result[idx] = deepcopy(item)
        else:
            positions[sid] = len(result)
            result.append(deepcopy(item))
    return result


def _merge_pipeline(base: dict[str, Any], child: dict[str, Any]) -> dict[str, Any]:
    result = _deep_merge(base, {k: v for k, v in child.items() if k not in {"stages", "final_stages"}})
    result["stages"] = _merge_stage_lists(list(base.get("stages") or []), list(child.get("stages") or []))
    final = _merge_stage_lists(list(base.get("final_stages") or []), list(child.get("final_stages") or []))
    if final:
        result["final_stages"] = final
    else:
        result.pop("final_stages", None)
    return result


def _merge_profiles(base: dict[str, Any], child: dict[str, Any]) -> dict[str, Any]:
    result = deepcopy(base)
    for key, value in child.items():
        if key.startswith("_") or key == "extends":
            continue
        if key == "pipeline":
            result[key] = _merge_pipeline(dict(result.get(key) or {}), dict(value or {}))
        elif key in {"capabilities", "workspace_types"}:
            result[key] = _merge_unique(list(result.get(key) or []), list(value or []))
        elif isinstance(result.get(key), dict) and isinstance(value, dict):
            result[key] = _deep_merge(result[key], value)
        else:
            result[key] = deepcopy(value)
    return result


def _validate_profile_dict(data: Any, *, source: str, as_parent: bool = False) -> dict[str, Any]:
    if not isinstance(data, dict):
        raise ValueError(f"Invalid analysis profile file: {source}")
    profile_id = str(data.get("profile_id") or "").strip()
    fragment_id = str(data.get("fragment_id") or "").strip()
    if as_parent:
        if not profile_id and not fragment_id:
            raise ValueError(f"analysis profile parent must contain profile_id or fragment_id: {source}")
    elif not profile_id:
        raise ValueError(f"analysis profile must contain profile_id: {source}")
    pipeline = data.get("pipeline") or {}
    if not isinstance(pipeline, dict):
        raise ValueError(f"analysis profile pipeline must be an object: {source}")
    stages = pipeline.get("stages") or []
    if stages and not isinstance(stages, list):
        raise ValueError(f"analysis profile pipeline.stages must be a list: {source}")

    evidence_requirements = data.get("evidence_requirements") or []
    if evidence_requirements and not isinstance(evidence_requirements, list):
        raise ValueError(f"analysis profile evidence_requirements must be a list: {source}")
    for item in evidence_requirements:
        if not isinstance(item, dict):
            raise ValueError(f"analysis profile evidence_requirements contains a non-object item: {source}")
        artifact_kind = str(item.get("artifact_kind") or "").strip()
        schema_version = str(item.get("schema_version") or "").strip()
        if not artifact_kind or not schema_version:
            raise ValueError(
                f"analysis profile evidence requirement must contain artifact_kind and schema_version: {source}"
            )

    if stages and evidence_requirements:
        raise ValueError(
            f"analysis profile must use either pipeline.stages or evidence_requirements, not both: {source}"
        )
    if not stages and not evidence_requirements:
        raise ValueError(
            f"analysis profile must contain pipeline.stages or evidence_requirements: {source}"
        )
    data = dict(data)
    data["_profile_source"] = source
    return data


def _resolve_parent_path(value: str, *, child_path: Path) -> Path:
    raw = str(value or "").strip()
    if not raw:
        raise ValueError(f"analysis profile extends entry must not be empty: {child_path}")
    candidate = Path(raw).expanduser()
    if not candidate.is_absolute():
        candidate = child_path.parent / candidate
    if candidate.suffix.lower() not in PROFILE_SUFFIXES:
        candidate = candidate.with_suffix(".yaml")
    candidate = candidate.resolve()
    if not candidate.exists() or not candidate.is_file():
        raise ValueError(f"parent analysis profile file not found: {candidate}")
    return candidate


def _load_profile_path(path: Path, *, stack: tuple[Path, ...], as_parent: bool) -> dict[str, Any]:
    resolved = path.resolve()
    if resolved in stack:
        chain = " -> ".join(str(item) for item in (*stack, resolved))
        raise ValueError(f"analysis profile inheritance cycle: {chain}")
    raw = yaml.safe_load(resolved.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ValueError(f"Invalid analysis profile file: {resolved}")

    extends = raw.get("extends")
    parent_refs: list[str]
    if extends is None:
        parent_refs = []
    elif isinstance(extends, str):
        parent_refs = [extends]
    elif isinstance(extends, list) and all(isinstance(item, str) for item in extends):
        parent_refs = list(extends)
    else:
        raise ValueError(f"analysis profile extends must be a string or list of strings: {resolved}")

    merged: dict[str, Any] = {}
    sources: list[str] = []
    inheritance: list[str] = []
    for parent_ref in parent_refs:
        parent_path = _resolve_parent_path(parent_ref, child_path=resolved)
        parent = _load_profile_path(parent_path, stack=(*stack, resolved), as_parent=True)
        merged = _merge_profiles(merged, parent)
        sources.extend(parent.get("_profile_sources") or [str(parent_path)])
        inheritance.extend(parent.get("_profile_inheritance") or [])
        inheritance.append(str(parent.get("profile_id") or parent.get("fragment_id") or parent_path.stem))

    merged = _merge_profiles(merged, raw)
    # Parent fragments are composition inputs only. Their fragment identity is
    # retained in inheritance metadata but is not part of the executable profile.
    if "fragment_id" not in raw:
        merged.pop("fragment_id", None)
    merged["_profile_source"] = str(resolved)
    merged["_profile_sources"] = _merge_unique(sources, [str(resolved)])
    merged["_profile_inheritance"] = _merge_unique([], inheritance)
    return _validate_profile_dict(merged, source=str(resolved), as_parent=as_parent)


def load_analysis_profile(profile_path: str | Path | None) -> dict[str, Any]:
    """Load and resolve an explicit YAML analysis profile.

    Profiles remain external runtime configuration. `extends` may reference only
    explicit sibling/relative YAML files; there is no package registry or global
    name lookup. Composition resolves before execution and the resulting stage
    sequence is deterministic.
    """
    if profile_path is None or str(profile_path).strip() == "":
        raise ValueError("analysis profile path is required; pass --analysis-profile /path/to/profile.yaml")

    path = Path(str(profile_path).strip()).expanduser()
    if not path.exists():
        raise ValueError(f"analysis profile file not found: {path}")
    if not path.is_file():
        raise ValueError(f"analysis profile must be a YAML file path, got: {path}")
    if path.suffix.lower() not in PROFILE_SUFFIXES:
        raise ValueError(f"analysis profile must be a .yaml/.yml file: {path}")
    return _load_profile_path(path, stack=(), as_parent=False)


def profile_stage_entries(profile: dict[str, Any]) -> list[Any]:
    pipeline = profile.get("pipeline") or {}
    stages = list(pipeline.get("stages") or [])
    final_stages = list(pipeline.get("final_stages") or [])
    entries = [*stages, *final_stages]
    # Validation at resolution time catches malformed profiles early; retaining
    # this check also protects programmatically constructed profiles in tests.
    seen: set[str] = set()
    for item in entries:
        sid = _stage_id(item)
        if sid in seen:
            raise ValueError(f"Duplicate stage after analysis profile composition: {sid}")
        seen.add(sid)
    return entries


def profile_stage_ids(profile: dict[str, Any]) -> list[str]:
    return [_stage_id(item) for item in profile_stage_entries(profile)]


def load_analysis_fragment(fragment_path: str | Path) -> dict[str, Any]:
    """Load an internal composable fragment for a dedicated core operation.

    Fragments remain non-executable through `analyze-java`; this loader is used
    only by explicit internal operations such as foundation artifact creation.
    """
    path = Path(str(fragment_path).strip()).expanduser()
    if not path.exists() or not path.is_file():
        raise ValueError(f"analysis fragment file not found: {path}")
    if path.suffix.lower() not in PROFILE_SUFFIXES:
        raise ValueError(f"analysis fragment must be a .yaml/.yml file: {path}")
    data = _load_profile_path(path, stack=(), as_parent=True)
    if not data.get("fragment_id"):
        raise ValueError(f"analysis fragment must contain fragment_id: {path}")
    return data
