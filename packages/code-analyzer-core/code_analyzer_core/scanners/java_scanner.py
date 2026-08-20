from __future__ import annotations

import re
from pathlib import Path
from code_analyzer_core.models import (
    Fact, EvidenceRef, SchemaInfo, FieldInfo, InterfaceInfo, RelationInfo, Direction, InterfaceKind
)
from code_analyzer_core.utils import snippet_around, normalize_name
from code_analyzer_core.scanners.java_trace_common import _tree_sitter_setter_bindings, _tree_sitter_builder_bindings, _kafka_payload_type_from_method_info
from code_analyzer_core.scanners.java_syntax import (
    JAVA_SYNTAX_EXTRACTOR,
    JavaAnnotation,
    JavaMethod,
    JavaSyntaxFile,
    parse_java_files,
    method_syntax_dict,
)

# Domain-pattern regexes are still used after Tree-sitter has produced exact Java nodes.
# They no longer define class/method boundaries.
REST_CLASS_ANNOTATIONS = {"RestController", "Controller"}
REST_MAPPING_ANNOTATIONS = {"GetMapping", "PostMapping", "PutMapping", "DeleteMapping", "PatchMapping", "RequestMapping"}
KAFKA_LISTENER_ANNOTATION = "KafkaListener"
GRPC_SERVICE_ANNOTATION = "GrpcService"
CALLBACK_INTERFACE_SUFFIXES = ("Facade", "Callback", "SPI", "Spi")
ANNOT_DESC_NAMES = {"Schema", "ApiModelProperty", "Operation", "ApiOperation"}


CLIENT_CLASS_ANNOTATIONS = {"FeignClient"}
VALIDATION_ANNOTATIONS = {"NotNull", "NotBlank", "NotEmpty", "Size", "Min", "Max", "Pattern", "Email", "Positive", "PositiveOrZero", "Past", "Future"}


def _annotation_arg_text(arguments: str | None, key: str) -> str | None:
    """Extract a simple annotation argument value.

    This helper intentionally handles only direct string/primitive annotation
    arguments returned by the Java syntax extractor. It is not a Java parser and
    does not infer semantics from arbitrary annotation expressions.
    """
    if not arguments:
        return None
    text = str(arguments).strip()
    patterns = [
        rf"\b{re.escape(key)}\s*=\s*\"([^\"]*)\"",
        rf"\b{re.escape(key)}\s*=\s*([^,\)]+)",
    ]
    if key == "value":
        patterns.append(r'^\s*"([^"]*)"\s*$')
    for pat in patterns:
        m = re.search(pat, text, re.DOTALL)
        if not m:
            continue
        value = str(m.group(1)).strip()
        if len(value) >= 2 and value[0] == value[-1] == '"':
            value = value[1:-1]
        return value.strip() or None
    return None


def _semantic_description(annotations: tuple[JavaAnnotation, ...]) -> str | None:
    for ann in annotations:
        if ann.name == "Schema":
            for key in ("description", "title", "name"):
                value = _annotation_arg_text(ann.arguments, key)
                if value:
                    return value
        if ann.name == "ApiModelProperty":
            for key in ("value", "notes"):
                value = _annotation_arg_text(ann.arguments, key)
                if value:
                    return value
        if ann.name == "Operation":
            for key in ("summary", "description"):
                value = _annotation_arg_text(ann.arguments, key)
                if value:
                    return value
        if ann.name == "ApiOperation":
            for key in ("value", "notes"):
                value = _annotation_arg_text(ann.arguments, key)
                if value:
                    return value
    return None


def _semantic_annotation_props(annotations: tuple[JavaAnnotation, ...]) -> dict[str, object]:
    props: dict[str, object] = {}
    description = _semantic_description(annotations)
    if description:
        props["description"] = description
    for ann in annotations:
        if ann.name in {"Schema", "ApiModelProperty"}:
            if _annotation_arg_text(ann.arguments, "example"):
                props["example"] = _annotation_arg_text(ann.arguments, "example")
            if _annotation_arg_text(ann.arguments, "allowableValues"):
                props["enum_values"] = _annotation_arg_text(ann.arguments, "allowableValues")
            if _annotation_arg_text(ann.arguments, "required"):
                props["required"] = _annotation_arg_text(ann.arguments, "required")
            if _annotation_arg_text(ann.arguments, "requiredMode"):
                props["required_mode"] = _annotation_arg_text(ann.arguments, "requiredMode")
    return props


def _validation_constraints(annotations: tuple[JavaAnnotation, ...]) -> list[dict[str, object]]:
    out: list[dict[str, object]] = []
    for ann in annotations:
        if ann.name not in VALIDATION_ANNOTATIONS:
            continue
        item: dict[str, object] = {"annotation": ann.name}
        for key in ("min", "max", "regexp", "message"):
            value = _annotation_arg_text(ann.arguments, key)
            if value is not None:
                item[key] = value
        out.append(item)
    return out


def _serialization_name_binding(field_name: str, annotations: tuple[JavaAnnotation, ...]) -> dict[str, object]:
    """Return observed Java-to-wire naming metadata without assigning confidence.

    Explicit Jackson/Gson annotations are preserved verbatim.  When no rename
    annotation is present, the Java field name is exposed as the framework
    default-name observation rather than as a semantic identity verdict.
    """
    aliases: list[str] = []
    for ann in annotations:
        if ann.name == "SerializedName":
            value = ann.string_arg("value") or ann.string_arg()
            alternate = re.search(r"\balternate\s*=\s*\{([^}]*)\}", ann.arguments or "", re.DOTALL)
            if alternate:
                aliases.extend(re.findall(r'"([^"]+)"', alternate.group(1)))
            return {
                "serialized_name": value or field_name,
                "serialized_name_basis": "gson_serialized_name_annotation" if value else "java_field_name_default",
                "serialization_library": "gson",
                "serialization_aliases": list(dict.fromkeys(aliases)),
            }
        if ann.name == "JsonProperty":
            value = ann.string_arg("value") or ann.string_arg()
            return {
                "serialized_name": value or field_name,
                "serialized_name_basis": "jackson_json_property_annotation" if value else "java_field_name_default",
                "serialization_library": "jackson",
                "serialization_aliases": [],
            }
        if ann.name == "JsonAlias":
            aliases.extend(re.findall(r'"([^"]+)"', ann.arguments or ""))
    return {
        "serialized_name": field_name,
        "serialized_name_basis": "java_field_name_default",
        "serialization_library": None,
        "serialization_aliases": list(dict.fromkeys(aliases)),
    }


def _feign_client_props(ann: JavaAnnotation | None) -> dict[str, object]:
    if not ann:
        return {}
    props: dict[str, object] = {}
    for key in ("name", "value", "contextId", "url", "path", "configuration"):
        value = _annotation_arg_text(ann.arguments, key)
        if value:
            props[key] = value
    return props


def _is_external_client_type(type_name: str | None) -> bool:
    text = str(type_name or "")
    simple = text.split("<", 1)[0].split(".")[-1]
    return simple.endswith(("FeignClient", "Client", "Api", "Gateway", "ManagerService")) or simple in {"S3ManagerService", "RestTemplate", "WebClient"}


def _external_call_kind(receiver_type: str | None, receiver: str | None) -> str | None:
    text = f"{receiver_type or ''} {receiver or ''}".lower()
    if "feign" in text:
        return "feign_client"
    if "s3" in text:
        return "s3_client"
    if "resttemplate" in text or "webclient" in text:
        return "http_client"
    if _is_external_client_type(receiver_type):
        return "external_library_client"
    return None


def _clean_type(t: str) -> str:
    return re.sub(r"\s+", " ", t.strip())


def _unwrap_transport_payload_type(type_text: str | None) -> str:
    """Unwrap common reactive/transport wrappers from a declared Java type.

    This is a syntactic observation over a Tree-sitter-extracted type declaration.
    It does not assert runtime serialization or wire compatibility.
    """
    value = _normalize_java_type(type_text)
    wrappers = {
        "Uni", "Multi", "CompletionStage", "CompletableFuture", "Publisher",
        "Mono", "Flux", "Optional", "ResponseEntity", "StreamObserver",
    }
    previous = None
    while value != previous:
        previous = value
        match = re.match(r"([A-Za-z0-9_.$]+)\s*<\s*(.+)\s*>$", value)
        if not match or match.group(1).split(".")[-1] not in wrappers:
            break
        value = _normalize_java_type(match.group(2))
    return value


def _callback_interface_candidates(cls: object, local_declared_types: set[str]) -> list[str]:
    """Return bounded external-interface callback candidates.

    Only explicit ``implements`` clauses whose simple name has a callback/SPI-like
    suffix and whose declaration is absent from the repository are included.
    """
    out: list[str] = []
    for interface in getattr(cls, "implements", ()) or ():
        simple = _normalize_java_type(interface).split("<", 1)[0].split(".")[-1]
        if simple in local_declared_types:
            continue
        if simple.endswith(CALLBACK_INTERFACE_SUFFIXES):
            out.append(simple)
    return list(dict.fromkeys(out))


def _method_has_override(method: JavaMethod) -> bool:
    return any(annotation.name == "Override" for annotation in method.annotations)


def _grpc_service_name(cls: object) -> str:
    implemented = list(getattr(cls, "implements", ()) or ())
    if implemented:
        return _normalize_java_type(implemented[0]).split("<", 1)[0].split(".")[-1]
    return str(getattr(cls, "name", "unknown"))


def _upper_first(value: object) -> str:
    text = str(value or "")
    return text[:1].upper() + text[1:] if text else ""



def _normalize_java_type(t: str | None) -> str:
    """Normalize common Java type noise so schema lookup works."""
    if not t:
        return "unknown"
    t = re.sub(r"\s+", " ", str(t).strip())
    t = t.strip(",;")
    t = re.sub(r"^(public|private|protected|static|final|abstract|synchronized|native)\s+", "", t)
    t = re.sub(r"^(public|private|protected|static|final|abstract|synchronized|native)\s+", "", t)
    if re.match(r"^[A-Za-z0-9_.$<>?, \[\]]+\s+[A-Za-z_][A-Za-z0-9_]*$", t):
        toks = t.split()
        if len(toks) == 2 and toks[0] not in {"List", "Set", "Map"}:
            t = toks[0]
    m = re.match(r"(?:ResponseEntity|HttpEntity|Optional)\s*<\s*(.+?)\s*>$", t)
    if m:
        t = m.group(1)
    t = re.sub(r"\b([a-z_][a-zA-Z0-9_]*\.)+([A-Z][A-Za-z0-9_]*)", r"\2", t)
    if t in {"=", "public", "private", "protected", "void"}:
        return "unknown"
    return t.strip()


def _is_technical_noise_call_text(value: str) -> bool:
    low = value.lower()
    return any(tok in low for tok in [
        "log.trace", "log.debug", "log.info", "log.warn", "log.error", "loggerhandler",
        "logduration", "monitoring.", "prometheus", "timer", "observeduration", "observeDuration".lower(),
        "string.format", ".inc()", "countlatency", "latency"
    ])


def _request_field_propagation(method: JavaMethod) -> list[str]:
    """Extract request-related propagation hints from Tree-sitter call nodes.

    Setter/builder field mappings are intentionally left to dedicated mapper
    extractors. This helper only records direct calls/object creations involving
    request-like variables without scanning method text as Java syntax.
    """
    facts: list[str] = []
    request_tokens = ("request", "extRequest")
    for call in method.calls:
        receiver = (call.receiver or "").strip()
        args_text = ", ".join(call.args)
        if not receiver or not any(tok in args_text for tok in request_tokens):
            continue
        entry = f"{receiver}.{call.method}({args_text})"
        if len(entry) < 240 and not _is_technical_noise_call_text(entry):
            facts.append(entry)
    for creation in method.object_creations:
        args_text = ", ".join(creation.args)
        if not any(tok in args_text for tok in ("profiles", "Profiles", "response", "Response")):
            continue
        entry = f"new {creation.type.split('.')[-1]}({args_text})"
        if not _is_technical_noise_call_text(entry):
            facts.append(entry)
    out: list[str] = []
    for f in facts:
        if f not in out:
            out.append(f)
    return out[:30]




def _source_set_for_path(path: Path) -> str:
    normalized = str(path).replace('\\', '/')
    if '/src/test/' in normalized or normalized.endswith('/src/test'):
        return 'test'
    return 'main'


def _is_test_source(path: Path) -> bool:
    return _source_set_for_path(path) == 'test'


def _mapping_paths(mapping_args: str | None) -> list[str | None]:
    if not mapping_args:
        return [None]
    values: list[str] = []
    # Support direct quoted annotation arguments and array forms such as
    # value = {"/a", "/b"}. This is annotation argument normalization
    # over already parsed Java annotations, not Java boundary parsing.
    for pat in [r'value\s*=\s*(?:\{([^}]*)\}|"([^"]+)")', r'path\s*=\s*(?:\{([^}]*)\}|"([^"]+)")']:
        for m in re.finditer(pat, mapping_args, re.IGNORECASE | re.DOTALL):
            raw = m.group(1) if m.group(1) is not None else m.group(2)
            if raw is None:
                continue
            for q in re.finditer(r'"([^"]+)"', raw):
                values.append(q.group(1))
            if raw and not values and not raw.strip().startswith('{'):
                values.append(raw.strip())
    if not values:
        # Positional string or array positional values: @GetMapping("/x") or @GetMapping({"/a", "/b"})
        raw = mapping_args.strip()
        for q in re.finditer(r'"([^"]+)"', raw):
            values.append(q.group(1))
    out: list[str] = []
    for value in values:
        if value not in out:
            out.append(value)
    return out or [None]


def _join_paths(base: str | None, path: str | None) -> str | None:
    if not base and not path:
        return None
    if not base:
        return path or None
    if not path:
        return base or None
    b = str(base).strip()
    p = str(path).strip()
    if not b:
        return p or None
    if not p:
        return b or None
    return '/' + '/'.join(part.strip('/') for part in [b, p] if part.strip('/'))


def _request_mapping_http_method(mapping: JavaAnnotation) -> str | None:
    method = _method_mapping_http_method(mapping.name)
    if method:
        return method
    args = mapping.arguments or ''
    m = re.search(r'\bmethod\s*=\s*(?:RequestMethod\.)?([A-Z]+)', args)
    if m:
        return m.group(1).upper()
    return None


def _rest_request_parameters(method: JavaMethod) -> list[dict[str, object]]:
    params: list[dict[str, object]] = []
    for param in method.params:
        for ann in param.annotations:
            if ann.name not in {"PathVariable", "RequestParam", "RequestHeader"}:
                continue
            args = ann.arguments or ''
            explicit = None
            for pat in [r'\bvalue\s*=\s*"([^"]+)"', r'\bname\s*=\s*"([^"]+)"', r'^\s*"([^"]+)"\s*$']:
                m = re.search(pat, args)
                if m:
                    explicit = m.group(1)
                    break
            req_m = re.search(r'\brequired\s*=\s*(true|false)\b', args, re.IGNORECASE)
            default_m = re.search(r'\bdefaultValue\s*=\s*"([^"]*)"', args)
            params.append({
                "name": explicit or param.name,
                "java_parameter": param.name,
                "java_type": _normalize_java_type(param.type),
                "source": ann.name,
                "required": None if not req_m else req_m.group(1).lower() == 'true',
                "default_value": default_m.group(1) if default_m else None,
            })
    return params





def _strip_string_literal(value: str | None) -> str | None:
    if value is None:
        return None
    raw = str(value).strip()
    if len(raw) >= 2 and raw[0] == raw[-1] == '"':
        return raw[1:-1]
    return None


def _simple_symbol(value: str | None) -> str | None:
    if not value:
        return None
    text = str(value).strip()
    m = re.match(r'(?:[A-Za-z_][A-Za-z0-9_]*\.)?([A-Z][A-Z0-9_]+)$', text)
    return m.group(1) if m else None


def _settings_symbol(value: str | None) -> str | None:
    if not value:
        return None
    text = str(value).strip()
    m = re.match(r'(?:Settings|T\([^)]*Settings\))\.([A-Z][A-Z0-9_]+)$', text)
    return m.group(1) if m else _simple_symbol(text)


def _build_settings_property_map(parsed_files: list[JavaSyntaxFile]) -> dict[str, dict[str, object]]:
    out: dict[str, dict[str, object]] = {}
    for parsed in parsed_files:
        for cls in parsed.classes:
            if cls.name != "Settings" or cls.kind != "enum":
                continue
            for const in cls.enum_constants:
                if not const.args:
                    continue
                key = _strip_string_literal(const.args[0])
                if not key:
                    continue
                out[const.name] = {
                    "settings_symbol": const.name,
                    "property_key": key,
                    "evidence": EvidenceRef(file_path=str(parsed.file), line_start=const.line_start, line_end=const.line_end, snippet=const.text[:500], extractor=JAVA_SYNTAX_EXTRACTOR),
                }
    return out


def _build_consumer_props_topic_map(parsed_files: list[JavaSyntaxFile], settings_map: dict[str, dict[str, object]]) -> dict[str, dict[str, object]]:
    out: dict[str, dict[str, object]] = {}
    for parsed in parsed_files:
        for cls in parsed.classes:
            if cls.name != "ConsumerProps" or cls.kind != "enum":
                continue
            for const in cls.enum_constants:
                # ConsumerProps declares enum constants as (id, topic, concurrency, toggle).
                # The topic argument is a direct Settings enum reference in the source.
                if len(const.args) < 2:
                    continue
                topic_symbol = _settings_symbol(const.args[1])
                if not topic_symbol:
                    continue
                setting = settings_map.get(topic_symbol) or {}
                out[const.name] = {
                    "consumer_props_symbol": const.name,
                    "topic_settings_symbol": topic_symbol,
                    "topic_property_key": setting.get("property_key"),
                    "evidence": EvidenceRef(file_path=str(parsed.file), line_start=const.line_start, line_end=const.line_end, snippet=const.text[:500], extractor=JAVA_SYNTAX_EXTRACTOR),
                }
    return out


def _constructor_consumer_props_symbol(cls: object) -> str | None:
    symbols: list[str] = []
    for method in getattr(cls, 'methods', ()) or ():
        if getattr(method, 'name', None) != getattr(cls, 'name', None):
            continue
        for m in re.finditer(r'\bsuper\s*\((?P<args>.*?)\)\s*;', method.text, re.DOTALL):
            from code_analyzer_core.scanners.java_syntax import split_java_arguments
            args = split_java_arguments(m.group('args'))
            if args:
                sym = re.match(r'(?:ConsumerProps\.)?([A-Z][A-Z0-9_]+)$', args[0].strip())
                if sym:
                    symbols.append(sym.group(1))
    uniq = list(dict.fromkeys(symbols))
    return uniq[0] if len(uniq) == 1 else None


def _settings_get_string_symbol(expr: str | None) -> str | None:
    if not expr:
        return None
    m = re.search(r'\bsettings\s*\.\s*getStringValue\s*\(\s*([^()]+?)\s*\)', str(expr))
    if not m:
        return None
    return _settings_symbol(m.group(1))


def _method_local_setting_binding(method: JavaMethod, variable: str | None, settings_map: dict[str, dict[str, object]]) -> dict[str, object] | None:
    if not variable:
        return None
    cleaned = str(variable).strip()
    for assignment in method.assignments:
        if assignment.target != cleaned:
            continue
        symbol = _settings_get_string_symbol(assignment.expression)
        if not symbol:
            continue
        setting = settings_map.get(symbol) or {}
        return {
            "settings_symbol": symbol,
            "property_key": setting.get("property_key"),
            "binding_basis": "local_assignment_settings_getStringValue",
        }
    return None


def _class_string_constants(cls: object) -> dict[str, dict[str, object]]:
    out: dict[str, dict[str, object]] = {}
    for field in getattr(cls, 'fields', ()) or ():
        if _normalize_java_type(field.type) != 'String':
            continue
        m = re.search(r'=\s*("(?:[^"\\]|\\.)*")\s*;', field.raw, re.DOTALL)
        if not m:
            continue
        value = _strip_string_literal(m.group(1))
        if value is None:
            continue
        out[field.name] = {
            "constant_name": field.name,
            "constant_value": value,
            "binding_basis": "class_string_constant_initializer",
            "line_start": field.line_start,
            "line_end": field.line_end,
        }
    return out


def _resolve_string_expression(expr: str | None, constants: dict[str, dict[str, object]]) -> dict[str, object] | None:
    if not expr:
        return None
    cleaned = str(expr).strip()
    literal = _strip_string_literal(cleaned)
    if literal is not None:
        return {"value": literal, "basis": "string_literal", "symbol": None}
    const = constants.get(cleaned)
    if const:
        return {"value": const.get("constant_value"), "basis": const.get("binding_basis"), "symbol": cleaned}
    return None


def _http_response_type_from_args(args: list[str] | tuple[str, ...]) -> str:
    for arg in list(args)[2:]:
        m = re.match(r'([A-Za-z0-9_.$]+)\s*\.\s*class$', str(arg).strip())
        if m:
            return _normalize_java_type(m.group(1).split('.')[-1])
    return "unknown"


def _http_outbound_parts(method: JavaMethod, call: object, constants: dict[str, dict[str, object]]) -> dict[str, object] | None:
    call_method = str(getattr(call, 'method', '') or '')
    if call_method not in {"postForObject", "getForObject", "exchange"}:
        return None
    args = list(getattr(call, 'args', ()) or ())
    if not args:
        return None
    url = _resolve_string_expression(args[0], constants)
    http_method = "POST" if call_method == "postForObject" else "GET" if call_method == "getForObject" else None
    request_expr = None
    if call_method == "postForObject" and len(args) >= 2:
        request_expr = args[1]
    elif call_method == "exchange":
        if len(args) >= 2:
            mm = re.search(r'HttpMethod\.([A-Z]+)', args[1])
            http_method = mm.group(1) if mm else None
        if len(args) >= 3:
            request_expr = args[2]
    payload_type, payload_basis = _payload_type_from_expression(method, request_expr)
    response_type = _http_response_type_from_args(args)
    return {
        "url_expression": args[0],
        "url_resolved": (url or {}).get("value"),
        "url_resolution_basis": (url or {}).get("basis"),
        "url_symbol": (url or {}).get("symbol"),
        "http_method": http_method,
        "request_payload_expression": request_expr,
        "request_payload_type": payload_type,
        "request_payload_resolution_basis": payload_basis,
        "response_payload_type": response_type,
        "client_call_pattern": call_method,
    }


def _qualified_rest_properties_name(param: object) -> str | None:
    for ann in getattr(param, 'annotations', ()) or ():
        if ann.name != 'Qualifier':
            continue
        return ann.string_arg('value') or ann.string_arg()
    return None


def _build_rest_client_bindings(parsed_files: list[JavaSyntaxFile]) -> dict[str, list[dict[str, object]]]:
    property_prefix_by_bean: dict[str, str] = {}
    for parsed in parsed_files:
        for cls in parsed.classes:
            for method in cls.methods:
                cp_ann = _annotation_by_name(method.annotations, {"ConfigurationProperties"})
                if not cp_ann:
                    continue
                prefix = cp_ann.string_arg('value') or cp_ann.string_arg()
                if prefix:
                    property_prefix_by_bean[method.name] = prefix
    bindings: dict[str, list[dict[str, object]]] = {}
    for parsed in parsed_files:
        for cls in parsed.classes:
            for method in cls.methods:
                if not _annotation_by_name(method.annotations, {"Bean"}):
                    continue
                qualified_param_prefix: dict[str, str] = {}
                for param in method.params:
                    bean_name = _qualified_rest_properties_name(param)
                    if bean_name and bean_name in property_prefix_by_bean:
                        qualified_param_prefix[param.name] = property_prefix_by_bean[bean_name]
                if not qualified_param_prefix:
                    continue
                rest_prefixes = [prefix for var, prefix in qualified_param_prefix.items() if re.search(rf'new\s+RestClient\s*\(\s*{re.escape(var)}\b', method.body)]
                if not rest_prefixes:
                    continue
                for creation in method.object_creations:
                    simple_type = creation.type.split('.')[-1]
                    if simple_type in {"RestClient", "RestClientProperties", "SslProperties"}:
                        continue
                    if "new RestClient" not in creation.text:
                        continue
                    for prefix in rest_prefixes:
                        bindings.setdefault(simple_type, []).append({
                            "config_prefix": prefix,
                            "base_url_property_key": f"{prefix}.url",
                            "bean_factory_method": method.name,
                            "binding_basis": "bean_factory_configuration_properties_rest_client",
                            "source_file": str(parsed.file),
                            "line_start": method.line_start,
                        })
    # Deduplicate while preserving direct ambiguity if more than one bean creates the same class.
    for key, vals in list(bindings.items()):
        dedup: list[dict[str, object]] = []
        seen: set[tuple[object, object]] = set()
        for val in vals:
            marker = (val.get("config_prefix"), val.get("bean_factory_method"))
            if marker not in seen:
                seen.add(marker)
                dedup.append(val)
        bindings[key] = dedup
    return bindings

def _producer_record_parts(args: list[str] | tuple[str, ...]) -> dict[str, str | None]:
    parts = list(args)
    if not parts:
        return {"topic": None, "key": None, "payload": None}
    topic = parts[0]
    key = None
    payload = None
    if len(parts) == 1:
        payload = None
    elif len(parts) == 2:
        payload = parts[1]
    elif len(parts) == 3:
        key = parts[1]
        payload = parts[2]
    elif len(parts) == 4:
        key = parts[2]
        payload = parts[3]
    else:
        # ProducerRecord(topic, partition, timestamp, key, value, ...).
        key = parts[3] if len(parts) > 3 else None
        payload = parts[4] if len(parts) > 4 else parts[-1]
    return {"topic": topic, "key": key, "payload": payload}


def _inline_producer_record_parts(expr: str | None) -> dict[str, str | None] | None:
    if not expr or "ProducerRecord" not in expr:
        return None
    m = re.search(r'new\s+(?:[A-Za-z0-9_.]+\.)?ProducerRecord\s*(?:<[^>]*>)?\s*\((?P<args>.*)\)\s*$', expr, re.DOTALL)
    if not m:
        return None
    from code_analyzer_core.scanners.java_syntax import split_java_arguments
    return _producer_record_parts(split_java_arguments(m.group("args")))


def _kafka_send_parts(call_args: list[str] | tuple[str, ...], method_name: str = "send") -> dict[str, str | None]:
    parts = list(call_args)
    if not parts:
        return {"topic": None, "key": None, "payload": None, "pattern": method_name}
    producer_record = _inline_producer_record_parts(parts[0])
    if producer_record:
        return {**producer_record, "pattern": "producer_record_inline"}
    if method_name == "sendMessage":
        # Common local wrapper shape observed in real code: sendMessage(topic, keySupplier, message).
        return {"topic": parts[0] if len(parts) > 0 else None, "key": parts[1] if len(parts) > 1 else None, "payload": parts[2] if len(parts) > 2 else None, "pattern": "custom_send_message_topic_key_payload"}
    if len(parts) == 1:
        return {"topic": None, "key": None, "payload": parts[0], "pattern": "send_payload_only"}
    if len(parts) == 2:
        return {"topic": parts[0], "key": None, "payload": parts[1], "pattern": "send_topic_payload"}
    if len(parts) == 3:
        return {"topic": parts[0], "key": parts[1], "payload": parts[2], "pattern": "send_topic_key_payload"}
    if len(parts) == 4:
        return {"topic": parts[0], "key": parts[2], "payload": parts[3], "pattern": "send_topic_partition_key_payload"}
    return {"topic": parts[0], "key": parts[-2], "payload": parts[-1], "pattern": "send_extended_args"}




def _producer_record_parts_for_expression(method: JavaMethod, expr: str | None) -> dict[str, str | None] | None:
    direct = _inline_producer_record_parts(expr)
    if direct:
        return {**direct, "pattern": "producer_record_inline"}
    if not expr:
        return None
    cleaned = str(expr).strip()
    for assignment in method.assignments:
        if cleaned == assignment.target and "ProducerRecord" in (assignment.declared_type or ""):
            assigned = _inline_producer_record_parts(assignment.expression)
            if assigned:
                return {**assigned, "pattern": "producer_record_assigned_variable"}
    return None

def _payload_type_from_expression(method: JavaMethod, expr: str | None) -> tuple[str, list[str]]:
    if not expr:
        return "unknown", []
    cleaned = str(expr).strip()
    for param in method.params:
        if cleaned == param.name:
            return _normalize_java_type(param.type), ["method_parameter_type"]
    for assignment in method.assignments:
        if cleaned == assignment.target and assignment.declared_type:
            return _normalize_java_type(assignment.declared_type), ["local_variable_declared_type"]
    m = re.match(r'new\s+([A-Za-z0-9_.$]+)\s*(?:<[^>]*>)?\s*\(', cleaned)
    if m:
        return _normalize_java_type(m.group(1).split('.')[-1]), ["object_creation_type"]
    return "unknown", []


def _lambda_params_with_send_body(method: JavaMethod) -> set[str]:
    params: set[str] = set()
    for lam in method.lambdas:
        if not lam.params:
            continue
        body = lam.body or lam.text or ""
        for param in lam.params:
            if re.search(rf'\b{re.escape(param)}\s*\.\s*send(?:Message)?\s*\(', body):
                params.add(param)
    return params


def _is_kafka_send_call(method: JavaMethod, call: object, lambda_kafka_receivers: set[str]) -> bool:
    receiver = str(getattr(call, "receiver", None) or "")
    call_method = str(getattr(call, "method", "") or "")
    if call_method not in {"send", "sendMessage"}:
        return False
    receiver_low = receiver.lower()
    if any(tok in receiver_low for tok in ["kafka", "template", "producer", "publisher"]):
        return True
    if receiver in lambda_kafka_receivers:
        return True
    return False

def _rest_body_parameter(method: JavaMethod) -> dict[str, object] | None:
    for param in method.params:
        if any(a.name == "RequestBody" for a in param.annotations):
            return {
                "name": param.name,
                "java_type": _normalize_java_type(param.type),
                "source": "RequestBody",
            }
    return None


def _annotation_by_name(annotations: tuple[JavaAnnotation, ...], names: set[str]) -> JavaAnnotation | None:
    for ann in annotations:
        if ann.name in names:
            return ann
    return None


def _extract_path(mapping_args: str | None) -> str | None:
    if not mapping_args:
        return None
    for pat in [r'value\s*=\s*"([^"]+)"', r'path\s*=\s*"([^"]+)"', r'"([^"]+)"']:
        m = re.search(pat, mapping_args)
        if m:
            return m.group(1)
    return None


def _extract_request_schema(method: JavaMethod) -> str | None:
    for param in method.params:
        if any(a.name == "RequestBody" for a in param.annotations):
            return _normalize_java_type(param.type)
    for param in method.params:
        if any(a.name in {"PathVariable", "RequestParam", "RequestHeader"} for a in param.annotations):
            continue
        typ = _normalize_java_type(param.type)
        if typ not in {"HttpServletRequest", "HttpServletResponse", "Boolean", "String", "int", "long", "boolean"}:
            return typ
    return None


def _method_mapping_http_method(ann_name: str) -> str | None:
    if ann_name == "RequestMapping":
        return None
    return ann_name.replace("Mapping", "").upper() or None


def _method_evidence(path: Path, method: JavaMethod) -> list[EvidenceRef]:
    return [EvidenceRef(
        file_path=str(path),
        line_start=method.line_start,
        line_end=method.line_end,
        snippet=method.text[:1200],
        extractor=f"{JAVA_SYNTAX_EXTRACTOR}_method",
    )]


def _schema_source_type(parsed: JavaSyntaxFile, class_name: str, class_annotations: tuple[JavaAnnotation, ...]) -> str:
    low = class_name.lower()
    if any(x in low for x in ["request", "response", "dto", "event", "message", "rq", "rs"]):
        return "dto"
    if any(a.name in {"Entity", "Table"} for a in class_annotations):
        return "entity"
    if "@Entity" in parsed.text or "@Table" in parsed.text:
        return "entity"
    return "java_class"


def _kafka_topic_from_annotation(ann: JavaAnnotation) -> str:
    args = ann.arguments or ""
    # Prefer the explicit topics attribute. Generic path extraction would often pick
    # groupId/id first because @KafkaListener has several quoted attributes.
    m = re.search(r'\btopics\s*=\s*"([^"]+)"', args, re.DOTALL)
    if m:
        return m.group(1)
    m = re.search(r'\btopics\s*=\s*\{([^}]*)\}', args, re.DOTALL)
    if m:
        quoted = re.findall(r'"([^"]+)"', m.group(1))
        if quoted:
            return ",".join(quoted)
    m = re.search(r'\btopics\s*=\s*([^,\n]+)', args, re.DOTALL)
    if m:
        return " ".join(m.group(1).split()).strip()
    return _extract_path(args) or args[:120].replace("\n", " ")


def _annotation_literal_arg(ann: JavaAnnotation | None, key: str = "value") -> str | None:
    if not ann:
        return None
    args = ann.arguments or ""
    for pat in [rf"\b{re.escape(key)}\s*=\s*\"([^\"]+)\"", r'^\s*\"([^\"]+)\"\s*$']:
        m = re.search(pat, args)
        if m:
            return m.group(1)
    return None


def _jpa_table_identity(cls: object) -> dict[str, object]:
    table_ann = _annotation_by_name(getattr(cls, 'annotations', ()), {'Table'})
    entity_ann = _annotation_by_name(getattr(cls, 'annotations', ()), {'Entity'})
    table_name = _annotation_literal_arg(table_ann, 'name') or _annotation_literal_arg(entity_ann, 'name') or getattr(cls, 'name', None)
    schema_name = _annotation_literal_arg(table_ann, 'schema')
    normalized_table_name = normalize_name(table_name or '') if table_name else None
    qualified = f"{normalize_name(schema_name)}.{normalized_table_name}" if schema_name and normalized_table_name else normalized_table_name
    return {
        'entity_class': getattr(cls, 'name', None),
        'table_name': table_name,
        'normalized_table_name': normalized_table_name,
        'schema_name': schema_name,
        'qualified_table_name': qualified,
    }


def _jpa_join_columns(field: object) -> list[dict[str, object]]:
    out: list[dict[str, object]] = []
    for ann in getattr(field, 'annotations', ()):
        if ann.name == 'JoinColumn':
            out.append({
                'join_column': _annotation_literal_arg(ann, 'name'),
                'referenced_column': _annotation_literal_arg(ann, 'referencedColumnName'),
                'nullable': ann.bool_arg('nullable'),
                'annotation': ann.name,
                'annotation_arguments': ann.arguments,
            })
        elif ann.name == 'JoinColumns':
            for body in re.findall(r'@JoinColumn\s*\(([^)]*)\)', ann.text or ''):
                fake = JavaAnnotation(name='JoinColumn', text=body, arguments=body, line_start=ann.line_start, line_end=ann.line_end)
                out.append({
                    'join_column': _annotation_literal_arg(fake, 'name'),
                    'referenced_column': _annotation_literal_arg(fake, 'referencedColumnName'),
                    'nullable': fake.bool_arg('nullable'),
                    'annotation': 'JoinColumn',
                    'annotation_arguments': body,
                })
    return out


def _jpa_relationship_kind(ann_name: str) -> tuple[str, str]:
    if ann_name == 'ManyToOne':
        return 'many_to_one', 'many_to_one'
    if ann_name == 'OneToMany':
        return 'one_to_many', 'one_to_many'
    if ann_name == 'OneToOne':
        return 'one_to_one', 'one_to_one'
    if ann_name == 'ManyToMany':
        return 'many_to_many', 'many_to_many'
    return 'association', 'unknown'


def _mapped_by(ann: JavaAnnotation) -> str | None:
    return _annotation_literal_arg(ann, 'mappedBy')


def _target_entity(field_type: str | None) -> str | None:
    typ = _normalize_java_type(field_type)
    m = re.search(r'(?:List|Set|Collection)\s*<\s*([A-Za-z0-9_$.]+)', typ)
    if m:
        return m.group(1).split('.')[-1]
    return typ.split('.')[-1] if typ and typ != 'unknown' else None


def _rest_interface_contracts(parsed_files: list[JavaSyntaxFile]) -> dict[str, list[dict[str, object]]]:
    contracts: dict[str, list[dict[str, object]]] = {}
    for parsed in parsed_files:
        for cls in parsed.classes:
            if cls.kind != 'interface':
                continue
            class_mapping = _annotation_by_name(cls.annotations, REST_MAPPING_ANNOTATIONS)
            if not class_mapping:
                continue
            class_paths = _mapping_paths(class_mapping.arguments)
            for method in cls.methods:
                mapping = _annotation_by_name(method.annotations, REST_MAPPING_ANNOTATIONS)
                if not mapping:
                    continue
                method_paths = _mapping_paths(mapping.arguments)
                for class_path in class_paths:
                    for method_path in method_paths:
                        contracts.setdefault(cls.name, []).append({
                            'interface_name': cls.name,
                            'method_name': method.name,
                            'path': _join_paths(class_path, method_path),
                            'http_method': _request_mapping_http_method(mapping),
                            'request_schema': _extract_request_schema(method),
                            'request_params': _rest_request_parameters(method),
                            'request_body': _rest_body_parameter(method),
                            'response_schema': _normalize_java_type(method.return_type),
                            'interface_file': str(parsed.file),
                            'line_start': method.line_start,
                            'line_end': method.line_end,
                            'mapping_annotation': mapping.name,
                            'operation_summary': _semantic_annotation_props(method.annotations).get('description'),
                            'operation_description': _semantic_annotation_props(method.annotations).get('description'),
                        })
    return contracts


def scan_java_files(files: list[Path]) -> tuple[list[Fact], list[SchemaInfo], list[InterfaceInfo], list[RelationInfo], list[Fact], list[str]]:
    facts: list[Fact] = []
    schemas: list[SchemaInfo] = []
    interfaces: list[InterfaceInfo] = []
    relations: list[RelationInfo] = []
    mapper_facts: list[Fact] = []
    warnings: list[str] = []

    parsed_files, parse_warnings = parse_java_files(files)
    warnings.extend(parse_warnings)

    settings_property_map = _build_settings_property_map(list(parsed_files))
    consumer_props_topic_map = _build_consumer_props_topic_map(list(parsed_files), settings_property_map)
    rest_client_bindings = _build_rest_client_bindings(list(parsed_files))
    rest_interface_contract_map = _rest_interface_contracts(list(parsed_files))
    local_declared_types = {cls.name for parsed in parsed_files for cls in parsed.classes}
    consumer_props_by_class: dict[str, str] = {}
    for parsed in parsed_files:
        for cls in parsed.classes:
            sym = _constructor_consumer_props_symbol(cls)
            if sym:
                consumer_props_by_class[cls.name] = sym

    for sym, info in settings_property_map.items():
        facts.append(Fact(
            fact_type="settings_property_binding",
            name=sym,
            properties={"settings_symbol": sym, "property_key": info.get("property_key"), "binding_basis": "settings_enum_string_initializer", "syntax_provider": "tree_sitter"},
            evidence=[info["evidence"]] if info.get("evidence") else [],
        ))
    for sym, info in consumer_props_topic_map.items():
        facts.append(Fact(
            fact_type="kafka_consumer_props_topic_binding",
            name=sym,
            properties={
                "consumer_props_symbol": sym,
                "topic_settings_symbol": info.get("topic_settings_symbol"),
                "topic_property_key": info.get("topic_property_key"),
                "binding_basis": "consumer_props_enum_topic_argument",
                "syntax_provider": "tree_sitter",
            },
            evidence=[info["evidence"]] if info.get("evidence") else [],
        ))
    for class_name, bindings in rest_client_bindings.items():
        for binding in bindings:
            facts.append(Fact(
                fact_type="rest_client_properties_binding",
                name=class_name,
                properties={
                    "target_class": class_name,
                    "config_prefix": binding.get("config_prefix"),
                    "base_url_property_key": binding.get("base_url_property_key"),
                    "bean_factory_method": binding.get("bean_factory_method"),
                    "binding_basis": binding.get("binding_basis"),
                    "syntax_provider": "tree_sitter",
                },
                evidence=[EvidenceRef(file_path=str(binding.get("source_file")), line_start=int(binding.get("line_start") or 1), extractor=JAVA_SYNTAX_EXTRACTOR)],
            ))

    feign_client_classes: dict[str, dict[str, object]] = {}
    for parsed in parsed_files:
        for cls in parsed.classes:
            feign_ann = _annotation_by_name(cls.annotations, CLIENT_CLASS_ANNOTATIONS)
            if not feign_ann:
                continue
            props = _feign_client_props(feign_ann)
            feign_client_classes[cls.name] = {**props, "source_file": str(parsed.file), "line_start": cls.line_start}
            facts.append(Fact(
                fact_type="external_dependency",
                name=cls.name,
                properties={
                    "dependency_kind": "feign_client",
                    "client_class": cls.name,
                    "declared_name": props.get("name") or props.get("value"),
                    "declared_url": props.get("url"),
                    "declared_path": props.get("path"),
                    "context_id": props.get("contextId"),
                    "configuration": props.get("configuration"),
                    "source_set": _source_set_for_path(parsed.file),
                    "is_test_source": _is_test_source(parsed.file),
                    "evidence_maturity_level": "confirmed",
                    "syntax_provider": "tree_sitter",
                },
                evidence=[EvidenceRef(file_path=str(parsed.file), line_start=cls.line_start, line_end=cls.line_end, snippet=cls.text[:1000], extractor=JAVA_SYNTAX_EXTRACTOR)],
            ))

    for parsed in parsed_files:
        p = parsed.file
        text = parsed.text
        if parsed.parse_errors:
            warnings.append(f"tree-sitter reported {parsed.parse_errors} parse error node(s) in {p}")
        for cls in parsed.classes:
            # Schema fields for Java classes/records.
            fields: list[FieldInfo] = []
            for field in cls.fields:
                # Static class constants are implementation metadata, not serialized
                # instance fields of the DTO/schema. Generated OpenAPI models often
                # declare SERIALIZED_NAME_* constants next to the actual fields.
                if re.search(r"\bstatic\b", field.raw or ""):
                    continue
                typ = _clean_type(field.type)
                nested_type = None
                lm = re.search(r"(?:List|Set|Collection)\s*<\s*([A-Za-z0-9_]+)\s*>", typ)
                if lm:
                    nested_type = lm.group(1)
                semantic_props = _semantic_annotation_props(field.annotations)
                validation = _validation_constraints(field.annotations)
                serialization = _serialization_name_binding(field.name, field.annotations)
                field_annotations = [a.name for a in field.annotations]
                if validation:
                    field_annotations.extend([f"constraint:{v.get('annotation')}" for v in validation])
                fields.append(FieldInfo(
                    name=field.name,
                    type=typ,
                    description=semantic_props.get("description"),
                    nested_type=nested_type,
                    annotations=field_annotations,
                    serialized_name=str(serialization.get("serialized_name") or field.name),
                    serialized_name_basis=str(serialization.get("serialized_name_basis") or "java_field_name_default"),
                    serialization_library=serialization.get("serialization_library"),
                    serialization_aliases=[str(x) for x in serialization.get("serialization_aliases") or []],
                    evidence=[EvidenceRef(
                        file_path=str(p),
                        line_start=field.line_start,
                        line_end=field.line_end,
                        snippet=field.raw[:1000],
                        extractor=JAVA_SYNTAX_EXTRACTOR,
                    )],
                ))
                if semantic_props.get("description") or validation:
                    facts.append(Fact(
                        fact_type="data_dictionary_entry",
                        name=f"{cls.name}.{field.name}",
                        properties={
                            "entry_kind": "java_field",
                            "container_name": cls.name,
                            "attribute_name": field.name,
                            "attribute_type": typ,
                            "description": semantic_props.get("description"),
                            "constraints": validation,
                            "source_type": "java_semantic_annotation",
                            "source_set": _source_set_for_path(p),
                            "is_test_source": _is_test_source(p),
                            "evidence_maturity_level": "confirmed",
                            "syntax_provider": "tree_sitter",
                        },
                        evidence=[EvidenceRef(file_path=str(p), line_start=field.line_start, line_end=field.line_end, snippet=field.raw[:1000], extractor=JAVA_SYNTAX_EXTRACTOR)],
                    ))
            if fields:
                class_semantic_props = _semantic_annotation_props(cls.annotations)
                schemas.append(SchemaInfo(
                    name=cls.name,
                    source_type=_schema_source_type(parsed, cls.name, cls.annotations),
                    fields=fields,
                    evidence=[EvidenceRef(file_path=str(p), line_start=cls.line_start, line_end=cls.line_end, snippet=cls.name, extractor=JAVA_SYNTAX_EXTRACTOR)],
                    comments=[class_semantic_props.get("description")] if class_semantic_props.get("description") else [],
                ))
                if class_semantic_props.get("description"):
                    facts.append(Fact(
                        fact_type="data_dictionary_entry",
                        name=cls.name,
                        properties={
                            "entry_kind": "java_schema",
                            "container_name": cls.name,
                            "description": class_semantic_props.get("description"),
                            "source_type": "java_semantic_annotation",
                            "source_set": _source_set_for_path(p),
                            "is_test_source": _is_test_source(p),
                            "evidence_maturity_level": "confirmed",
                            "syntax_provider": "tree_sitter",
                        },
                        evidence=[EvidenceRef(file_path=str(p), line_start=cls.line_start, line_end=cls.line_end, snippet=cls.text[:1000], extractor=JAVA_SYNTAX_EXTRACTOR)],
                    ))

            entity_ann = _annotation_by_name(cls.annotations, {"Entity"})
            table_ann = _annotation_by_name(cls.annotations, {"Table"})
            if entity_ann or table_ann:
                table_identity = _jpa_table_identity(cls)
                facts.append(Fact(
                    fact_type="jpa_entity",
                    name=cls.name,
                    properties={
                        **table_identity,
                        "source_set": _source_set_for_path(p),
                        "is_test_source": _is_test_source(p),
                        "evidence_maturity_level": "confirmed",
                        "evidence_level": "declared",
                        "syntax_provider": "tree_sitter",
                    },
                    evidence=[EvidenceRef(file_path=str(p), line_start=cls.line_start, line_end=cls.line_end, snippet=cls.name, extractor=JAVA_SYNTAX_EXTRACTOR)],
                ))

            inheritance_ann = _annotation_by_name(cls.annotations, {"Inheritance"})
            discriminator_col_ann = _annotation_by_name(cls.annotations, {"DiscriminatorColumn"})
            discriminator_value_ann = _annotation_by_name(cls.annotations, {"DiscriminatorValue"})
            if inheritance_ann or discriminator_col_ann or discriminator_value_ann or cls.extends:
                if inheritance_ann or discriminator_col_ann or discriminator_value_ann:
                    facts.append(Fact(
                        fact_type="jpa_inheritance",
                        name=cls.name,
                        properties={
                            "entity_class": cls.name,
                            "parent_class": cls.extends,
                            "inheritance_strategy": (inheritance_ann.arguments if inheritance_ann else None),
                            "discriminator_column": _annotation_literal_arg(discriminator_col_ann, "name"),
                            "discriminator_value": _annotation_literal_arg(discriminator_value_ann, "value"),
                            "table_identity": _jpa_table_identity(cls),
                            "source_set": _source_set_for_path(p),
                            "is_test_source": _is_test_source(p),
                            "evidence_maturity_level": "confirmed",
                            "evidence_level": "declared",
                            "syntax_provider": "tree_sitter",
                        },
                        evidence=[EvidenceRef(file_path=str(p), line_start=cls.line_start, line_end=cls.line_end, snippet=cls.text[:1000], extractor=JAVA_SYNTAX_EXTRACTOR)],
                    ))

            for field in cls.fields:
                rel_ann = _annotation_by_name(field.annotations, {"ManyToOne", "OneToMany", "OneToOne", "ManyToMany"})
                if not rel_ann:
                    continue
                relationship_kind, cardinality = _jpa_relationship_kind(rel_ann.name)
                join_columns = _jpa_join_columns(field)
                target_entity = _target_entity(field.type)
                facts.append(Fact(
                    fact_type="jpa_relationship",
                    name=f"{cls.name}.{field.name}->{target_entity or field.type}",
                    properties={
                        "source_entity": cls.name,
                        "source_field": field.name,
                        "source_table_identity": _jpa_table_identity(cls),
                        "target_entity": target_entity,
                        "target_type": _normalize_java_type(field.type),
                        "relationship_kind": relationship_kind,
                        "cardinality": cardinality,
                        "mapped_by": _mapped_by(rel_ann),
                        "join_columns": join_columns,
                        "optional": rel_ann.bool_arg("optional"),
                        "fetch": (re.search(r"fetch\s*=\s*FetchType\.([A-Z_]+)", rel_ann.arguments or "") or [None, None])[1],
                        "source_set": _source_set_for_path(p),
                        "is_test_source": _is_test_source(p),
                        "evidence_maturity_level": "confirmed",
                        "evidence_level": "declared",
                        "relationship_evidence_kind": "jpa_annotation",
                        "syntax_provider": "tree_sitter",
                    },
                    evidence=[EvidenceRef(file_path=str(p), line_start=field.line_start, line_end=field.line_end, snippet=field.raw[:1000], extractor=JAVA_SYNTAX_EXTRACTOR)],
                ))

            # Swagger/OpenAPI/Javadoc-ish semantic annotation facts.
            for ann in list(cls.annotations) + [a for m in cls.methods for a in m.annotations] + [a for f in cls.fields for a in f.annotations]:
                if ann.name in ANNOT_DESC_NAMES:
                    facts.append(Fact(
                        fact_type="semantic_annotation",
                        name=f"{cls.name}:{ann.name}",
                        properties={"annotation": ann.name, "content": (ann.arguments or ann.text)[:500], "description": _semantic_description((ann,)), "syntax_provider": "tree_sitter"},
                        evidence=[EvidenceRef(file_path=str(p), line_start=ann.line_start, line_end=ann.line_end, snippet=snippet_around(text, ann.line_start), extractor=JAVA_SYNTAX_EXTRACTOR)],
                    ))

            rest_class = any(a.name in REST_CLASS_ANNOTATIONS for a in cls.annotations)
            grpc_class = any(a.name == GRPC_SERVICE_ANNOTATION for a in cls.annotations)
            grpc_service_name = _grpc_service_name(cls) if grpc_class else None
            callback_interfaces = _callback_interface_candidates(cls, local_declared_types)
            class_mapping = _annotation_by_name(cls.annotations, REST_MAPPING_ANNOTATIONS)
            class_paths = _mapping_paths(class_mapping.arguments if class_mapping else None)
            source_set = _source_set_for_path(p)
            is_test_source = source_set == "test"
            class_constants = _class_string_constants(cls)
            class_field_types = {field.name: _normalize_java_type(field.type).split('<', 1)[0] for field in cls.fields}
            class_rest_bindings = rest_client_bindings.get(cls.name) or []
            class_consumer_props_symbol = consumer_props_by_class.get(cls.name)
            class_consumer_topic_binding = consumer_props_topic_map.get(class_consumer_props_symbol or "") if class_consumer_props_symbol else None
            if grpc_class:
                facts.append(Fact(
                    fact_type="grpc_service_declaration",
                    name=str(grpc_service_name or cls.name),
                    properties={
                        "implementation_class": cls.name,
                        "service_interface": grpc_service_name,
                        "annotation": GRPC_SERVICE_ANNOTATION,
                        "source_set": source_set,
                        "is_test_source": is_test_source,
                        "evidence_maturity_level": "confirmed",
                        "syntax_provider": "tree_sitter",
                    },
                    evidence=[EvidenceRef(file_path=str(p), line_start=cls.line_start, line_end=cls.line_end, snippet=cls.text[:1000], extractor=JAVA_SYNTAX_EXTRACTOR)],
                ))
            for callback_interface in callback_interfaces:
                facts.append(Fact(
                    fact_type="framework_callback_implementation",
                    name=f"{callback_interface}->{cls.name}",
                    properties={
                        "interface_name": callback_interface,
                        "implementation_class": cls.name,
                        "interface_source_status": "not_declared_in_repository",
                        "observation_kind": "implemented_external_interface_name",
                        "source_set": source_set,
                        "is_test_source": is_test_source,
                        "evidence_maturity_level": "observed",
                        "syntax_provider": "tree_sitter",
                    },
                    evidence=[EvidenceRef(file_path=str(p), line_start=cls.line_start, line_end=cls.line_end, snippet=cls.text[:1000], extractor=JAVA_SYNTAX_EXTRACTOR)],
                ))
            if rest_class and cls.implements:
                impl_method_names = {m.name for m in cls.methods}
                for iface in cls.implements:
                    for contract in rest_interface_contract_map.get(iface, []):
                        if contract.get("method_name") not in impl_method_names and impl_method_names:
                            continue
                        path_value = contract.get("path")
                        http_method = contract.get("http_method")
                        return_type = str(contract.get("response_schema") or "unknown")
                        req_schema = contract.get("request_schema")
                        request_params = contract.get("request_params") or []
                        request_body = contract.get("request_body")
                        op = f"{cls.name}.{contract.get('method_name')}"
                        evidence = [EvidenceRef(file_path=str(contract.get("interface_file")), line_start=contract.get("line_start"), line_end=contract.get("line_end"), extractor=f"{JAVA_SYNTAX_EXTRACTOR}_interface_rest_contract")]
                        method_props = {
                            "source_set": source_set,
                            "is_test_source": is_test_source,
                            "syntax_provider": "tree_sitter",
                            "declared_on_interface": iface,
                            "implemented_by_class": cls.name,
                            "interface_contract_basis": "request_mapping_on_interface_rest_controller_on_implementation",
                            "request_parameters": request_params,
                            "request_body": request_body,
                            "operation_summary": contract.get("operation_summary"),
                            "operation_description": contract.get("operation_description"),
                        }
                        if req_schema or request_params:
                            interfaces.append(InterfaceInfo(
                                name=f"{op} request",
                                direction=Direction.INBOUND,
                                kind=InterfaceKind.REST,
                                schema_ref=str(req_schema or "method_parameters"),
                                operation=op,
                                path=str(path_value) if path_value else None,
                                method=str(http_method) if http_method else None,
                                evidence=evidence,
                                properties={**method_props, "boundary_role": "rest_request"},
                            ))
                        interfaces.append(InterfaceInfo(
                            name=op,
                            direction=Direction.OUTBOUND,
                            kind=InterfaceKind.REST,
                            schema_ref=return_type,
                            operation=op,
                            path=str(path_value) if path_value else None,
                            method=str(http_method) if http_method else None,
                            evidence=evidence,
                            properties={**method_props, "boundary_role": "rest_response"},
                        ))
                        if req_schema:
                            relations.append(RelationInfo(
                                source=str(req_schema),
                                target=return_type,
                                relation_type="same_rest_operation",
                                evidence=evidence,
                                properties={"operation": op, "path": path_value, "syntax_provider": "tree_sitter", "declared_on_interface": iface},
                            ))
            for method in cls.methods:
                if grpc_class and method.name not in {"<init>", cls.name}:
                    request_param = method.params[0] if method.params else None
                    request_type = _unwrap_transport_payload_type(request_param.type) if request_param else "method_parameters"
                    response_type = _unwrap_transport_payload_type(method.return_type)
                    grpc_path = f"{grpc_service_name or cls.name}/{method.name}"
                    evidence = _method_evidence(p, method)
                    interfaces.append(InterfaceInfo(
                        name=f"{grpc_path} request",
                        direction=Direction.INBOUND,
                        kind=InterfaceKind.GRPC,
                        schema_ref=request_type,
                        operation=method.operation,
                        path=grpc_path,
                        method=method.name,
                        evidence=evidence,
                        properties={
                            "boundary_role": "grpc_request",
                            "service_interface": grpc_service_name,
                            "implementation_class": cls.name,
                            "declared_request_type": _normalize_java_type(request_param.type) if request_param else None,
                            "request_payload_type": request_type,
                            "request_parameter": request_param.name if request_param else None,
                            "source_set": source_set,
                            "is_test_source": is_test_source,
                            "syntax_provider": "tree_sitter",
                        },
                    ))
                    if response_type not in {"void", "unknown"}:
                        interfaces.append(InterfaceInfo(
                            name=f"{grpc_path} response",
                            direction=Direction.OUTBOUND,
                            kind=InterfaceKind.GRPC,
                            schema_ref=response_type,
                            operation=method.operation,
                            path=grpc_path,
                            method=method.name,
                            evidence=evidence,
                            properties={
                                "boundary_role": "grpc_response",
                                "service_interface": grpc_service_name,
                                "implementation_class": cls.name,
                                "declared_response_type": _normalize_java_type(method.return_type),
                                "response_payload_type": response_type,
                                "source_set": source_set,
                                "is_test_source": is_test_source,
                                "syntax_provider": "tree_sitter",
                            },
                        ))

                if callback_interfaces and _method_has_override(method):
                    request_param = method.params[0] if len(method.params) == 1 else None
                    request_type = _unwrap_transport_payload_type(request_param.type) if request_param else "method_parameters"
                    request_parameters = [
                        {"name": param.name, "type": _normalize_java_type(param.type)}
                        for param in method.params
                    ]
                    response_type = _unwrap_transport_payload_type(method.return_type)
                    for callback_interface in callback_interfaces:
                        callback_path = f"{callback_interface}/{method.name}"
                        evidence = _method_evidence(p, method)
                        interfaces.append(InterfaceInfo(
                            name=f"{callback_path} request",
                            direction=Direction.INBOUND,
                            kind=InterfaceKind.CALLBACK,
                            schema_ref=request_type,
                            operation=method.operation,
                            path=callback_path,
                            method=method.name,
                            evidence=evidence,
                            properties={
                                "boundary_role": "framework_callback_request",
                                "callback_interface": callback_interface,
                                "implementation_class": cls.name,
                                "interface_source_status": "not_declared_in_repository",
                                "request_payload_type": request_type,
                                "request_parameter": request_param.name if request_param else None,
                                "request_parameters": request_parameters,
                                "source_set": source_set,
                                "is_test_source": is_test_source,
                                "syntax_provider": "tree_sitter",
                            },
                        ))
                        if response_type not in {"void", "unknown"}:
                            interfaces.append(InterfaceInfo(
                                name=f"{callback_path} response",
                                direction=Direction.OUTBOUND,
                                kind=InterfaceKind.CALLBACK,
                                schema_ref=response_type,
                                operation=method.operation,
                                path=callback_path,
                                method=method.name,
                                evidence=evidence,
                                properties={
                                    "boundary_role": "framework_callback_response",
                                    "callback_interface": callback_interface,
                                    "implementation_class": cls.name,
                                    "interface_source_status": "not_declared_in_repository",
                                    "response_payload_type": response_type,
                                    "source_set": source_set,
                                    "is_test_source": is_test_source,
                                    "syntax_provider": "tree_sitter",
                                },
                            ))

                mapping = _annotation_by_name(method.annotations, REST_MAPPING_ANNOTATIONS)
                if rest_class and mapping:
                    method_paths = _mapping_paths(mapping.arguments)
                    return_type = _normalize_java_type(method.return_type)
                    req_schema = _extract_request_schema(method)
                    request_params = _rest_request_parameters(method)
                    request_body = _rest_body_parameter(method)
                    op = method.operation
                    http_method = _request_mapping_http_method(mapping)
                    propagation = _request_field_propagation(method)
                    evidence = _method_evidence(p, method)
                    for class_path in class_paths:
                        for method_path in method_paths:
                            full_path = _join_paths(class_path, method_path)
                            mapping_name = f"{mapping.name} {full_path or ''}".strip()
                            method_props = {
                                "method_snippet": method.text[:6000],
                                "method_line_start": method.line_start,
                                "method_line_end": method.line_end,
                                "class_path": class_path,
                                "method_path": method_path,
                                "full_path_basis": "class_and_method_mapping" if class_path and method_path else ("class_mapping" if class_path else "method_mapping"),
                                "request_field_propagation": propagation,
                                "request_parameters": request_params,
                                "request_body_parameter": request_body,
                                "operation_summary": _semantic_annotation_props(method.annotations).get("description"),
                                "operation_description": _semantic_annotation_props(method.annotations).get("description"),
                                "source_set": source_set,
                                "is_test_source": is_test_source,
                                "syntax_provider": "tree_sitter",
                            }
                            if req_schema or request_params:
                                interfaces.append(InterfaceInfo(
                                    name=f"{mapping_name} request",
                                    direction=Direction.INBOUND,
                                    kind=InterfaceKind.REST,
                                    schema_ref=req_schema or "method_parameters",
                                    operation=op,
                                    path=full_path,
                                    method=http_method,
                                    evidence=evidence,
                                    properties={**method_props, "boundary_role": "rest_request"},
                                ))
                            interfaces.append(InterfaceInfo(
                                name=mapping_name,
                                direction=Direction.OUTBOUND,
                                kind=InterfaceKind.REST,
                                schema_ref=return_type,
                                operation=op,
                                path=full_path,
                                method=http_method,
                                evidence=evidence,
                                properties={**method_props, "boundary_role": "rest_response"},
                            ))
                            if req_schema:
                                relations.append(RelationInfo(
                                    source=req_schema,
                                    target=return_type,
                                    relation_type="same_rest_operation",
                                    evidence=evidence,
                                    properties={"operation": op, "path": full_path, "request_field_propagation": propagation, "syntax_provider": "tree_sitter"},
                                ))

                kafka_ann = _annotation_by_name(method.annotations, {KAFKA_LISTENER_ANNOTATION})
                if kafka_ann:
                    topic = _kafka_topic_from_annotation(kafka_ann)
                    kafka_topic_binding = None
                    if class_consumer_topic_binding and "__listener.props.getTopic" in (kafka_ann.arguments or kafka_ann.text or ""):
                        kafka_topic_binding = {
                            "consumer_props_symbol": class_consumer_props_symbol,
                            "settings_symbol": class_consumer_topic_binding.get("topic_settings_symbol"),
                            "property_key": class_consumer_topic_binding.get("topic_property_key"),
                            "binding_basis": "kafka_listener_spel_listener_props_consumer_props_settings",
                        }
                    method_info = method_syntax_dict(method)
                    kafka_payload = _kafka_payload_type_from_method_info(method_info)
                    declared_schema = _normalize_java_type(method.params[0].type) if method.params else "Message"
                    schema = kafka_payload.get("payload_type") or declared_schema
                    payload_status = str(kafka_payload.get("status") or "not_found")
                    if payload_status == "not_found":
                        payload_status = "declared_parameter_type"
                    interfaces.append(InterfaceInfo(
                        name=topic,
                        direction=Direction.INBOUND,
                        kind=InterfaceKind.KAFKA,
                        schema_ref=schema or "unknown",
                        operation=method.operation,
                        evidence=[EvidenceRef(file_path=str(p), line_start=kafka_ann.line_start, line_end=method.line_end, snippet=method.text[:1200], extractor=JAVA_SYNTAX_EXTRACTOR)],
                        properties={
                            "syntax_provider": "tree_sitter",
                            "declared_payload_type": declared_schema,
                            "payload_resolution_status": payload_status,
                            "payload_resolution_basis": list(kafka_payload.get("basis") or []),
                            "topic_expression": topic,
                            "topic_property_key": (kafka_topic_binding or {}).get("property_key"),
                            "topic_settings_symbol": (kafka_topic_binding or {}).get("settings_symbol"),
                            "consumer_props_symbol": (kafka_topic_binding or {}).get("consumer_props_symbol"),
                            "topic_resolution_basis": (kafka_topic_binding or {}).get("binding_basis"),
                            "boundary_role": "kafka_consume",
                            "source_set": source_set,
                            "is_test_source": is_test_source,
                        },
                    ))

                # Kafka sends / producer records use Tree-sitter call/object nodes.
                lambda_kafka_receivers = _lambda_params_with_send_body(method)
                for call in [c for c in method.calls if _is_kafka_send_call(method, c, lambda_kafka_receivers)]:
                    send_parts = _kafka_send_parts(call.args, call.method)
                    assigned_record_parts = _producer_record_parts_for_expression(method, send_parts.get("payload"))
                    if assigned_record_parts:
                        send_parts = assigned_record_parts
                    topic = send_parts.get("topic") or "unknown"
                    topic_binding = _method_local_setting_binding(method, topic, settings_property_map)
                    key_expr = send_parts.get("key")
                    payload_expr = send_parts.get("payload")
                    payload_type, payload_basis = _payload_type_from_expression(method, payload_expr)
                    interfaces.append(InterfaceInfo(
                        name=str(topic)[:160],
                        direction=Direction.OUTBOUND,
                        kind=InterfaceKind.KAFKA,
                        schema_ref=payload_type,
                        operation=method.operation,
                        evidence=[EvidenceRef(file_path=str(p), line_start=call.line_start, snippet=call.text[:1200], extractor=JAVA_SYNTAX_EXTRACTOR)],
                        properties={
                            "payload_expression": payload_expr,
                            "message_key_expression": key_expr,
                            "send_pattern": send_parts.get("pattern"),
                            "topic_expression": topic,
                            "topic_property_key": (topic_binding or {}).get("property_key"),
                            "topic_settings_symbol": (topic_binding or {}).get("settings_symbol"),
                            "topic_resolution_basis": (topic_binding or {}).get("binding_basis"),
                            "payload_resolution_basis": payload_basis,
                            "boundary_role": "kafka_publish",
                            "source_set": source_set,
                            "is_test_source": is_test_source,
                            "syntax_provider": "tree_sitter",
                        },
                    ))
                    facts.append(Fact(
                        fact_type="kafka_send_call",
                        name=str(topic)[:160],
                        properties={
                            "args": call.args_text[:500],
                            "topic_expression": topic,
                            "topic_property_key": (topic_binding or {}).get("property_key"),
                            "topic_settings_symbol": (topic_binding or {}).get("settings_symbol"),
                            "topic_resolution_basis": (topic_binding or {}).get("binding_basis"),
                            "message_key_expression": key_expr,
                            "payload_expression": payload_expr,
                            "payload_type": payload_type,
                            "send_pattern": send_parts.get("pattern"),
                            "operation": method.operation,
                            "source_set": source_set,
                            "is_test_source": is_test_source,
                            "syntax_provider": "tree_sitter",
                        },
                        evidence=[EvidenceRef(file_path=str(p), line_start=call.line_start, snippet=call.text[:1200], extractor=JAVA_SYNTAX_EXTRACTOR)],
                    ))
                for creation in [c for c in method.object_creations if c.type.split(".")[-1] == "ProducerRecord"]:
                    pr_parts = _producer_record_parts(creation.args)
                    pr_topic_binding = _method_local_setting_binding(method, pr_parts.get("topic"), settings_property_map)
                    payload_type, payload_basis = _payload_type_from_expression(method, pr_parts.get("payload"))
                    facts.append(Fact(
                        fact_type="producer_record_creation",
                        name=creation.args_text[:120],
                        properties={
                            "args": creation.args_text[:500],
                            "topic_expression": pr_parts.get("topic"),
                            "topic_property_key": (pr_topic_binding or {}).get("property_key"),
                            "topic_settings_symbol": (pr_topic_binding or {}).get("settings_symbol"),
                            "topic_resolution_basis": (pr_topic_binding or {}).get("binding_basis"),
                            "message_key_expression": pr_parts.get("key"),
                            "payload_expression": pr_parts.get("payload"),
                            "payload_type": payload_type,
                            "payload_resolution_basis": payload_basis,
                            "operation": method.operation,
                            "source_set": source_set,
                            "is_test_source": is_test_source,
                            "syntax_provider": "tree_sitter",
                        },
                        evidence=[EvidenceRef(file_path=str(p), line_start=creation.line_start, snippet=creation.text[:1200], extractor=JAVA_SYNTAX_EXTRACTOR)],
                    ))

                # HTTP/REST client outbound calls with direct receiver-type evidence.
                for call in method.calls:
                    receiver = (call.receiver or "").strip()
                    if not receiver:
                        continue
                    receiver_type = class_field_types.get(receiver)
                    if receiver_type not in {"RestClient", "RestTemplate", "WebClient"}:
                        continue
                    http_parts = _http_outbound_parts(method, call, class_constants)
                    if not http_parts:
                        continue
                    http_binding_status = "not_resolved"
                    http_base_property_key = None
                    http_base_config_prefixes: list[str] = []
                    if len(class_rest_bindings) == 1:
                        http_binding_status = "resolved_single_bean_configuration_properties"
                        http_base_property_key = class_rest_bindings[0].get("base_url_property_key")
                        http_base_config_prefixes = [str(class_rest_bindings[0].get("config_prefix"))]
                    elif len(class_rest_bindings) > 1:
                        http_binding_status = "ambiguous_multiple_bean_configuration_properties"
                        http_base_config_prefixes = [str(x.get("config_prefix")) for x in class_rest_bindings if x.get("config_prefix")]
                    endpoint_name = str(http_parts.get("url_resolved") or http_parts.get("url_expression") or "unknown")[:160]
                    interfaces.append(InterfaceInfo(
                        name=endpoint_name,
                        direction=Direction.OUTBOUND,
                        kind=InterfaceKind.REST,
                        schema_ref=str(http_parts.get("response_payload_type") or "unknown"),
                        operation=method.operation,
                        path=str(http_parts.get("url_resolved") or http_parts.get("url_expression") or ""),
                        method=str(http_parts.get("http_method") or "") or None,
                        evidence=[EvidenceRef(file_path=str(p), line_start=call.line_start, snippet=call.text[:1200], extractor=JAVA_SYNTAX_EXTRACTOR)],
                        properties={
                            "boundary_role": "http_outbound",
                            "client_receiver": receiver,
                            "client_receiver_type": receiver_type,
                            "client_call_pattern": http_parts.get("client_call_pattern"),
                            "endpoint_expression": http_parts.get("url_expression"),
                            "endpoint_path": http_parts.get("url_resolved"),
                            "endpoint_path_resolution_basis": http_parts.get("url_resolution_basis"),
                            "endpoint_path_symbol": http_parts.get("url_symbol"),
                            "base_config_prefixes": http_base_config_prefixes,
                            "base_url_property_key": http_base_property_key,
                            "base_url_resolution_status": http_binding_status,
                            "request_payload_expression": http_parts.get("request_payload_expression"),
                            "request_payload_type": http_parts.get("request_payload_type"),
                            "request_payload_resolution_basis": http_parts.get("request_payload_resolution_basis"),
                            "response_payload_type": http_parts.get("response_payload_type"),
                            "source_set": source_set,
                            "is_test_source": is_test_source,
                            "syntax_provider": "tree_sitter",
                        },
                    ))
                    facts.append(Fact(
                        fact_type="http_outbound_call",
                        name=endpoint_name,
                        properties={
                            "operation": method.operation,
                            "http_method": http_parts.get("http_method"),
                            "endpoint_expression": http_parts.get("url_expression"),
                            "endpoint_path": http_parts.get("url_resolved"),
                            "endpoint_path_resolution_basis": http_parts.get("url_resolution_basis"),
                            "endpoint_path_symbol": http_parts.get("url_symbol"),
                            "client_receiver": receiver,
                            "client_receiver_type": receiver_type,
                            "client_call_pattern": http_parts.get("client_call_pattern"),
                            "base_config_prefixes": http_base_config_prefixes,
                            "base_url_property_key": http_base_property_key,
                            "base_url_resolution_status": http_binding_status,
                            "request_payload_expression": http_parts.get("request_payload_expression"),
                            "request_payload_type": http_parts.get("request_payload_type"),
                            "response_payload_type": http_parts.get("response_payload_type"),
                            "source_set": source_set,
                            "is_test_source": is_test_source,
                            "syntax_provider": "tree_sitter",
                        },
                        evidence=[EvidenceRef(file_path=str(p), line_start=call.line_start, snippet=call.text[:1200], extractor=JAVA_SYNTAX_EXTRACTOR)],
                    ))

                # Generic external dependency calls for system-description evidence.
                for call in method.calls:
                    receiver = (call.receiver or "").strip()
                    receiver_type = class_field_types.get(receiver)
                    dependency_kind = _external_call_kind(receiver_type, receiver)
                    if not dependency_kind:
                        continue
                    facts.append(Fact(
                        fact_type="external_dependency_call",
                        name=f"{receiver_type or receiver}.{call.method}",
                        properties={
                            "dependency_kind": dependency_kind,
                            "client_receiver": receiver,
                            "client_receiver_type": receiver_type,
                            "method": call.method,
                            "operation": method.operation,
                            "arguments_preview": call.args_text[:500],
                            "source_set": source_set,
                            "is_test_source": is_test_source,
                            "evidence_maturity_level": "confirmed",
                            "syntax_provider": "tree_sitter",
                        },
                        evidence=[EvidenceRef(file_path=str(p), line_start=call.line_start, line_end=call.line_end, snippet=call.text[:1000], extractor=JAVA_SYNTAX_EXTRACTOR)],
                    ))

                # mapper-like facts from Tree-sitter call nodes.
                method_info = method_syntax_dict(method)
                for binding in _tree_sitter_setter_bindings(method_info):
                    mapper_fact = Fact(
                        fact_type="setter_getter_mapping",
                        name=f"{binding.get('source_parameter')}.get{_upper_first(binding.get('source_field'))} -> {binding.get('target_variable')}.set{_upper_first(binding.get('target_field'))}",
                        properties={"target_var": binding.get("target_variable"), "target_field": binding.get("target_field"), "source_var": binding.get("source_parameter"), "source_field": binding.get("source_field"), "class": cls.name, "operation": method.operation, "syntax_provider": "tree_sitter"},
                        evidence=[EvidenceRef(file_path=str(p), line_start=method.line_start, line_end=method.line_end, snippet=method.text[:1200], extractor=JAVA_SYNTAX_EXTRACTOR)],
                    )
                    mapper_facts.append(mapper_fact)
                    facts.append(Fact(
                        fact_type="attribute_derivation",
                        name=f"{method.operation}:{binding.get('target_field')}",
                        properties={"target_object": binding.get("target_variable"), "target_field": binding.get("target_field"), "source_object": binding.get("source_parameter"), "source_fields": [binding.get("source_field")], "expression_kind": "direct_mapping", "derivation_kind": "setter_getter_mapping", "operation": method.operation, "evidence_maturity_level": "confirmed", "syntax_provider": "tree_sitter"},
                        evidence=mapper_fact.evidence,
                    ))
                for binding in _tree_sitter_builder_bindings(method_info):
                    mapper_fact = Fact(
                        fact_type="builder_mapping",
                        name=f"{binding.get('source_parameter')}.get{_upper_first(binding.get('source_field'))} -> builder.{binding.get('target_field')}",
                        properties={"target_field": binding.get("target_field"), "source_var": binding.get("source_parameter"), "source_field": binding.get("source_field"), "class": cls.name, "operation": method.operation, "syntax_provider": "tree_sitter"},
                        evidence=[EvidenceRef(file_path=str(p), line_start=method.line_start, line_end=method.line_end, snippet=method.text[:1200], extractor=JAVA_SYNTAX_EXTRACTOR)],
                    )
                    mapper_facts.append(mapper_fact)
                    if str(binding.get("source_field") or "").lower() not in {"class"} and str(binding.get("target_field") or "").lower() not in {"run", "start", "stop"}:
                        facts.append(Fact(
                            fact_type="attribute_derivation",
                            name=f"{method.operation}:{binding.get('target_field')}",
                            properties={"target_object": "builder", "target_field": binding.get("target_field"), "source_object": binding.get("source_parameter"), "source_fields": [binding.get("source_field")], "expression_kind": "direct_mapping", "derivation_kind": "builder_mapping", "operation": method.operation, "evidence_maturity_level": "confirmed", "syntax_provider": "tree_sitter"},
                            evidence=mapper_fact.evidence,
                        ))

            # MapStruct mappings are usually annotation-driven declarations; keep extraction over parsed class text.
            for ann in [a for m in cls.methods for a in m.annotations]:
                if ann.name == "Mapping":
                    src = re.search(r'source\s*=\s*"([^"]+)"', ann.arguments or "")
                    tgt = re.search(r'target\s*=\s*"([^"]+)"', ann.arguments or "")
                    if src and tgt:
                        mapper_fact = Fact(
                            fact_type="mapstruct_mapping",
                            name=f"{src.group(1)} -> {tgt.group(1)}",
                            properties={"source_field": src.group(1), "target_field": tgt.group(1), "class": cls.name, "operation": method.operation, "syntax_provider": "tree_sitter"},
                            evidence=[EvidenceRef(file_path=str(p), line_start=ann.line_start, line_end=ann.line_end, snippet=snippet_around(text, ann.line_start), extractor=JAVA_SYNTAX_EXTRACTOR)],
                        )
                        mapper_facts.append(mapper_fact)
                        facts.append(Fact(
                            fact_type="attribute_derivation",
                            name=f"{cls.name}:{tgt.group(1)}",
                            properties={"target_field": tgt.group(1), "source_fields": [src.group(1)], "expression_kind": "direct_mapping", "derivation_kind": "mapstruct_mapping", "operation": method.operation, "evidence_maturity_level": "confirmed", "syntax_provider": "tree_sitter"},
                            evidence=mapper_fact.evidence,
                        ))

    return facts, schemas, interfaces, relations, mapper_facts, warnings
