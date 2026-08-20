from __future__ import annotations

import ast
import re
import hashlib
from pathlib import Path
from typing import Any

from code_analyzer_core.models import (
    Fact,
    EvidenceRef,
    SchemaInfo,
    FieldInfo,
    InterfaceInfo,
    RelationInfo,
    Direction,
    InterfaceKind,
)
from code_analyzer_core.utils import read_text, snippet_around
from code_analyzer_core.evidence_contract import maturity_props, candidate_signal

HTTP_METHODS = {"get", "post", "put", "patch", "delete", "route"}
REQUEST_CLIENT_NAMES = {"requests", "httpx", "aiohttp"}
DB_WRITE_NAMES = {"insert", "insert_one", "insert_many", "update", "update_one", "update_many", "upsert", "save", "add", "create", "bulk_create", "merge", "execute", "executemany", "commit", "delete", "delete_one", "delete_many"}
DB_READ_PREFIXES = ("find", "get", "select", "query", "fetch", "load", "count", "exists")
KAFKA_SEND_NAMES = {"send", "send_and_wait", "produce", "publish"}
IDENTIFIER_FIELD_NAMES = {"card", "cards", "card_number", "card_numbers", "pan", "pans", "phone", "phone_number", "phone_numbers", "ucp_id", "ucp_ids", "client_id", "customer_id", "device_id", "account", "accounts", "request_id", "rq_uid", "rqUid"}


def _python_boundary_evidence_props(*, operation: str, target: str, storage_access_id: str | None = None) -> dict[str, Any]:
    props = maturity_props({
        "python_storage_boundary": "unresolved",
        "persistence_write": "unresolved",
        "physical_storage": "unresolved",
        "source_boundary": "unresolved",
        "field_mapping": "unresolved",
        "end_to_end_trace": "unresolved",
    }, notes=["Python scanner uses source-only AST candidate signals; storage boundaries require targeted source/ORM/SQL inspection before they become evidence."])
    props["candidate_signals"] = [candidate_signal(
        signal_type="python_storage_boundary",
        target=target,
        basis="Python source-only AST observed DB/ORM/repository-like call; exact persistence semantics are not hard evidence",
        recommended_action=f"inspect Python function {operation} and follow concrete ORM/SQL/helper target before treating it as persistence evidence",
        related_evidence_refs=[storage_access_id or ""],
    )]
    return props


def _python_trace_evidence_props(*, is_ingress: bool, has_storage_write: bool, has_outbound: bool) -> dict[str, Any]:
    return maturity_props({
        "source_boundary": "confirmed" if is_ingress else "unresolved",
        "persistence_write": "unresolved" if has_storage_write else "not_applicable",
        "end_to_end_trace": "confirmed" if is_ingress else "unresolved",
        "field_mapping": "unresolved" if (has_storage_write or has_outbound) else "not_applicable",
        "physical_storage": "unresolved" if has_storage_write else "not_applicable",
    }, notes=["Python data_trace is navigation evidence; unresolved dimensions require targeted source inspection."])


def _stable_int(*parts: str) -> int:
    data = "|".join(parts).encode("utf-8", errors="ignore")
    return int(hashlib.sha1(data).hexdigest()[:10], 16) % 1000000


def _ann_to_str(node: ast.AST | None) -> str | None:
    if node is None:
        return None
    try:
        return ast.unparse(node)
    except Exception:
        if isinstance(node, ast.Name):
            return node.id
        if isinstance(node, ast.Attribute):
            return f"{_ann_to_str(node.value)}.{node.attr}".strip(".")
        return None


def _call_name(node: ast.AST) -> str:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        base = _call_name(node.value)
        return f"{base}.{node.attr}" if base else node.attr
    if isinstance(node, ast.Call):
        return _call_name(node.func)
    return ""


def _decorator_name(node: ast.AST) -> str:
    if isinstance(node, ast.Call):
        return _call_name(node.func)
    return _call_name(node)


def _string_arg(node: ast.Call) -> str | None:
    for arg in node.args:
        if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
            return arg.value
    for kw in node.keywords:
        if kw.arg in {"path", "rule", "value", "topic", "topics", "queue"} and isinstance(kw.value, ast.Constant) and isinstance(kw.value.value, str):
            return kw.value.value
    return None


def _decorator_call(node: ast.AST) -> ast.Call | None:
    return node if isinstance(node, ast.Call) else None


def _is_fastapi_or_flask_route(dec: ast.AST) -> tuple[bool, str | None, str | None]:
    name = _decorator_name(dec)
    parts = name.split(".")
    last = parts[-1] if parts else name
    if last not in HTTP_METHODS:
        return False, None, None
    # Heuristic: @app.get, @router.post, @bp.route, @blueprint.route.
    if len(parts) < 2:
        return False, None, None
    call = _decorator_call(dec)
    path = _string_arg(call) if call else None
    method = last.upper() if last != "route" else "ROUTE"
    if last == "route" and call:
        for kw in call.keywords:
            if kw.arg == "methods" and isinstance(kw.value, (ast.List, ast.Tuple)):
                vals = [x.value for x in kw.value.elts if isinstance(x, ast.Constant) and isinstance(x.value, str)]
                if vals:
                    method = ",".join(vals)
    return True, method, path


def _is_message_or_job_decorator(dec: ast.AST) -> tuple[bool, str, str | None]:
    name = _decorator_name(dec)
    low = name.lower()
    call = _decorator_call(dec)
    topic = _string_arg(call) if call else None
    if "kafkalistener" in low or low.endswith(".subscribe") or low.endswith(".consumer") or "consumer" in low:
        return True, "kafka_listener", topic
    if low.endswith(".task") or low == "shared_task" or "celery" in low:
        return True, "task", topic
    if "schedule" in low or "cron" in low:
        return True, "scheduler", topic
    return False, "", None


def _function_params(fn: ast.FunctionDef | ast.AsyncFunctionDef) -> list[tuple[str, str | None]]:
    out: list[tuple[str, str | None]] = []
    args = list(fn.args.posonlyargs) + list(fn.args.args) + list(fn.args.kwonlyargs)
    for a in args:
        if a.arg in {"self", "cls"}:
            continue
        out.append((a.arg, _ann_to_str(a.annotation)))
    return out


def _request_payload(params: list[tuple[str, str | None]]) -> tuple[str | None, str | None]:
    for name, typ in params:
        if typ and typ not in {"Request", "flask.Request", "HttpRequest", "Any", "str", "int", "bool", "float"}:
            return name, typ
    for name, typ in params:
        if name not in {"request", "req"}:
            return name, typ or "unknown"
    return None, None


def _param_field_usages(fn: ast.FunctionDef | ast.AsyncFunctionDef, params: list[tuple[str, str | None]]) -> list[tuple[str, str]]:
    param_names = {name for name, _ in params}
    out: list[tuple[str, str]] = []
    for node in ast.walk(fn):
        if isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name) and node.value.id in param_names:
            pair = (node.value.id, node.attr)
            if pair not in out:
                out.append(pair)
    return out[:40]


def _expr_to_str(node: ast.AST | None) -> str | None:
    if node is None:
        return None
    try:
        return ast.unparse(node)
    except Exception:
        return None


def _evidence(path: Path, node: ast.AST, text: str, extractor: str = "python_ast") -> list[EvidenceRef]:
    line = getattr(node, "lineno", None)
    end = getattr(node, "end_lineno", None) or line
    return [EvidenceRef(file_path=str(path), line_start=line, line_end=end, snippet=snippet_around(text, line or 1), extractor=extractor)]


def _schema_from_class(path: Path, node: ast.ClassDef, text: str) -> SchemaInfo | None:
    bases = [_call_name(b) for b in node.bases]
    decorators = [_decorator_name(d) for d in node.decorator_list]
    is_schema_like = any(b.endswith(x) for b in bases for x in ["BaseModel", "Model", "Schema", "Serializer", "TypedDict"]) or any("dataclass" in d for d in decorators)
    fields: list[FieldInfo] = []
    for stmt in node.body:
        if isinstance(stmt, ast.AnnAssign) and isinstance(stmt.target, ast.Name):
            fields.append(FieldInfo(name=stmt.target.id, type=_ann_to_str(stmt.annotation)))
        elif isinstance(stmt, ast.Assign):
            for target in stmt.targets:
                if isinstance(target, ast.Name) and not target.id.startswith("_"):
                    fields.append(FieldInfo(name=target.id, type=None))
        elif isinstance(stmt, ast.FunctionDef) and stmt.name == "__init__":
            for inner in ast.walk(stmt):
                if isinstance(inner, ast.Assign):
                    for target in inner.targets:
                        if isinstance(target, ast.Attribute) and isinstance(target.value, ast.Name) and target.value.id == "self":
                            src_type = None
                            if isinstance(inner.value, ast.Name):
                                for arg_name, arg_type in _function_params(stmt):
                                    if arg_name == inner.value.id:
                                        src_type = arg_type
                            if not any(f.name == target.attr for f in fields):
                                fields.append(FieldInfo(name=target.attr, type=src_type))
    if not fields and not is_schema_like:
        return None
    source_type = "python_class"
    low_name = node.name.lower()
    if is_schema_like or any(x in low_name for x in ["request", "response", "dto", "schema", "event", "message", "model", "payload"]):
        source_type = "dto"
    if any(b.endswith("Model") for b in bases) and "BaseModel" not in bases:
        source_type = "orm_model"
    return SchemaInfo(
        name=node.name,
        source_type=source_type,
        fields=fields,
        evidence=_evidence(path, node, text),
        comments=[f"bases={bases}", f"decorators={decorators}"],
    )


class _PythonFunctionAnalyzer(ast.NodeVisitor):
    def __init__(self, path: Path, text: str, class_name: str | None, fn: ast.FunctionDef | ast.AsyncFunctionDef):
        self.path = path
        self.text = text
        self.class_name = class_name
        self.fn = fn
        self.operation = f"{class_name + '.' if class_name else ''}{fn.name}"
        self.facts: list[Fact] = []
        self.interfaces: list[InterfaceInfo] = []
        self.relations: list[RelationInfo] = []
        self.calls: list[dict[str, Any]] = []
        self.has_outbound = False
        self.has_storage_write = False
        self.first_outbound_flow_id: str | None = None
        self.first_storage_access_id: str | None = None
        self.params = _function_params(fn)
        self.param_field_usages = _param_field_usages(fn, self.params)

    def visit_Call(self, node: ast.Call) -> Any:
        name = _call_name(node.func)
        low = name.lower()
        args = [_expr_to_str(a) for a in node.args]
        payload = args[0] if args else None
        if any(low == f"{client}.{method}" or low.endswith(f".{method}") and low.split(".")[0] in REQUEST_CLIENT_NAMES for client in REQUEST_CLIENT_NAMES for method in ["get", "post", "put", "patch", "delete", "request"]):
            self._add_http_outbound(node, name, args)
        elif (low.endswith(".send") or low.endswith(".send_and_wait") or low.endswith(".produce") or low.endswith(".publish")) and any(tok in low for tok in ["kafka", "producer", "publisher", "topic"]):
            self._add_kafka_outbound(node, name, args)
        elif self._is_storage_call(low):
            self._add_storage_access(node, name, args)
        self.generic_visit(node)

    def _add_field_flow_facts(self, *, node: ast.Call, sink_kind: str, sink_pattern: str, payload: str | None, related_flow_id: str) -> None:
        ev = _evidence(self.path, node, self.text)
        for source_obj, source_field in self.param_field_usages[:12]:
            field_flow_id = f"field_flow_py_{_stable_int(str(self.path), self.operation, source_obj, source_field, sink_kind, str(getattr(node, 'lineno', ''))):06d}"
            role = "identifier" if source_field in IDENTIFIER_FIELD_NAMES else "business_or_context_field"
            self.facts.append(Fact(
                fact_type="field_identifier_flow",
                name=f"{source_obj}.{source_field} -> {sink_kind}",
                properties={
                    "field_flow_id": field_flow_id,
                    "source_object": source_obj,
                    "source_parameter": source_obj,
                    "source_field": source_field,
                    "source_role": role,
                    "field_mode": "python_param_attribute_usage",
                    "sink_channel": sink_kind,
                    "sink_kind": sink_kind,
                    "sink_pattern": sink_pattern,
                    "sink_payload": payload,
                    "payload_expression": payload,
                    "operation": self.operation,
                    "class_name": self.class_name,
                    "method_name": self.fn.name,
                    "related_flow_id": related_flow_id,
                    "path": [f"{source_obj}.{source_field}", payload or "unknown_payload", sink_pattern],
                },
                evidence=ev
            ))

    def _add_http_outbound(self, node: ast.Call, name: str, args: list[str | None]) -> None:
        line = getattr(node, "lineno", None)
        url = args[0] if args else None
        payload = None
        for kw in node.keywords:
            if kw.arg in {"json", "data", "params"}:
                payload = _expr_to_str(kw.value)
                break
        if payload is None and len(args) > 1:
            payload = args[1]
        flow_id = f"flow_py_{_stable_int(str(self.path), self.operation, str(line), name):06d}"
        self.first_outbound_flow_id = self.first_outbound_flow_id or flow_id
        self.has_outbound = True
        ev = _evidence(self.path, node, self.text)
        self.interfaces.append(InterfaceInfo(
            name=str(url or name)[:160],
            direction=Direction.OUTBOUND,
            kind=InterfaceKind.REST,
            schema_ref="unknown",
            operation=self.operation,
            path=str(url) if url else None,
            method=name.split(".")[-1].upper(),
            evidence=ev,
            properties={"receiver_expression": name, "payload_expression": payload, "sink_kind": "http_client"},
        ))
        self.facts.append(Fact(
            fact_type="source_to_sink_flow",
            name=f"{self.operation} -> http_client",
            properties={
                "flow_id": flow_id,
                "flow_type": "python_source_to_sink",
                "operation": self.operation,
                "source_kind": "method_parameter" if self.params else "local_value",
                "source_parameter": self.params[0][0] if self.params else None,
                "source_type": self.params[0][1] if self.params else "unknown",
                "sink_kind": "http_client",
                "sink_pattern": name,
                "target_expression": name,
                "payload_expression": payload,
                "flow_mode": "source_only_python_ast",
            },
            evidence=ev
        ))
        self._add_field_flow_facts(node=node, sink_kind="http_client", sink_pattern=name, payload=payload, related_flow_id=flow_id)

    def _add_kafka_outbound(self, node: ast.Call, name: str, args: list[str | None]) -> None:
        line = getattr(node, "lineno", None)
        topic = args[0] if args else None
        payload = args[1] if len(args) > 1 else None
        flow_id = f"flow_py_{_stable_int(str(self.path), self.operation, str(line), name):06d}"
        self.first_outbound_flow_id = self.first_outbound_flow_id or flow_id
        self.has_outbound = True
        ev = _evidence(self.path, node, self.text)
        self.interfaces.append(InterfaceInfo(
            name=str(topic or name)[:160],
            direction=Direction.OUTBOUND,
            kind=InterfaceKind.KAFKA,
            schema_ref="unknown",
            operation=self.operation,
            evidence=ev,
            properties={"receiver_expression": name, "payload_expression": payload, "sink_kind": "kafka"},
        ))
        self.facts.append(Fact(
            fact_type="source_to_sink_flow",
            name=f"{self.operation} -> kafka",
            properties={
                "flow_id": flow_id,
                "flow_type": "python_source_to_sink",
                "operation": self.operation,
                "source_kind": "method_parameter" if self.params else "local_value",
                "source_parameter": self.params[0][0] if self.params else None,
                "source_type": self.params[0][1] if self.params else "unknown",
                "sink_kind": "kafka",
                "sink_pattern": name,
                "target_expression": name,
                "payload_expression": payload,
                "flow_mode": "source_only_python_ast",
            },
            evidence=ev
        ))
        self._add_field_flow_facts(node=node, sink_kind="kafka", sink_pattern=name, payload=payload, related_flow_id=flow_id)

    def _is_storage_call(self, low: str) -> bool:
        method = low.split(".")[-1]
        if method in DB_WRITE_NAMES:
            return any(tok in low for tok in ["db", "session", "repo", "repository", "dao", "collection", "model", "objects", "cursor"])
        if method.startswith(DB_READ_PREFIXES):
            return any(tok in low for tok in ["db", "session", "repo", "repository", "dao", "collection", "objects", "cursor"])
        return False

    def _add_storage_access(self, node: ast.Call, name: str, args: list[str | None]) -> None:
        method = name.split(".")[-1]
        is_read = method.startswith(DB_READ_PREFIXES)
        is_delete = method.startswith("delete")
        access_kind = "read" if is_read else ("mutation" if is_delete else "write")
        write_kind = "delete" if is_delete else (method if not is_read else None)
        line = getattr(node, "lineno", None)
        storage_id = f"storage_access_py_{_stable_int(str(self.path), self.operation, str(line), name):06d}"
        if access_kind in {"write", "mutation"}:
            self.has_storage_write = True
            self.first_storage_access_id = self.first_storage_access_id or storage_id
        ev = _evidence(self.path, node, self.text)
        self.facts.append(Fact(
            fact_type="storage_access",
            name=name,
            properties={
                "storage_access_id": storage_id,
                "operation": self.operation,
                "access_kind": access_kind,
                "write_kind": write_kind,
                "mutation_kind": "delete" if is_delete else None,
                "table_or_repository": name.rsplit(".", 1)[0] if "." in name else name,
                "storage_method": method,
                "payload_expression": args[0] if args else None,
                **_python_boundary_evidence_props(operation=self.operation, target=name, storage_access_id=storage_id),
            },
            evidence=ev
        ))


def scan_python_files(files: list[Path]) -> tuple[list[Fact], list[SchemaInfo], list[InterfaceInfo], list[RelationInfo], list[Fact], list[str]]:
    facts: list[Fact] = []
    schemas: list[SchemaInfo] = []
    interfaces: list[InterfaceInfo] = []
    relations: list[RelationInfo] = []
    mapper_facts: list[Fact] = []
    warnings: list[str] = []
    ingress_seq = 0
    trace_seq = 0

    for p in [x for x in files if x.suffix.lower() == ".py"]:
        text = read_text(p)
        try:
            tree = ast.parse(text)
        except SyntaxError as exc:
            warnings.append(f"python parse failed {p}: {exc}")
            continue

        module = p.stem
        parent: dict[ast.AST, ast.AST | None] = {}
        for node in ast.walk(tree):
            for child in ast.iter_child_nodes(node):
                parent[child] = node

        class_by_node: dict[ast.AST, str] = {}
        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef):
                class_by_node[node] = node.name
                schema = _schema_from_class(p, node, text)
                if schema:
                    schemas.append(schema)

        functions: list[tuple[str | None, ast.FunctionDef | ast.AsyncFunctionDef]] = []
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                cls = None
                par = parent.get(node)
                if isinstance(par, ast.ClassDef):
                    cls = par.name
                functions.append((cls, node))

        for class_name, fn in functions:
            op = f"{class_name + '.' if class_name else ''}{fn.name}"
            params = _function_params(fn)
            payload_param, payload_type = _request_payload(params)
            is_ingress = False
            ingress_kind = None
            endpoint = None
            method = None
            for dec in fn.decorator_list:
                route, m, path = _is_fastapi_or_flask_route(dec)
                if route:
                    is_ingress = True
                    ingress_kind = "rest_controller"
                    endpoint = path
                    method = m
                msg, kind, topic = _is_message_or_job_decorator(dec)
                if msg:
                    is_ingress = True
                    ingress_kind = kind
                    endpoint = topic
                    method = None
            if fn.name in {"lambda_handler", "handler", "main"} and not class_name:
                # Treat as entrypoint/trigger but only lambda_handler with event payload is a payload origin.
                is_ingress = True
                ingress_kind = "external_adapter" if fn.name == "lambda_handler" else "batch_job"
                endpoint = fn.name

            if is_ingress:
                ingress_seq += 1
                ingress_id = f"ingress_{ingress_seq:06d}"
                ev = _evidence(p, fn, text)
                if ingress_kind == "rest_controller":
                    interfaces.append(InterfaceInfo(
                        name=f"{method or 'ROUTE'} {endpoint or ''}".strip(),
                        direction=Direction.INBOUND,
                        kind=InterfaceKind.REST,
                        schema_ref=payload_type or "unknown",
                        operation=op,
                        path=endpoint,
                        method=method,
                        evidence=ev,
                        properties={"payload_parameter": payload_param, "framework": "python_web"},
                    ))
                    interfaces.append(InterfaceInfo(
                        name=f"{method or 'ROUTE'} {endpoint or ''} response".strip(),
                        direction=Direction.OUTBOUND,
                        kind=InterfaceKind.REST,
                        schema_ref=_ann_to_str(fn.returns) or "unknown",
                        operation=op,
                        path=endpoint,
                        method=method,
                        evidence=ev,
                        properties={"framework": "python_web", "return_type": _ann_to_str(fn.returns)},
                    ))
                facts.append(Fact(
                    fact_type="system_ingress",
                    name=op,
                    properties={
                        "ingress_id": ingress_id,
                        "origin_id": ingress_id.replace("ingress_", "origin_"),
                        "ingress_kind": ingress_kind,
                        "origin_kind": ingress_kind,
                        "is_payload_origin": ingress_kind not in {"scheduler", "batch_job"},
                        "operation": op,
                        "operation_id": op,
                        "class_name": class_name,
                        "method_name": fn.name,
                        "signature": f"{op}({', '.join(n for n, _ in params)})",
                        "payload_type": payload_type,
                        "payload_parameter": payload_param,
                        "endpoint_or_topic": endpoint,
                    },
                    evidence=ev
                ))

            analyzer = _PythonFunctionAnalyzer(p, text, class_name, fn)
            analyzer.visit(fn)
            facts.extend(analyzer.facts)
            interfaces.extend(analyzer.interfaces)
            relations.extend(analyzer.relations)

            if analyzer.has_outbound or analyzer.has_storage_write:
                trace_seq += 1
                trace_id = f"trace_{trace_seq:06d}"
                if is_ingress:
                    trace_status = "unresolved"
                    missing_links: list[str] = []
                    origin_id = f"origin_{ingress_seq:06d}"
                    ingress_id = f"ingress_{ingress_seq:06d}"
                else:
                    trace_status = "outbound_only_unknown_origin" if analyzer.has_outbound else "persistence_only_unknown_origin"
                    missing_links = ["no confirmed ingress/data-origin", f"no caller chain to {op}"]
                    origin_id = None
                    ingress_id = None
                trace_type = "ingress_to_outbound" if analyzer.has_outbound else "ingress_to_persistence"
                facts.append(Fact(
                    fact_type="data_trace",
                    name=f"{trace_type} {op}",
                    properties={
                        "trace_id": trace_id,
                        "trace_type": trace_type,
                        "origin_trace_type": trace_type,
                        "trace_status": trace_status,
                        "ingress_id": ingress_id,
                        "origin_id": origin_id,
                        "origin_kind": ingress_kind if is_ingress else "unknown",
                        "ingress_operation_id": op if is_ingress else None,
                        "earliest_observed_operation_id": op,
                        "earliest_observed_reason": None if is_ingress else "no confirmed ingress/data-origin found",
                        "terminal_operation_id": op,
                        "outbound_operation_id": op if analyzer.has_outbound else None,
                        "persistence_operation_id": op if analyzer.has_storage_write else None,
                        "storage_access_id": analyzer.first_storage_access_id,
                        **_python_trace_evidence_props(is_ingress=is_ingress, has_storage_write=analyzer.has_storage_write, has_outbound=analyzer.has_outbound),
                        "evidence_refs": [x for x in [ingress_id, analyzer.first_outbound_flow_id, analyzer.first_storage_access_id] if x],
                        "missing_links": missing_links,
                        "steps": [
                            {"kind": "ingress" if is_ingress else "earliest_observed_operation", "operation_id": op, "description": f"Python function {op}"},
                            {"kind": "outbound_sink" if analyzer.has_outbound else "storage_access", "operation_id": op, "description": "Detected by source-only Python AST scanner"},
                        ],
                    },
                    evidence=_evidence(p, fn, text)
                ))

    return facts, schemas, interfaces, relations, mapper_facts, warnings
