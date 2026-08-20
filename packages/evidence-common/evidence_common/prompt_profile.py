from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any
import json
import re

import yaml

from .files import sha256_text

PROMPT_STAGE_SEPARATOR = "\n\n---\n\n"
SUPPORTED_PROMPT_STAGES = ("initial", "continuation", "report")
GENERATED_PROFILE_SCHEMA_CONTRACT = "@generated/profile_schema_contract"
PROFILE_SCHEMA_RELATIVE_PATH = Path("schemas") / "structured_result.schema.json"


class PromptProfileError(ValueError):
    """Raised when an analysis prompt profile is misconfigured."""


@dataclass(frozen=True)
class PromptFragment:
    stage: str
    declared_path: str
    resolved_path: Path
    text: str
    chars: int
    sha256: str
    generated: bool = False


@dataclass(frozen=True)
class PromptProfile:
    profile_dir: Path
    profile_yaml: Path
    profile_id: str
    profile_version: str | None
    prompt_assembly: dict[str, list[str]]
    raw: dict[str, Any]


@dataclass(frozen=True)
class PromptProfileIndexEntry:
    profile_id: str
    profile_dir: Path
    profile_yaml: Path
    profile_version: str | None
    profile_group: str | None = None


def _profile_group_from_relative(profile_yaml: Path, root: Path) -> str | None:
    try:
        rel = profile_yaml.relative_to(root)
    except ValueError:
        return None
    parts = rel.parts
    if len(parts) >= 2:
        return parts[0]
    return None


def _is_under_shared(profile_yaml: Path, root: Path) -> bool:
    try:
        rel = profile_yaml.relative_to(root)
    except ValueError:
        return False
    return bool(rel.parts) and rel.parts[0] == "shared"


def resolve_prompt_profile_dir(profile_dir: Path) -> Path:
    """Resolve and validate an explicit prompt profile directory.

    No legacy fallback is performed: the supplied path must already point to a
    runnable profile directory or directly to a profile.yaml file. This keeps the
    profile identity stable when prompt packs use grouped physical layouts such
    as code/<profile_id>, sdd/<profile_id>, support/<profile_id>.
    """
    raw = Path(profile_dir)
    path = raw.resolve()
    if path.is_file() and path.name == "profile.yaml":
        path = path.parent
    profile_yaml = path / "profile.yaml"
    if not path.exists() or not path.is_dir():
        raise PromptProfileError(f"Prompt profile directory not found: {raw}")
    if not profile_yaml.exists() or not profile_yaml.is_file():
        raise PromptProfileError(f"Prompt profile directory does not contain profile.yaml: {path}")
    return path


def discover_prompt_profile_dirs(prompt_root: Path, *, exclude_shared: bool = True) -> list[Path]:
    """Discover runnable prompt profile directories recursively under a prompt root.

    The physical grouping directories are packaging/layout details only. Runnable
    profiles are identified by profile.yaml files. The shared/ tree is excluded
    by default because it contains reusable fragments, not runnable profiles.
    """
    root = Path(prompt_root).resolve()
    if not root.exists() or not root.is_dir():
        raise PromptProfileError(f"Prompt root directory not found: {prompt_root}")
    profile_yamls = sorted(root.rglob("profile.yaml"), key=lambda p: str(p.relative_to(root)))
    dirs: list[Path] = []
    for profile_yaml in profile_yamls:
        if exclude_shared and _is_under_shared(profile_yaml, root):
            continue
        dirs.append(profile_yaml.parent.resolve())
    return dirs


def build_prompt_profile_index(prompt_root: Path, *, exclude_shared: bool = True) -> dict[str, PromptProfileIndexEntry]:
    """Build a deterministic profile_id -> profile directory index.

    Duplicate profile_id values are a hard error because profile_id is the
    canonical runtime identity and physical groups are not part of the id.
    """
    root = Path(prompt_root).resolve()
    index: dict[str, PromptProfileIndexEntry] = {}
    duplicates: dict[str, list[Path]] = {}
    for profile_dir in discover_prompt_profile_dirs(root, exclude_shared=exclude_shared):
        profile = load_prompt_profile(profile_dir)
        entry = PromptProfileIndexEntry(
            profile_id=profile.profile_id,
            profile_dir=profile.profile_dir,
            profile_yaml=profile.profile_yaml,
            profile_version=profile.profile_version,
            profile_group=_profile_group_from_relative(profile.profile_yaml, root),
        )
        if profile.profile_id in index:
            duplicates.setdefault(profile.profile_id, [index[profile.profile_id].profile_yaml]).append(profile.profile_yaml)
        else:
            index[profile.profile_id] = entry
    if duplicates:
        lines = ["Duplicate prompt profile_id values found during recursive discovery:"]
        for profile_id in sorted(duplicates):
            paths = ", ".join(str(p) for p in duplicates[profile_id])
            lines.append(f"- {profile_id}: {paths}")
        raise PromptProfileError("\n".join(lines))
    return dict(sorted(index.items(), key=lambda kv: kv[0]))


def list_prompt_profiles(prompt_root: Path, *, exclude_shared: bool = True) -> list[PromptProfileIndexEntry]:
    """Return discovered runnable prompt profiles in deterministic profile_id order."""
    return list(build_prompt_profile_index(prompt_root, exclude_shared=exclude_shared).values())


def validate_prompt_profile_fragment_paths(profile_dir: Path) -> dict[str, Any]:
    """Validate that all declared prompt_assembly fragments resolve for a profile.

    Fragments are resolved relative to the concrete profile.yaml directory, so
    grouped layouts can safely use paths such as ../../shared/<fragment>.md.
    Generated fragments are validated through their generated-contract loader.
    """
    profile = load_prompt_profile(resolve_prompt_profile_dir(profile_dir))
    stages: dict[str, Any] = {}
    for stage in sorted(profile.prompt_assembly):
        _, fragments = load_prompt_fragments(profile.profile_dir, stage)
        stages[stage] = [
            {
                "declared_path": fragment.declared_path,
                "resolved_path": str(fragment.resolved_path),
                "generated": fragment.generated,
                "chars": fragment.chars,
                "sha256": fragment.sha256,
            }
            for fragment in fragments
        ]
    return {
        "profile_id": profile.profile_id,
        "profile_dir": str(profile.profile_dir),
        "profile_yaml": str(profile.profile_yaml),
        "stages": stages,
    }


def _quote_generated_tokens_for_yaml(text: str) -> str:
    """Allow profile.yaml to use unquoted @generated/... entries.

    Plain scalars starting with @ are not valid YAML, but the prompt profile
    contract intentionally uses a human-readable marker such as:

      - @generated/profile_schema_contract

    This preprocessor quotes only list items that are exactly generated tokens,
    preserving all other YAML content.
    """
    return re.sub(
        r"^(?P<prefix>\s*-\s*)(?P<token>@generated/[A-Za-z0-9_.-]+)(?P<suffix>\s*(?:#.*)?$)",
        lambda m: f"{m.group('prefix')}\"{m.group('token')}\"{m.group('suffix')}",
        text,
        flags=re.MULTILINE,
    )


def _load_yaml(path: Path) -> dict[str, Any]:
    if not path.exists() or not path.is_file():
        raise PromptProfileError(f"Prompt profile file not found: {path}")
    try:
        raw_text = path.read_text(encoding="utf-8")
        data = yaml.safe_load(_quote_generated_tokens_for_yaml(raw_text))
    except Exception as exc:
        raise PromptProfileError(f"Cannot parse prompt profile YAML: {path}: {exc}") from exc
    if not isinstance(data, dict):
        raise PromptProfileError(f"Prompt profile YAML must contain an object: {path}")
    return data


def load_prompt_profile(profile_dir: Path) -> PromptProfile:
    """Load and validate a prompt profile directory.

    The profile must use the prompt_assembly contract. Legacy `prompts:` blocks
    are intentionally not supported. Paths are resolved from the concrete
    profile.yaml directory, so grouped prompt layouts do not change profile ids.
    """
    profile_dir = resolve_prompt_profile_dir(profile_dir)
    profile_yaml = profile_dir / "profile.yaml"
    data = _load_yaml(profile_yaml)

    profile_id = str(data.get("profile_id") or profile_dir.name).strip()
    if not profile_id:
        raise PromptProfileError(f"profile_id is empty in {profile_yaml}")
    version_raw = data.get("profile_version") or data.get("version")
    profile_version = str(version_raw).strip() if version_raw is not None else None

    assembly = data.get("prompt_assembly")
    if assembly is None:
        if "prompts" in data:
            raise PromptProfileError(
                f"profile_id={profile_id}: legacy 'prompts' block is not supported. "
                "Use required 'prompt_assembly' with initial, continuation and report stages."
            )
        raise PromptProfileError(
            f"profile_id={profile_id}: missing required 'prompt_assembly' section in {profile_yaml}"
        )
    if not isinstance(assembly, dict):
        raise PromptProfileError(f"profile_id={profile_id}: prompt_assembly must be an object in {profile_yaml}")

    normalized: dict[str, list[str]] = {}
    for stage, items in assembly.items():
        if stage not in SUPPORTED_PROMPT_STAGES:
            raise PromptProfileError(
                f"profile_id={profile_id}: unsupported prompt_assembly.{stage} in {profile_yaml}; "
                f"expected one of {list(SUPPORTED_PROMPT_STAGES)}"
            )
        if not isinstance(items, list) or not items:
            raise PromptProfileError(f"profile_id={profile_id}: prompt_assembly.{stage} must be a non-empty list in {profile_yaml}")
        stage_items: list[str] = []
        for idx, item in enumerate(items):
            if not isinstance(item, str) or not item.strip():
                raise PromptProfileError(
                    f"profile_id={profile_id}: prompt_assembly.{stage}[{idx}] must be a non-empty string in {profile_yaml}"
                )
            stage_items.append(item.strip())
        normalized[stage] = stage_items
    if not normalized:
        raise PromptProfileError(f"profile_id={profile_id}: prompt_assembly must define at least one stage in {profile_yaml}")

    return PromptProfile(
        profile_dir=profile_dir,
        profile_yaml=profile_yaml,
        profile_id=profile_id,
        profile_version=profile_version,
        prompt_assembly=normalized,
        raw=data,
    )


def _fragment_error(*, profile: PromptProfile, stage: str, declared_path: str, resolved_path: Path, reason: str) -> PromptProfileError:
    return PromptProfileError(
        "Prompt assembly failed.\n"
        f"profile_id: {profile.profile_id}\n"
        f"stage: {stage}\n"
        f"fragment: {declared_path}\n"
        f"resolved_path: {resolved_path}\n"
        f"reason: {reason}"
    )


def _generated_fragment_error(*, profile: PromptProfile, stage: str, schema_path: Path, reason: str) -> PromptProfileError:
    return PromptProfileError(
        "Generated prompt fragment assembly failed.\n"
        f"profile_id: {profile.profile_id}\n"
        f"stage: {stage}\n"
        f"generated_fragment: {GENERATED_PROFILE_SCHEMA_CONTRACT}\n"
        f"schema_path: {schema_path}\n"
        f"reason: {reason}"
    )


def _load_profile_schema(profile: PromptProfile, stage: str) -> tuple[Path, dict[str, Any]]:
    schema_path = (profile.profile_dir / PROFILE_SCHEMA_RELATIVE_PATH).resolve()
    if not schema_path.exists() or not schema_path.is_file():
        raise _generated_fragment_error(
            profile=profile,
            stage=stage,
            schema_path=schema_path,
            reason="schema file does not exist for generated profile schema contract",
        )
    try:
        raw = schema_path.read_text(encoding="utf-8")
        schema = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise _generated_fragment_error(
            profile=profile,
            stage=stage,
            schema_path=schema_path,
            reason=f"schema is not valid JSON: {exc}",
        ) from exc
    except Exception as exc:
        raise _generated_fragment_error(
            profile=profile,
            stage=stage,
            schema_path=schema_path,
            reason=f"cannot read schema: {exc}",
        ) from exc
    if not isinstance(schema, dict):
        raise _generated_fragment_error(
            profile=profile,
            stage=stage,
            schema_path=schema_path,
            reason="schema root must be a JSON object",
        )
    return schema_path, schema


def _json_type(spec: Any) -> str:
    if not isinstance(spec, dict):
        return "unknown"
    if "const" in spec:
        return f"const {spec['const']!r}"
    value = spec.get("type")
    if isinstance(value, list):
        return " | ".join(str(x) for x in value)
    if isinstance(value, str):
        return value
    if "$ref" in spec:
        return str(spec["$ref"])
    if "enum" in spec:
        return "enum"
    return "object"


def _enum_values(spec: Any) -> list[Any]:
    if isinstance(spec, dict) and isinstance(spec.get("enum"), list):
        return spec["enum"]
    return []


def _resolve_ref(schema: dict[str, Any], ref: str) -> dict[str, Any] | None:
    if not ref.startswith("#/"):
        return None
    current: Any = schema
    for raw_part in ref[2:].split("/"):
        part = raw_part.replace("~1", "/").replace("~0", "~")
        if not isinstance(current, dict) or part not in current:
            return None
        current = current[part]
    return current if isinstance(current, dict) else None


def _finding_schema(schema: dict[str, Any]) -> dict[str, Any]:
    defs = schema.get("$defs")
    if isinstance(defs, dict) and isinstance(defs.get("finding"), dict):
        return defs["finding"]
    properties = schema.get("properties")
    if isinstance(properties, dict):
        findings = properties.get("findings")
        if isinstance(findings, dict):
            items = findings.get("items")
            if isinstance(items, dict):
                if isinstance(items.get("$ref"), str):
                    resolved = _resolve_ref(schema, items["$ref"])
                    if resolved is not None:
                        return resolved
                if items.get("type") == "object" or "properties" in items:
                    return items
    return {}


def _resolved_spec(schema: dict[str, Any], spec: Any) -> dict[str, Any]:
    """Resolve a local JSON Schema reference while preserving sibling keywords."""
    if not isinstance(spec, dict):
        return {}
    ref = spec.get("$ref")
    if not isinstance(ref, str):
        return spec
    resolved = _resolve_ref(schema, ref)
    if resolved is None:
        return spec
    if len(spec) == 1:
        return resolved
    merged = dict(resolved)
    merged.update({key: value for key, value in spec.items() if key != "$ref"})
    return merged


def _properties(spec: Any) -> dict[str, Any]:
    if isinstance(spec, dict) and isinstance(spec.get("properties"), dict):
        return spec["properties"]
    return {}


def _required(spec: Any) -> list[str]:
    if isinstance(spec, dict) and isinstance(spec.get("required"), list):
        return [str(x) for x in spec["required"]]
    return []


def _additional_policy(spec: Any) -> str | None:
    if not isinstance(spec, dict) or "additionalProperties" not in spec:
        return None
    value = spec.get("additionalProperties")
    if value is False:
        return "additionalProperties: false"
    if value is True:
        return "additionalProperties: true"
    if isinstance(value, dict):
        return "additionalProperties: schema-defined"
    return f"additionalProperties: {value!r}"


def _description_lines(name: str, spec: Any, *, indent: str = "  ") -> list[str]:
    lines: list[str] = []
    if not isinstance(spec, dict):
        return lines
    description = spec.get("description")
    if isinstance(description, str) and description.strip():
        lines.append(f"{indent}- {name}: {description.strip()}")
    for key in sorted(spec):
        if key.startswith("x_") or key.startswith("x-"):
            value = spec[key]
            if isinstance(value, (str, int, float, bool)):
                lines.append(f"{indent}- {name}.{key}: {value}")
            else:
                try:
                    encoded = json.dumps(value, ensure_ascii=False, sort_keys=True)
                except TypeError:
                    encoded = str(value)
                lines.append(f"{indent}- {name}.{key}: {encoded}")
    return lines


def _format_list(values: list[Any]) -> str:
    if not values:
        return "none specified"
    return ", ".join(str(v) for v in values)


def _field_summary(name: str, spec: dict[str, Any], required_fields: set[str]) -> str:
    markers: list[str] = []
    if name in required_fields:
        markers.append("required")
    type_text = _json_type(spec)
    markers.append(f"type={type_text}")
    enum_values = _enum_values(spec)
    if enum_values:
        markers.append("enum=[" + _format_list(enum_values) + "]")
    if "minimum" in spec or "maximum" in spec:
        markers.append(f"range={spec.get('minimum', '-inf')}..{spec.get('maximum', '+inf')}")
    return f"- `{name}`: " + "; ".join(markers)



def _conditional_attribute_requirements(finding: dict[str, Any]) -> dict[str, list[str]]:
    """Extract per-finding-type required attribute fields from common if/then schemas."""
    result: dict[str, list[str]] = {}
    clauses = finding.get("allOf") if isinstance(finding.get("allOf"), list) else []
    for clause in clauses:
        if not isinstance(clause, dict):
            continue
        condition = clause.get("if") if isinstance(clause.get("if"), dict) else {}
        condition_properties = _properties(condition)
        finding_type_spec = condition_properties.get("finding_type")
        finding_types: list[str] = []
        if isinstance(finding_type_spec, dict):
            if isinstance(finding_type_spec.get("const"), str):
                finding_types = [finding_type_spec["const"]]
            elif isinstance(finding_type_spec.get("enum"), list):
                finding_types = [str(value) for value in finding_type_spec["enum"]]
        then = clause.get("then") if isinstance(clause.get("then"), dict) else {}
        attributes_spec = _properties(then).get("attributes")
        required: list[str] = []
        if isinstance(attributes_spec, dict):
            required.extend(_required(attributes_spec))
            for nested in attributes_spec.get("allOf") if isinstance(attributes_spec.get("allOf"), list) else []:
                required.extend(_required(nested))
        if finding_types and required:
            deduped = list(dict.fromkeys(required))
            for finding_type in finding_types:
                result[finding_type] = deduped
    return result


def _collect_local_refs(value: Any, *, out: list[str] | None = None) -> list[str]:
    refs = out if out is not None else []
    if isinstance(value, dict):
        ref = value.get("$ref")
        if isinstance(ref, str) and ref.startswith("#/$defs/") and ref not in refs:
            refs.append(ref)
        for item in value.values():
            _collect_local_refs(item, out=refs)
    elif isinstance(value, list):
        for item in value:
            _collect_local_refs(item, out=refs)
    return refs


def _render_nested_contract(schema: dict[str, Any], ref: str) -> list[str]:
    spec = _resolve_ref(schema, ref)
    if not isinstance(spec, dict):
        return []
    name = ref.rsplit("/", 1)[-1]
    properties = _properties(spec)
    required = set(_required(spec))
    lines = [f"### Nested object `{name}`", f"- referenced as: `{ref}`"]
    policy = _additional_policy(spec)
    if policy:
        lines.append(f"- {policy}")
    lines.append(f"- required fields: {_format_list(list(required))}")
    for field_name, field_spec in properties.items():
        if not isinstance(field_spec, dict):
            continue
        lines.append(_field_summary(field_name, field_spec, required))
        resolved = _resolved_spec(schema, field_spec)
        items = resolved.get("items") if isinstance(resolved.get("items"), dict) else None
        enum_values = _enum_values(resolved)
        if enum_values:
            lines.append(f"  - `{field_name}` enum: {_format_list(enum_values)}")
        if items:
            item_resolved = _resolved_spec(schema, items)
            item_enum = _enum_values(item_resolved)
            if item_enum:
                lines.append(f"  - `{field_name}` item enum: {_format_list(item_enum)}")
            if isinstance(items.get("$ref"), str):
                lines.append(f"  - `{field_name}` items use `{items['$ref']}`")
        if isinstance(field_spec.get("$ref"), str):
            lines.append(f"  - `{field_name}` uses `{field_spec['$ref']}`")
    return lines

def generate_profile_schema_contract(profile: PromptProfile, stage: str) -> tuple[str, dict[str, Any]]:
    """Generate a machine-readable prompt contract from structured_result.schema.json.

    This renderer intentionally does not encode business logic. It only turns the
    JSON Schema into a concise technical contract for the LLM prompt.
    """
    schema_path, schema = _load_profile_schema(profile, stage)
    top_properties = _properties(schema)
    top_required = _required(schema)
    finding = _finding_schema(schema)
    finding_properties = _properties(finding)
    finding_required = _required(finding)
    finding_required_set = set(finding_required)
    attributes_raw = finding_properties.get("attributes") if isinstance(finding_properties.get("attributes"), dict) else {}
    attributes = _resolved_spec(schema, attributes_raw)
    attribute_properties = _properties(attributes)
    attribute_required = _required(attributes)
    conditional_attribute_requirements = _conditional_attribute_requirements(finding)
    attribute_required_set = set(attribute_required)

    lines: list[str] = []
    lines.append("# Generated profile schema contract")
    lines.append("")
    lines.append("This fragment is generated automatically from the profile JSON Schema.")
    lines.append("Do not treat it as business guidance. It is the machine-readable output contract for this profile.")
    lines.append("")
    lines.append(f"- profile_id: `{profile.profile_id}`")
    if profile.profile_version is not None:
        lines.append(f"- profile_version: `{profile.profile_version}`")
    lines.append(f"- schema_path: `{schema_path}`")
    title = schema.get("title")
    if isinstance(title, str) and title.strip():
        lines.append(f"- schema_title: {title.strip()}")
    schema_description = schema.get("description")
    if isinstance(schema_description, str) and schema_description.strip():
        lines.append(f"- schema_description: {schema_description.strip()}")
    for key in sorted(schema):
        if key.startswith("x_") or key.startswith("x-"):
            value = schema[key]
            encoded = json.dumps(value, ensure_ascii=False, sort_keys=True) if not isinstance(value, str) else value
            lines.append(f"- schema_{key}: {encoded}")

    lines.append("")
    lines.append("## Top-level object contract")
    lines.append(f"- allowed top-level fields: {_format_list(list(top_properties.keys()))}")
    lines.append(f"- required top-level fields: {_format_list(top_required)}")
    policy = _additional_policy(schema)
    if policy:
        lines.append(f"- top-level {policy}")
    for name, spec in top_properties.items():
        if isinstance(spec, dict):
            lines.append(_field_summary(name, spec, set(top_required)))
    desc = []
    for name, spec in top_properties.items():
        desc.extend(_description_lines(name, spec))
    if desc:
        lines.append("")
        lines.append("Top-level descriptions and schema guidance:")
        lines.extend(desc)

    lines.append("")
    lines.append("## Finding object contract")
    if finding:
        lines.append(f"- required finding fields: {_format_list(finding_required)}")
        finding_policy = _additional_policy(finding)
        if finding_policy:
            lines.append(f"- finding {finding_policy}")
        for key in ("finding_type", "assessment", "decision", "severity"):
            enum_values = _enum_values(finding_properties.get(key))
            lines.append(f"- allowed {key} values: {_format_list(enum_values)}")
        confidence = finding_properties.get("confidence") if isinstance(finding_properties.get("confidence"), dict) else {}
        if confidence:
            lines.append(
                "- confidence: type=number; "
                f"range={confidence.get('minimum', '-inf')}..{confidence.get('maximum', '+inf')}"
            )
        if "evidence_refs" in finding_properties:
            requirement = "required" if "evidence_refs" in finding_required_set else "optional"
            evidence_spec = finding_properties.get("evidence_refs") if isinstance(finding_properties.get("evidence_refs"), dict) else {}
            item_type = _json_type(evidence_spec.get("items")) if isinstance(evidence_spec, dict) else "unknown"
            lines.append(f"- evidence_refs: {requirement}; type=array; item_type={item_type}")
        lines.append("")
        lines.append("Finding fields:")
        for name, spec in finding_properties.items():
            if isinstance(spec, dict):
                lines.append(_field_summary(name, spec, finding_required_set))
        desc = []
        for name, spec in finding_properties.items():
            desc.extend(_description_lines(name, spec))
        if desc:
            lines.append("")
            lines.append("Finding descriptions and schema guidance:")
            lines.extend(desc)
    else:
        lines.append("- finding schema could not be located in the JSON Schema. Follow the top-level schema strictly.")

    lines.append("")
    lines.append("## Profile-specific attributes contract")
    if isinstance(attributes, dict) and attributes:
        if attribute_properties:
            lines.append(f"- allowed profile-specific attributes: {_format_list(list(attribute_properties.keys()))}")
            lines.append(f"- required profile-specific attributes: {_format_list(attribute_required)}")
            attr_policy = _additional_policy(attributes)
            if attr_policy:
                lines.append(f"- attributes {attr_policy}")
            lines.append("")
            lines.append("Attribute fields:")
            for name, spec in attribute_properties.items():
                if isinstance(spec, dict):
                    lines.append(_field_summary(name, spec, attribute_required_set))
                    items = spec.get("items") if isinstance(spec.get("items"), dict) else None
                    if items and _enum_values(items):
                        lines.append(f"  - `{name}` item enum: {_format_list(_enum_values(items))}")
            desc = []
            for name, spec in attribute_properties.items():
                desc.extend(_description_lines(name, spec))
            if desc:
                lines.append("")
                lines.append("Attribute descriptions and schema guidance:")
                lines.extend(desc)
        else:
            attr_policy = _additional_policy(attributes)
            if attr_policy:
                lines.append(f"- attributes {attr_policy}")
            lines.append("- no explicit attribute properties are specified in schema")
    else:
        lines.append("- no `attributes` object is defined in the finding schema")

    if conditional_attribute_requirements:
        lines.append("")
        lines.append("## Conditional required attributes by finding_type")
        lines.append("These requirements are mandatory in addition to the base attributes contract:")
        for finding_type, required_fields in conditional_attribute_requirements.items():
            lines.append(f"- `{finding_type}`: {_format_list(required_fields)}")

    refs = _collect_local_refs(attributes)
    rendered_refs: set[str] = set()
    if refs:
        lines.append("")
        lines.append("## Nested object contracts referenced from attributes")
        queue = list(refs)
        while queue:
            ref = queue.pop(0)
            if ref in rendered_refs:
                continue
            rendered_refs.add(ref)
            nested = _resolve_ref(schema, ref)
            if isinstance(nested, dict):
                lines.append("")
                lines.extend(_render_nested_contract(schema, ref))
                for child_ref in _collect_local_refs(nested):
                    if child_ref not in rendered_refs and child_ref not in queue:
                        queue.append(child_ref)

    lines.append("")
    lines.append("Strict instruction: final structured output for this profile must satisfy this JSON Schema exactly.")

    text = "\n".join(lines).strip() + "\n"
    meta = {
        "generated_fragment": GENERATED_PROFILE_SCHEMA_CONTRACT,
        "schema_path": str(schema_path),
        "schema_sha256": sha256_text(json.dumps(schema, ensure_ascii=False, sort_keys=True)),
        "generated_prompt_sha256": sha256_text(text),
        "top_level_fields": list(top_properties.keys()),
        "required_top_level_fields": top_required,
        "required_finding_fields": finding_required,
        "allowed_finding_types": _enum_values(finding_properties.get("finding_type")),
        "allowed_assessments": _enum_values(finding_properties.get("assessment")),
        "allowed_decisions": _enum_values(finding_properties.get("decision")),
        "allowed_severities": _enum_values(finding_properties.get("severity")),
        "allowed_attributes": list(attribute_properties.keys()),
        "conditional_required_attributes": conditional_attribute_requirements,
        "nested_contract_refs": sorted(rendered_refs),
    }
    return text, meta


def load_prompt_fragments(profile_dir: Path, stage: str) -> tuple[PromptProfile, list[PromptFragment]]:
    profile = load_prompt_profile(profile_dir)
    if stage not in SUPPORTED_PROMPT_STAGES:
        raise PromptProfileError(
            f"profile_id={profile.profile_id}: unsupported prompt stage {stage!r}; expected one of {list(SUPPORTED_PROMPT_STAGES)}"
        )
    if stage not in profile.prompt_assembly:
        available = ", ".join(sorted(profile.prompt_assembly)) or "none"
        raise PromptProfileError(
            f"profile_id={profile.profile_id}: missing prompt_assembly.{stage} in {profile.profile_yaml}; "
            f"available stages: {available}"
        )
    fragments: list[PromptFragment] = []
    for declared_path in profile.prompt_assembly[stage]:
        if declared_path == GENERATED_PROFILE_SCHEMA_CONTRACT:
            text, generated_meta = generate_profile_schema_contract(profile, stage)
            schema_path = Path(str(generated_meta["schema_path"]))
            fragments.append(
                PromptFragment(
                    stage=stage,
                    declared_path=declared_path,
                    resolved_path=schema_path,
                    text=text,
                    chars=len(text),
                    sha256=sha256_text(text),
                    generated=True,
                )
            )
            continue

        resolved = (profile.profile_dir / declared_path).resolve()
        if not resolved.exists() or not resolved.is_file():
            raise _fragment_error(
                profile=profile,
                stage=stage,
                declared_path=declared_path,
                resolved_path=resolved,
                reason="file does not exist",
            )
        try:
            text = resolved.read_text(encoding="utf-8", errors="ignore")
        except Exception as exc:
            raise _fragment_error(
                profile=profile,
                stage=stage,
                declared_path=declared_path,
                resolved_path=resolved,
                reason=f"cannot read file: {exc}",
            ) from exc
        fragments.append(
            PromptFragment(
                stage=stage,
                declared_path=declared_path,
                resolved_path=resolved,
                text=text,
                chars=len(text),
                sha256=sha256_text(text),
                generated=False,
            )
        )
    return profile, fragments


def assemble_prompt_stage(profile_dir: Path, stage: str, *, separator: str = PROMPT_STAGE_SEPARATOR) -> tuple[str, dict[str, Any]]:
    """Assemble one prompt stage by concatenating profile.yaml prompt_assembly fragments.

    Paths are resolved relative to the concrete profile directory.
    Generated fragments such as @generated/profile_schema_contract are expanded in place.
    """
    profile, fragments = load_prompt_fragments(profile_dir, stage)
    assembled = separator.join(fragment.text.strip() for fragment in fragments).strip() + "\n"
    meta = {
        "profile_id": profile.profile_id,
        "profile_version": profile.profile_version,
        "profile_dir": str(profile.profile_dir),
        "profile_yaml": str(profile.profile_yaml),
        "stage": stage,
        "separator": separator,
        "assembled_prompt_sha256": sha256_text(assembled),
        "fragments": [
            {
                "stage": fragment.stage,
                "declared_path": fragment.declared_path,
                "resolved_path": str(fragment.resolved_path),
                "chars": fragment.chars,
                "sha256": fragment.sha256,
                "generated": fragment.generated,
            }
            for fragment in fragments
        ],
    }
    return assembled, meta
