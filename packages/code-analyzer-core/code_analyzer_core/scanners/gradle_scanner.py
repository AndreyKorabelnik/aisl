from __future__ import annotations

"""Mechanical Gradle build declaration scanner.

The scanner intentionally does not execute Gradle, Groovy, or Kotlin. It only
publishes declarations that can be observed directly in build files, simple
string/alias resolutions, and explicit unresolved observations for dynamic
expressions.
"""

from collections import defaultdict
import hashlib
import re
import tomllib
from pathlib import Path
from typing import Any, Iterable

from code_analyzer_core.models import EvidenceRef, Fact

GRADLE_EXTRACTOR = "gradle_source_declaration"

_GRADLE_NAMES = {"build.gradle", "build.gradle.kts", "settings.gradle", "settings.gradle.kts"}
_DEP_CONFIGURATION = re.compile(
    r"^(?P<configuration>[A-Za-z_][A-Za-z0-9_]*)\s*(?:\(|\s)\s*(?P<expression>.+?)\s*\)?\s*(?:\{.*)?$"
)
_COORDINATE = re.compile(r"^(?P<group>[^:\s]+):(?P<artifact>[^:\s]+)(?::(?P<version>[^:\s]+))?(?::(?P<classifier>[^:\s]+))?(?:@(?P<extension>[^\s]+))?$")
_PROJECT_CALL = re.compile(r"project\s*\(\s*[\"'](?P<path>:[^\"']+)[\"']\s*\)")
_STRING = re.compile(r"^[\"'](?P<value>.*)[\"']$")
_ALIAS = re.compile(r"^(?P<namespace>[A-Za-z_][A-Za-z0-9_]*)\.(?P<alias>[A-Za-z_][A-Za-z0-9_.-]*)$")


def _stable_id(kind: str, *parts: Any) -> str:
    raw = "\u001f".join(str(part or "") for part in parts)
    return f"{kind}_{hashlib.sha256(raw.encode('utf-8')).hexdigest()[:24]}"


def _line_ref(path: Path, line_no: int, snippet: str | None = None) -> EvidenceRef:
    return EvidenceRef(
        file_path=str(path),
        line_start=line_no,
        line_end=line_no,
        snippet=(snippet.strip()[:500] if snippet else None),
        extractor=GRADLE_EXTRACTOR,
    )


def _strip_line_comment(line: str) -> str:
    in_single = False
    in_double = False
    escaped = False
    for index, char in enumerate(line):
        if escaped:
            escaped = False
            continue
        if char == "\\":
            escaped = True
            continue
        if char == "'" and not in_double:
            in_single = not in_single
        elif char == '"' and not in_single:
            in_double = not in_double
        elif char == "/" and not in_single and not in_double and index + 1 < len(line) and line[index + 1] == "/":
            return line[:index]
    return line


def _substitute(text: str, variables: dict[str, str]) -> tuple[str, list[str]]:
    unresolved: set[str] = set()

    def replace_braced(match: re.Match[str]) -> str:
        key = match.group(1)
        if key in variables:
            return variables[key]
        unresolved.add(key)
        return match.group(0)

    def replace_plain(match: re.Match[str]) -> str:
        key = match.group(1)
        if key in variables:
            return variables[key]
        unresolved.add(key)
        return match.group(0)

    value = re.sub(r"\$\{([A-Za-z_][A-Za-z0-9_.-]*)\}", replace_braced, text)
    value = re.sub(r"\$([A-Za-z_][A-Za-z0-9_]*)", replace_plain, value)
    return value, sorted(unresolved)


def _module_path(repo_root: Path, path: Path) -> str:
    try:
        relative_parent = path.parent.resolve().relative_to(repo_root.resolve())
    except ValueError:
        return ":"
    if str(relative_parent) in {"", "."}:
        return ":"
    return ":" + ":".join(relative_parent.parts)


def _find_repo_root(files: Iterable[Path]) -> Path:
    settings = sorted((path for path in files if path.name in {"settings.gradle", "settings.gradle.kts"}), key=lambda p: len(p.parts))
    if settings:
        return settings[0].parent.resolve()
    builds = sorted((path for path in files if path.name in {"build.gradle", "build.gradle.kts"}), key=lambda p: len(p.parts))
    return (builds[0].parent if builds else Path.cwd()).resolve()


def _read_gradle_files(files: Iterable[Path]) -> list[Path]:
    return sorted(
        path for path in files
        if path.name in _GRADLE_NAMES or path.suffix.lower() == ".gradle" or path.name == "libs.versions.toml"
    )


def _parse_variables(paths: Iterable[Path]) -> dict[str, str]:
    variables: dict[str, str] = {}
    pattern = re.compile(r"^\s*(?:def\s+|val\s+|var\s+)?([A-Za-z_][A-Za-z0-9_]*)\s*=\s*[\"']([^\"']*)[\"']\s*;?\s*$")
    for path in paths:
        if path.name == "libs.versions.toml":
            continue
        try:
            lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
        except OSError:
            continue
        for line in lines:
            match = pattern.match(_strip_line_comment(line))
            if match:
                variables[match.group(1)] = match.group(2)
    # Resolve simple variable chains deterministically.
    for _ in range(5):
        changed = False
        for key, raw in list(variables.items()):
            resolved, _ = _substitute(raw, variables)
            if resolved != raw:
                variables[key] = resolved
                changed = True
        if not changed:
            break
    return variables


def _parse_aliases(paths: Iterable[Path], variables: dict[str, str]) -> tuple[dict[str, list[str]], list[Fact]]:
    aliases: dict[str, list[str]] = defaultdict(list)
    facts: list[Fact] = []
    for path in paths:
        if path.name == "libs.versions.toml":
            try:
                payload = tomllib.loads(path.read_text(encoding="utf-8"))
            except Exception:
                continue
            versions = {str(k): str(v) for k, v in (payload.get("versions") or {}).items()}
            for alias, item in sorted((payload.get("libraries") or {}).items()):
                coordinate: str | None = None
                unresolved: list[str] = []
                if isinstance(item, str):
                    coordinate = item
                elif isinstance(item, dict):
                    module = item.get("module")
                    group = item.get("group")
                    name = item.get("name")
                    version = item.get("version")
                    version_ref = item.get("version.ref") or item.get("version_ref")
                    if isinstance(version, dict):
                        version_ref = version.get("ref")
                        version = version.get("require") or version.get("strictly") or version.get("prefer")
                    if version_ref:
                        version = versions.get(str(version_ref))
                        if version is None:
                            unresolved.append(str(version_ref))
                    module = module or (f"{group}:{name}" if group and name else None)
                    coordinate = f"{module}:{version}" if module and version else str(module or "")
                if coordinate:
                    key = f"libs.{alias}"
                    aliases[key].append(coordinate)
                    facts.append(Fact(
                        fact_type="gradle_version_catalog_observation",
                        name=key,
                        properties={
                            "observation_id": _stable_id("gradle_catalog", path, alias, coordinate),
                            "alias": key,
                            "coordinates": [coordinate],
                            "unresolved_symbols": unresolved,
                            "configuration_format": "toml",
                            "evidence_maturity_level": "confirmed" if not unresolved else "unresolved",
                        },
                        evidence=[EvidenceRef(file_path=str(path), extractor=GRADLE_EXTRACTOR)],
                    ))
            continue

        try:
            lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
        except OSError:
            continue
        namespace: str | None = None
        bracket_depth = 0
        for line_no, raw_line in enumerate(lines, 1):
            line = _strip_line_comment(raw_line).strip()
            start = re.match(r"^(?:ext\.)?([A-Za-z_][A-Za-z0-9_]*)\s*=\s*\[\s*$", line)
            if start:
                namespace = start.group(1)
                bracket_depth = 1
                continue
            if namespace:
                bracket_depth += line.count("[") - line.count("]")
                item = re.match(r"^([A-Za-z_][A-Za-z0-9_]*)\s*:\s*[\"']([^\"']+)[\"']\s*,?\s*$", line)
                if item:
                    coordinate, unresolved = _substitute(item.group(2), variables)
                    key = f"{namespace}.{item.group(1)}"
                    aliases[key].append(coordinate)
                    facts.append(Fact(
                        fact_type="gradle_version_catalog_observation",
                        name=key,
                        properties={
                            "observation_id": _stable_id("gradle_alias", path, line_no, key, coordinate),
                            "alias": key,
                            "coordinates": [coordinate],
                            "unresolved_symbols": unresolved,
                            "configuration_format": "groovy",
                            "evidence_maturity_level": "confirmed" if not unresolved else "unresolved",
                        },
                        evidence=[_line_ref(path, line_no, raw_line)],
                    ))
                if bracket_depth <= 0:
                    namespace = None
                continue
            direct = re.match(r"^([A-Za-z_][A-Za-z0-9_]*)\.([A-Za-z_][A-Za-z0-9_.-]*)\s*=\s*(.+?)\s*;?\s*$", line)
            if not direct:
                continue
            key = f"{direct.group(1)}.{direct.group(2)}"
            expression = direct.group(3).strip()
            string_match = _STRING.match(expression)
            coordinates: list[str] = []
            unresolved: list[str] = []
            if string_match:
                coordinate, unresolved = _substitute(string_match.group("value"), variables)
                coordinates = [coordinate]
            elif expression.startswith("[") and expression.endswith("]"):
                members = [part.strip() for part in expression[1:-1].split(",") if part.strip()]
                for member in members:
                    coordinates.extend(aliases.get(member, []))
                    if member not in aliases:
                        unresolved.append(member)
            if coordinates or unresolved:
                aliases[key].extend(coordinates)
                facts.append(Fact(
                    fact_type="gradle_version_catalog_observation",
                    name=key,
                    properties={
                        "observation_id": _stable_id("gradle_alias", path, line_no, key, expression),
                        "alias": key,
                        "coordinates": coordinates,
                        "unresolved_symbols": sorted(set(unresolved)),
                        "configuration_format": "groovy",
                        "evidence_maturity_level": "confirmed" if coordinates and not unresolved else "unresolved",
                    },
                    evidence=[_line_ref(path, line_no, raw_line)],
                ))
    return {key: list(dict.fromkeys(values)) for key, values in sorted(aliases.items())}, facts


def _parse_settings(repo_root: Path, paths: Iterable[Path]) -> tuple[str, list[str], list[Fact]]:
    root_name = repo_root.name
    modules: list[str] = []
    facts: list[Fact] = []
    for path in paths:
        if path.name not in {"settings.gradle", "settings.gradle.kts"}:
            continue
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
        joined = "\n".join(_strip_line_comment(line) for line in lines)
        root_match = re.search(r"rootProject\.name\s*=\s*[\"']([^\"']+)[\"']", joined)
        if root_match:
            root_name = root_match.group(1)
        include_buffer = ""
        include_start_line = 1
        for line_no, raw_line in enumerate(lines, 1):
            line = _strip_line_comment(raw_line).strip()
            if re.match(r"^include\b", line):
                include_buffer = line
                include_start_line = line_no
            elif include_buffer and (raw_line[:1].isspace() or include_buffer.rstrip().endswith(",")):
                include_buffer += " " + line
            elif include_buffer:
                for value in re.findall(r"[\"']([^\"']+)[\"']", include_buffer):
                    module = value if value.startswith(":") else f":{value}"
                    modules.append(module)
                include_buffer = ""
            if include_buffer and not include_buffer.rstrip().endswith(",") and line.count("(") == line.count(")"):
                for value in re.findall(r"[\"']([^\"']+)[\"']", include_buffer):
                    module = value if value.startswith(":") else f":{value}"
                    modules.append(module)
                include_buffer = ""
            build_match = re.search(r"includeBuild\s*(?:\(|\s)\s*[\"']([^\"']+)[\"']", line)
            if build_match:
                facts.append(Fact(
                    fact_type="gradle_included_build_observation",
                    name=build_match.group(1),
                    properties={
                        "observation_id": _stable_id("gradle_included_build", path, line_no, build_match.group(1)),
                        "included_build_path": build_match.group(1),
                        "evidence_maturity_level": "confirmed",
                    },
                    evidence=[_line_ref(path, line_no, raw_line)],
                ))
        if include_buffer:
            for value in re.findall(r"[\"']([^\"']+)[\"']", include_buffer):
                module = value if value.startswith(":") else f":{value}"
                modules.append(module)
    modules = sorted(dict.fromkeys(modules))
    return root_name, modules, facts


def _coordinate_properties(coordinate: str) -> dict[str, Any]:
    match = _COORDINATE.match(coordinate)
    if not match:
        return {"coordinate": coordinate}
    return {
        "group_id": match.group("group"),
        "artifact_id": match.group("artifact"),
        "version": match.group("version"),
        "classifier": match.group("classifier"),
        "extension": match.group("extension"),
        "coordinate": coordinate,
    }


def _source_set_for_configuration(configuration: str) -> str:
    lower = configuration.lower()
    if "test" in lower:
        return "test"
    if "integrationtest" in lower or "integration_test" in lower:
        return "integrationTest"
    return "main"


def scan_gradle_dependencies(files: list[Path]) -> tuple[list[Fact], dict[str, Any]]:
    paths = _read_gradle_files(files)
    repo_root = _find_repo_root(paths)
    variables = _parse_variables(paths)
    aliases, alias_facts = _parse_aliases(paths, variables)
    root_name, declared_modules, settings_facts = _parse_settings(repo_root, paths)

    facts: list[Fact] = [*alias_facts, *settings_facts]
    build_files = [path for path in paths if path.name in {"build.gradle", "build.gradle.kts"}]
    observed_modules = {":", *declared_modules, *(_module_path(repo_root, path) for path in build_files)}
    facts.append(Fact(
        fact_type="gradle_project_observation",
        name=root_name,
        properties={
            "observation_id": _stable_id("gradle_project", repo_root, root_name),
            "root_project_name": root_name,
            "root_directory": str(repo_root),
            "module_paths": sorted(observed_modules),
            "build_system": "gradle",
            "evidence_maturity_level": "confirmed",
        },
        evidence=[EvidenceRef(file_path=str(next((p for p in paths if p.name.startswith("settings.gradle")), repo_root)), extractor=GRADLE_EXTRACTOR)],
    ))

    module_build_file: dict[str, Path] = {_module_path(repo_root, path): path for path in build_files}
    for module in sorted(observed_modules):
        build_file = module_build_file.get(module)
        facts.append(Fact(
            fact_type="gradle_module_observation",
            name=module,
            properties={
                "observation_id": _stable_id("gradle_module", repo_root, module),
                "module_path": module,
                "module_name": root_name if module == ":" else module.rsplit(":", 1)[-1],
                "project_directory": str(repo_root if module == ":" else repo_root.joinpath(*module.strip(":").split(":"))),
                "build_file": str(build_file) if build_file else None,
                "declared_in_settings": module in declared_modules or module == ":",
                "build_system": "gradle",
                "evidence_maturity_level": "confirmed" if module in declared_modules or build_file else "observed_without_build_file",
            },
            evidence=[EvidenceRef(file_path=str(build_file or repo_root), extractor=GRADLE_EXTRACTOR)],
        ))

    counts: defaultdict[str, int] = defaultdict(int)
    unresolved_count = 0
    for path in paths:
        if path.name == "libs.versions.toml" or path.name.startswith("settings.gradle"):
            continue
        module = _module_path(repo_root, path) if path.name in {"build.gradle", "build.gradle.kts"} else ":"
        try:
            lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
        except OSError:
            continue
        block_stack: list[str] = []
        brace_depth = 0
        for line_no, raw_line in enumerate(lines, 1):
            line = _strip_line_comment(raw_line).strip()
            if not line:
                continue
            # Track coarse block context only; this is not a Groovy parser.
            block_start = re.match(r"^([A-Za-z_][A-Za-z0-9_]*)\s*\{", line)
            if block_start:
                block_stack.append(block_start.group(1))
            context = "/".join(block_stack)

            apply_match = re.search(r"apply\s+(?:from\s*:\s*|\(\s*from\s*=\s*)[\"']([^\"']+)[\"']", line)
            if apply_match:
                facts.append(Fact(
                    fact_type="gradle_applied_script_observation",
                    name=apply_match.group(1),
                    properties={
                        "observation_id": _stable_id("gradle_script", path, line_no, apply_match.group(1)),
                        "module_path": module,
                        "script_path": apply_match.group(1),
                        "evidence_maturity_level": "confirmed",
                    },
                    evidence=[_line_ref(path, line_no, raw_line)],
                ))
                counts["applied_scripts"] += 1

            plugin_match = re.search(r"\bid\s*(?:\(\s*)?[\"']([^\"']+)[\"']", line)
            plugin_version_match = re.search(r"\bversion\s+[\"']([^\"']+)[\"']", line)
            apply_plugin_match = re.search(r"apply\s+plugin\s*:\s*[\"']([^\"']+)[\"']", line)
            plugin_id = plugin_match.group(1) if plugin_match else (apply_plugin_match.group(1) if apply_plugin_match else None)
            if plugin_id:
                plugin_version = plugin_version_match.group(1) if plugin_version_match else None
                facts.append(Fact(
                    fact_type="gradle_plugin_observation",
                    name=plugin_id,
                    properties={
                        "observation_id": _stable_id("gradle_plugin", path, line_no, module, plugin_id),
                        "module_path": module,
                        "plugin_id": plugin_id,
                        "version": plugin_version,
                        "application_kind": "plugins_block" if plugin_match else "apply_plugin",
                        "evidence_maturity_level": "confirmed",
                    },
                    evidence=[_line_ref(path, line_no, raw_line)],
                ))
                counts["plugins"] += 1

            repository_match = re.search(r"\b(?:url\s*(?:=|\s)\s*)[\"']([^\"']+)[\"']", line)
            if repository_match and "repositories" in context:
                value, unresolved = _substitute(repository_match.group(1), variables)
                facts.append(Fact(
                    fact_type="gradle_repository_observation",
                    name=value,
                    properties={
                        "observation_id": _stable_id("gradle_repository", path, line_no, module, value),
                        "module_path": module,
                        "repository_url_expression": repository_match.group(1),
                        "repository_url": value,
                        "unresolved_symbols": unresolved,
                        "evidence_maturity_level": "confirmed" if not unresolved else "unresolved",
                    },
                    evidence=[_line_ref(path, line_no, raw_line)],
                ))
                counts["repositories"] += 1

            if "sourceSets" in context:
                source_match = re.match(r"^([A-Za-z_][A-Za-z0-9_]*)\s*\{", line)
                if source_match and source_match.group(1) not in {"sourceSets", "resources", "java"}:
                    source_set = source_match.group(1)
                    facts.append(Fact(
                        fact_type="gradle_source_set_observation",
                        name=f"{module}:{source_set}",
                        properties={
                            "observation_id": _stable_id("gradle_source_set", path, line_no, module, source_set),
                            "module_path": module,
                            "source_set": source_set,
                            "evidence_maturity_level": "confirmed",
                        },
                        evidence=[_line_ref(path, line_no, raw_line)],
                    ))
                    counts["source_sets"] += 1

            dependency_line = line
            inline_dependencies = re.match(r"^dependencies\s*\{\s*(.*?)\s*\}\s*$", line)
            if inline_dependencies:
                dependency_line = inline_dependencies.group(1).strip()
            in_dependencies = "dependencies" in context or inline_dependencies is not None or re.match(r"^(?:classpath|implementation|api|compileOnly|runtimeOnly|annotationProcessor|testImplementation|testCompileOnly|liquibaseRuntime)\b", dependency_line)
            if in_dependencies:
                dependency_match = _DEP_CONFIGURATION.match(dependency_line)
                if dependency_match:
                    configuration = dependency_match.group("configuration")
                    if configuration not in {"dependencies", "exclude", "because", "constraints", "components"}:
                        # Preserve the complete source expression after the configuration name.
                        # The previous regex capture intentionally tolerated optional call
                        # parentheses, but could therefore trim the final ``)`` from values such
                        # as ``project(":api")``. Keep the verbatim expression for provenance
                        # and use a normalized inner form only for mechanical parsing.
                        expression = dependency_line[len(configuration):].strip().rstrip(";")
                        # A dependency may open a configuration closure on the same
                        # line (for example ``implementation(alias) {``). The closure
                        # is not part of the dependency expression and must not turn a
                        # resolvable alias into a dynamic/unresolved observation.
                        expression = re.sub(r"\s*\{\s*$", "", expression).strip()
                        if expression.startswith("="):
                            project_match = None
                            unresolved = []
                            continue
                        parse_expression = expression
                        if parse_expression.startswith("(") and parse_expression.endswith(")"):
                            parse_expression = parse_expression[1:-1].strip()
                        project_match = _PROJECT_CALL.search(parse_expression)
                        if project_match:
                            target = project_match.group("path")
                            props = {
                                "observation_id": _stable_id("module_dependency", path, line_no, module, configuration, target),
                                "dependency_kind": "gradle_project",
                                "build_system": "gradle",
                                "source_module_path": module,
                                "target_module_path": target,
                                "configuration": configuration,
                                "scope": configuration,
                                "source_set": _source_set_for_configuration(configuration),
                                "expression": expression,
                                "evidence_maturity_level": "confirmed",
                            }
                            facts.append(Fact(fact_type="module_dependency_observation", name=f"{module}->{target}", properties=props, evidence=[_line_ref(path, line_no, raw_line)]))
                            facts.append(Fact(fact_type="build_dependency_observation", name=f"{module}->{target}", properties=props, evidence=[_line_ref(path, line_no, raw_line)]))
                            counts["module_dependencies"] += 1
                        else:
                            inner = parse_expression
                            wrapper = re.match(r"(?:platform|enforcedPlatform|files|fileTree)\s*\((.*)\)\s*$", inner)
                            if wrapper:
                                inner = wrapper.group(1).strip()
                            string_match = _STRING.match(inner)
                            coordinates: list[str] = []
                            resolution_basis = "literal"
                            alias_name: str | None = None
                            if string_match:
                                coordinate, unresolved = _substitute(string_match.group("value"), variables)
                                coordinates = [coordinate]
                            else:
                                alias_match = _ALIAS.match(inner)
                                unresolved = []
                                if alias_match:
                                    alias_name = inner
                                    coordinates = list(aliases.get(inner, []))
                                    resolution_basis = "alias"
                                    if not coordinates:
                                        unresolved = [inner]
                                else:
                                    map_match = re.search(r"group\s*:\s*[\"']([^\"']+)[\"'].*name\s*:\s*[\"']([^\"']+)[\"'](?:.*version\s*:\s*[\"']([^\"']+)[\"'])?", inner)
                                    if map_match:
                                        raw_coordinate = f"{map_match.group(1)}:{map_match.group(2)}" + (f":{map_match.group(3)}" if map_match.group(3) else "")
                                        coordinate, unresolved = _substitute(raw_coordinate, variables)
                                        coordinates = [coordinate]
                                        resolution_basis = "map_notation"
                                    else:
                                        unresolved = [inner]
                            if coordinates:
                                for coordinate in coordinates:
                                    cprops = _coordinate_properties(coordinate)
                                    maturity = "confirmed" if _COORDINATE.match(coordinate) and not unresolved else "unresolved"
                                    props = {
                                        "observation_id": _stable_id("gradle_dependency", path, line_no, module, configuration, coordinate),
                                        "external_dependency_id": _stable_id("external_dependency", path, line_no, module, configuration, coordinate),
                                        "dependency_kind": "gradle_artifact",
                                        "build_system": "gradle",
                                        "source_module_path": module,
                                        "configuration": configuration,
                                        "scope": configuration,
                                        "source_set": _source_set_for_configuration(configuration),
                                        "is_test_source": _source_set_for_configuration(configuration) != "main",
                                        "alias": alias_name,
                                        "resolution_basis": resolution_basis,
                                        "expression": expression,
                                        "unresolved_symbols": unresolved,
                                        "evidence_maturity_level": maturity,
                                        **cprops,
                                    }
                                    facts.append(Fact(fact_type="gradle_external_dependency_observation", name=coordinate, properties=props, evidence=[_line_ref(path, line_no, raw_line)]))
                                    facts.append(Fact(fact_type="build_dependency_observation", name=coordinate, properties=props, evidence=[_line_ref(path, line_no, raw_line)]))
                                    facts.append(Fact(fact_type="external_dependency", name=coordinate, properties=props, evidence=[_line_ref(path, line_no, raw_line)]))
                                    counts["external_dependencies"] += 1
                            elif unresolved:
                                unresolved_count += 1
                                facts.append(Fact(
                                    fact_type="gradle_unresolved_dependency_observation",
                                    name=f"{module}:{configuration}:{inner}",
                                    properties={
                                        "observation_id": _stable_id("gradle_unresolved_dependency", path, line_no, module, configuration, inner),
                                        "dependency_kind": "gradle_dynamic_expression",
                                        "build_system": "gradle",
                                        "source_module_path": module,
                                        "configuration": configuration,
                                        "scope": configuration,
                                        "source_set": _source_set_for_configuration(configuration),
                                        "expression": expression,
                                        "unresolved_symbols": sorted(set(unresolved)),
                                        "evidence_maturity_level": "unresolved",
                                    },
                                    evidence=[_line_ref(path, line_no, raw_line)],
                                ))

            brace_depth += line.count("{") - line.count("}")
            while block_stack and brace_depth < len(block_stack):
                block_stack.pop()

    facts.sort(key=lambda fact: (
        fact.fact_type,
        fact.name,
        fact.evidence[0].file_path if fact.evidence else "",
        fact.evidence[0].line_start or 0 if fact.evidence else 0,
        str((fact.properties or {}).get("observation_id") or ""),
    ))
    return facts, {
        "requested": True,
        "status": "success",
        "build_system": "gradle",
        "gradle_files_scanned": len(paths),
        "build_files_scanned": len(build_files),
        "root_project_name": root_name,
        "modules_observed": len(observed_modules),
        "module_dependencies_extracted": counts["module_dependencies"],
        "external_dependencies_extracted": counts["external_dependencies"],
        "plugins_extracted": counts["plugins"],
        "repositories_extracted": counts["repositories"],
        "source_sets_extracted": counts["source_sets"],
        "applied_scripts_extracted": counts["applied_scripts"],
        "aliases_resolved": sum(1 for values in aliases.values() if values),
        "unresolved_dependency_expressions": unresolved_count,
        "facts_extracted": len(facts),
        "policy": "source declarations and simple alias/string resolution only; Gradle is not executed and dynamic expressions remain unresolved observations",
    }
