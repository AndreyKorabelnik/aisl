#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Mapping

from aisl_sdk import AislClient, project_data_model_object
from aisl_sdk.errors import AislApiError, AislContractError, AislTransportError

DEFAULT_PROFILE = "data-model/v1"
VERSION = "0.2.0"


def _dict(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, Mapping) else {}


def _list_dicts(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    return [dict(v) for v in value if isinstance(v, Mapping)]


def _text(value: Any) -> str:
    return str(value or "").strip()


def _headers(values: list[str]) -> dict[str, str]:
    result: dict[str, str] = {}
    for value in values:
        if "=" not in value:
            raise ValueError(f"--header must be KEY=VALUE, got {value!r}")
        key, item = value.split("=", 1)
        key = key.strip()
        if not key:
            raise ValueError("--header key must not be empty")
        result[key] = item
    return result


def _make_client(args: argparse.Namespace) -> AislClient:
    cert: str | tuple[str, str] | None = None
    if args.cert and args.key:
        cert = (args.cert, args.key)
    elif args.cert:
        cert = args.cert
    elif args.key:
        raise ValueError("--key requires --cert")
    verify: bool | str = args.ca if args.ca else (not args.insecure)
    return AislClient(
        args.api_url,
        timeout_sec=args.timeout,
        headers=_headers(args.header),
        verify=verify,
        cert=cert,
    )


def _pinned_revision(client: AislClient, args: argparse.Namespace):
    if args.revision_id:
        return client.revision(args.system_id, args.revision_id)
    return client.active_revision(args.system_id)


def _integration(revision: Any, args: argparse.Namespace):
    return revision.integration(args.profile)


def _tool(integration: Any, name: str, arguments: Mapping[str, Any]) -> dict[str, Any]:
    return dict(integration.execute_tool(name, arguments).result)


def _write_json(value: Any, output: str | None, *, compact: bool = False) -> None:
    text = json.dumps(
        value,
        ensure_ascii=False,
        indent=None if compact else 2,
        separators=(",", ":") if compact else None,
    ) + "\n"
    if not output or output == "-":
        sys.stdout.write(text)
        return
    Path(output).write_text(text, encoding="utf-8")


def _search_objects(integration: Any, text: str, limit: int) -> list[dict[str, Any]]:
    payload = _tool(
        integration,
        "search_declared_data_objects",
        {
            "repo_id": None,
            "search": text,
            "type_annotations": [],
            "include_fields": False,
            "offset": 0,
            "limit": limit,
        },
    )
    return _list_dicts(payload.get("items"))


def _candidate_id(item: Mapping[str, Any]) -> str:
    return _text(item.get("object_id") or _dict(item.get("object")).get("object_id"))


def _compact_candidate(item: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "object_id": _candidate_id(item),
        "name": item.get("name"),
        "fqcn": item.get("fqcn"),
        "repo_id": item.get("repo_id"),
        "retrieval_score": item.get("retrieval_score"),
        "match_evidence": item.get("match_evidence"),
    }


def _resolve_object(integration: Any, selector: str, search_limit: int) -> tuple[str, dict[str, Any]]:
    selector = selector.strip()
    if not selector:
        raise ValueError("--object must not be empty")

    if selector.startswith("code_declared_type_"):
        context = _tool(integration, "get_data_model_object_context", {"object_id": selector})
        return selector, {
            "input": selector,
            "basis": "exact_object_id",
            "candidate_count": 1,
        }

    items = _search_objects(integration, selector, search_limit)
    exact_fqcn = [x for x in items if _text(x.get("fqcn")) == selector]
    exact_name = [x for x in items if _text(x.get("name")) == selector]

    chosen: dict[str, Any] | None = None
    basis = ""
    if len(exact_fqcn) == 1:
        chosen, basis = exact_fqcn[0], "exact_fqcn"
    elif len(exact_fqcn) > 1:
        raise AislContractError(f"multiple exact FQCN matches for {selector!r}")
    elif len(exact_name) == 1:
        chosen, basis = exact_name[0], "exact_name"
    elif len(exact_name) > 1:
        raise AislContractError(
            "object name is ambiguous; use exact FQCN or object_id. Candidates: "
            + json.dumps([_compact_candidate(x) for x in exact_name[:20]], ensure_ascii=False)
        )
    elif len(items) == 1:
        chosen, basis = items[0], "single_search_result"
    else:
        raise AislContractError(
            f"object selector {selector!r} did not resolve uniquely; use exact FQCN or object_id. Candidates: "
            + json.dumps([_compact_candidate(x) for x in items[:20]], ensure_ascii=False)
        )

    object_id = _candidate_id(chosen)
    if not object_id:
        raise AislContractError("resolved object has no object_id")
    return object_id, {
        "input": selector,
        "basis": basis,
        "candidate_count": len(items),
        "selected": _compact_candidate(chosen),
    }


def cmd_revision(args: argparse.Namespace) -> int:
    with _make_client(args) as client:
        rev = _pinned_revision(client, args)
        _write_json(
            {
                "system_id": rev.system_id,
                "revision_id": rev.revision_id,
                "capabilities": list(rev.get_capabilities()),
                "products": [p.raw for p in rev.list_products()],
            },
            args.output,
            compact=args.compact,
        )
    return 0


def cmd_tools(args: argparse.Namespace) -> int:
    with _make_client(args) as client:
        rev = _pinned_revision(client, args)
        integration = _integration(rev, args)
        _write_json(
            {
                "system_id": rev.system_id,
                "revision_id": rev.revision_id,
                "profile_id": integration.profile_id,
                "profile_fingerprint": integration.fingerprint,
                "tools": [dict(x) for x in integration.tools],
            },
            args.output,
            compact=args.compact,
        )
    return 0


def cmd_call(args: argparse.Namespace) -> int:
    values = json.loads(args.args_json or "{}")
    if not isinstance(values, dict):
        raise ValueError("--args-json must be a JSON object")
    with _make_client(args) as client:
        rev = _pinned_revision(client, args)
        integration = _integration(rev, args)
        executed = integration.execute_tool(args.tool_name, values)
        _write_json(
            {
                "system_id": rev.system_id,
                "revision_id": rev.revision_id,
                "profile_id": integration.profile_id,
                "tool": executed.tool_name,
                "duration_ms": executed.duration_ms,
                "result": executed.result,
            },
            args.output,
            compact=args.compact,
        )
    return 0


def cmd_resolve_object(args: argparse.Namespace) -> int:
    with _make_client(args) as client:
        rev = _pinned_revision(client, args)
        integration = _integration(rev, args)
        object_id, resolution = _resolve_object(integration, args.object, args.search_limit)
        _write_json(
            {
                "system_id": rev.system_id,
                "revision_id": rev.revision_id,
                "profile_id": integration.profile_id,
                "object_id": object_id,
                "resolution": resolution,
            },
            args.output,
            compact=args.compact,
        )
    return 0


def cmd_project_data_model_object(args: argparse.Namespace) -> int:
    with _make_client(args) as client:
        rev = _pinned_revision(client, args)
        integration = _integration(rev, args)
        # The profile is authoritative: projection requires these exact public tools.
        integration.tool("search_declared_data_objects")
        integration.tool("get_data_model_object_context")
        object_id, resolution = _resolve_object(integration, args.object, args.search_limit)
        context = _tool(integration, "get_data_model_object_context", {"object_id": object_id})
        projected = project_data_model_object(
            context,
            profile_id=integration.profile_id,
            profile_fingerprint=integration.fingerprint,
            resolution=resolution,
            include_provenance=args.include_provenance,
        )
        _write_json(projected, args.output, compact=args.compact)
    return 0


def _common(p: argparse.ArgumentParser) -> None:
    p.add_argument("--api-url", required=True, help="Knowledge API URL, e.g. http://127.0.0.1:8080")
    p.add_argument("--system-id", required=True)
    p.add_argument("--revision-id", help="Exact immutable revision. If omitted, active revision is resolved once and pinned.")
    p.add_argument("--profile", default=DEFAULT_PROFILE, help=f"Consumer Integration Profile (default: {DEFAULT_PROFILE})")
    p.add_argument("--timeout", type=float, default=30.0)
    p.add_argument("--header", action="append", default=[], metavar="KEY=VALUE")
    p.add_argument("--ca", help="CA bundle path")
    p.add_argument("--cert", help="Client certificate path")
    p.add_argument("--key", help="Client private key path")
    p.add_argument("--insecure", action="store_true", help="Disable TLS verification (development only)")
    p.add_argument("--output", default="-", help="Output JSON file, or - for stdout")
    p.add_argument("--compact", action="store_true", help="Emit compact JSON")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="aisl",
        description="Generic CLI for consuming published AISL knowledge via Knowledge API and Consumer Integration Profiles.",
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {VERSION}")
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("revision", help="Inspect a pinned revision")
    _common(p)
    p.set_defaults(func=cmd_revision)

    p = sub.add_parser("tools", help="List tools allowed by an Integration Profile")
    _common(p)
    p.set_defaults(func=cmd_tools)

    p = sub.add_parser("call", help="Execute one explicitly selected profile tool")
    _common(p)
    p.add_argument("tool_name")
    p.add_argument("--args-json", default="{}")
    p.set_defaults(func=cmd_call)

    p = sub.add_parser("resolve-object", help="Resolve object_id from exact object_id, FQCN or unique name")
    _common(p)
    p.add_argument("--object", required=True, help="object_id, exact FQCN, or unique object name")
    p.add_argument("--search-limit", type=int, default=50)
    p.set_defaults(func=cmd_resolve_object)

    p = sub.add_parser("project", help="Create a reusable consumer-side projection from published knowledge")
    project_sub = p.add_subparsers(dest="projection", required=True)

    q = project_sub.add_parser(
        "data-model-object",
        help="Export one complete declared/effective data-model object with storage/reference semantics",
    )
    _common(q)
    q.add_argument("--object", required=True, help="object_id, exact FQCN, or unique object name")
    q.add_argument("--search-limit", type=int, default=50)
    q.add_argument("--include-provenance", action="store_true", help="Include source refs/provenance in addition to compact evidence IDs")
    q.set_defaults(func=cmd_project_data_model_object)

    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return int(args.func(args))
    except (ValueError, json.JSONDecodeError, AislApiError, AislContractError, AislTransportError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
