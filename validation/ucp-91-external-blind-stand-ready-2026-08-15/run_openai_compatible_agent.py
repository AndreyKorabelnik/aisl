#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import re
import time
from pathlib import Path
from typing import Any
from urllib.parse import quote

import requests

RESULT_SCHEMA = "ucp-attribute-agent-result/v1"
ALLOWED_STATUSES = {"confirmed", "strongly_supported", "probable", "ambiguous", "unresolved"}


def endpoint_url(value: str) -> str:
    value = value.rstrip("/")
    if value.endswith("/chat/completions"):
        return value
    if value.endswith("/v1"):
        return value + "/chat/completions"
    return value + "/v1/chat/completions"


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def json_type(spec: str) -> dict[str, Any]:
    spec = spec.strip()
    nullable = spec.endswith("|null")
    base = spec[:-5] if nullable else spec
    if base == "string":
        out: dict[str, Any] = {"type": "string"}
    elif base == "integer":
        out = {"type": "integer"}
    elif base == "boolean":
        out = {"type": "boolean"}
    elif base == "array[string]":
        out = {"type": "array", "items": {"type": "string"}}
    else:
        out = {"type": "string"}
    if nullable:
        out = {"anyOf": [out, {"type": "null"}]}
    return out


def openai_tools(catalog: list[dict[str, Any]]) -> list[dict[str, Any]]:
    required_by_name = {
        "get_declared_data_object": ["object_id"],
        "get_knowledge_item": ["artifact_id", "item_kind", "local_id"],
    }
    result = []
    for tool in catalog:
        props = {name: json_type(str(spec)) for name, spec in (tool.get("arguments") or {}).items()}
        params: dict[str, Any] = {"type": "object", "properties": props, "additionalProperties": False}
        required = [x for x in required_by_name.get(str(tool.get("name")), []) if x in props]
        if required:
            params["required"] = required
        result.append({
            "type": "function",
            "function": {
                "name": tool["name"],
                "description": tool.get("description") or "",
                "parameters": params,
            },
        })
    return result


class ToolExecutor:
    def __init__(self, *, api_base: str, profile: dict[str, Any], catalog: list[dict[str, Any]], timeout: int) -> None:
        self.api_base = api_base.rstrip("/")
        self.profile = profile
        self.catalog = {str(t["name"]): t for t in catalog}
        self.timeout = timeout
        scope = profile.get("scope") or {}
        self.system_id = str(scope.get("system_id") or "")
        self.revision_id = str(scope.get("revision_id") or "")
        if not self.system_id or not self.revision_id:
            raise ValueError("consumer profile must pin system_id and revision_id")

    def call(self, name: str, args: dict[str, Any]) -> dict[str, Any]:
        if name not in self.catalog:
            return {"ok": False, "error": f"unknown tool: {name}"}
        tool = self.catalog[name]
        binding = tool.get("api_binding") or {}
        if str(binding.get("method") or "GET").upper() != "GET":
            return {"ok": False, "error": f"unsupported method for validation runner: {binding.get('method')}"}
        path = str(binding.get("path_template") or "")
        path = path.replace("{system_id}", quote(self.system_id, safe=""))
        query: dict[str, str] = {}
        rev = binding.get("revision_binding") or {}
        if rev.get("location") == "query":
            query[str(rev.get("name") or "revision_id")] = self.revision_id
        for arg_name, spec in (binding.get("arguments") or {}).items():
            if arg_name not in args or args[arg_name] is None:
                continue
            value = args[arg_name]
            loc = spec.get("location")
            transform = str(spec.get("transform") or "identity")
            api_name = str(spec.get("name") or arg_name)
            if transform == "csv" and isinstance(value, list):
                encoded = ",".join(str(x) for x in value)
            elif transform == "bool":
                encoded = "true" if bool(value) else "false"
            elif transform == "bounded_int":
                encoded = str(int(value))
            else:
                encoded = str(value)
            if loc == "path":
                path = path.replace("{" + api_name + "}", quote(encoded, safe=""))
            elif loc == "query":
                query[api_name] = encoded
        if "{" in path or "}" in path:
            return {"ok": False, "error": f"missing path argument for {name}", "path": path}
        started = time.perf_counter()
        try:
            resp = requests.get(self.api_base + path, params=query, timeout=self.timeout)
            duration_ms = int((time.perf_counter() - started) * 1000)
            try:
                body = resp.json()
            except Exception:
                body = {"text": resp.text[:8000]}
            return {"ok": 200 <= resp.status_code < 300, "status_code": resp.status_code, "duration_ms": duration_ms, "body": body}
        except Exception as exc:
            return {"ok": False, "status_code": None, "duration_ms": int((time.perf_counter() - started) * 1000), "error": str(exc)}


def parse_content_json(content: Any) -> dict[str, Any]:
    if isinstance(content, list):
        content = "\n".join(str(x.get("text") or "") for x in content if isinstance(x, dict))
    if not isinstance(content, str):
        raise ValueError("assistant content is not text")
    text = content.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text, flags=re.I)
        text = re.sub(r"\s*```$", "", text)
    try:
        value = json.loads(text)
    except json.JSONDecodeError:
        start, end = text.find("{"), text.rfind("}")
        if start < 0 or end <= start:
            raise
        value = json.loads(text[start : end + 1])
    if not isinstance(value, dict):
        raise ValueError("final response JSON must be an object")
    return value


def validate_batch(result: dict[str, Any], expected: dict[int, str]) -> list[dict[str, Any]]:
    rows = result.get("results")
    if not isinstance(rows, list) or len(rows) != len(expected):
        raise ValueError(f"expected {len(expected)} results, got {len(rows) if isinstance(rows, list) else 'non-list'}")
    seen: set[int] = set()
    out: list[dict[str, Any]] = []
    for row in rows:
        if not isinstance(row, dict):
            raise ValueError("result row must be object")
        idx = row.get("input_index")
        if not isinstance(idx, int) or idx not in expected or idx in seen:
            raise ValueError(f"invalid/duplicate input_index: {idx!r}")
        seen.add(idx)
        if row.get("attribute") != expected[idx]:
            raise ValueError(f"attribute for {idx} must be copied verbatim")
        if row.get("status") not in ALLOWED_STATUSES:
            raise ValueError(f"invalid status for {idx}: {row.get('status')!r}")
        if not isinstance(row.get("basis"), str) or not row["basis"].strip():
            raise ValueError(f"empty basis for {idx}")
        row.setdefault("object_fqcn", None)
        row.setdefault("field", None)
        row.setdefault("repo_id", None)
        row.setdefault("alternatives", [])
        row.setdefault("analysis_gap", None)
        out.append(row)
    return sorted(out, key=lambda x: int(x["input_index"]))


def main() -> int:
    parser = argparse.ArgumentParser(description="Reference external-agent runner for the Gold-isolated UCP 91 stand.")
    parser.add_argument("--endpoint", default=os.getenv("LLM_BASE_URL"))
    parser.add_argument("--model", default=os.getenv("LLM_MODEL"))
    parser.add_argument("--api-key", default=os.getenv("LLM_API_KEY"))
    parser.add_argument("--api-base", default="http://127.0.0.1:18081")
    parser.add_argument("--batch-size", type=int, default=10)
    parser.add_argument("--max-turns", type=int, default=30)
    parser.add_argument("--llm-timeout", type=int, default=300)
    parser.add_argument("--tool-timeout", type=int, default=60)
    parser.add_argument("--cert", type=Path, default=Path(os.environ["LLM_CERT_FILE"]) if os.getenv("LLM_CERT_FILE") else None)
    parser.add_argument("--key", type=Path, default=Path(os.environ["LLM_KEY_FILE"]) if os.getenv("LLM_KEY_FILE") else None)
    parser.add_argument("--ca", type=Path, default=Path(os.environ["LLM_CA_FILE"]) if os.getenv("LLM_CA_FILE") else None)
    parser.add_argument("--output", type=Path, default=Path("agent-result.json"))
    parser.add_argument("--trace-dir", type=Path, default=Path("agent-traces"))
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    root = Path(__file__).resolve().parents[1]
    kit = root / "runtime" / "consumer-kit"
    if not kit.exists():
        raise SystemExit("runtime/consumer-kit is missing. Run scripts/publish_revision.py --reset first.")
    profile = load_json(kit / "llm_integration_profile.json")
    catalog = load_json(kit / "TOOL_CATALOG.json")
    inputs = load_json(root / "blind" / "INPUTS_91.json")["items"]
    system_prompt = (kit / "SYSTEM_PROMPT.md").read_text(encoding="utf-8")
    consumer_policy = (root / "blind" / "CONSUMER_POLICY.md").read_text(encoding="utf-8")
    tools = openai_tools(catalog)
    executor = ToolExecutor(api_base=args.api_base, profile=profile, catalog=catalog, timeout=args.tool_timeout)

    if args.dry_run:
        print(json.dumps({
            "status": "dry-run-ready",
            "system_id": executor.system_id,
            "revision_id": executor.revision_id,
            "input_count": len(inputs),
            "batch_size": args.batch_size,
            "tool_names": [t["function"]["name"] for t in tools],
            "endpoint": endpoint_url(args.endpoint) if args.endpoint else None,
            "model": args.model,
        }, ensure_ascii=False, indent=2))
        return 0
    if not args.endpoint or not args.model:
        raise SystemExit("--endpoint/LLM_BASE_URL and --model/LLM_MODEL are required")
    if bool(args.cert) ^ bool(args.key):
        raise SystemExit("Both --cert and --key are required for mTLS")

    verify: bool | str = str(args.ca) if args.ca else True
    cert = (str(args.cert), str(args.key)) if args.cert and args.key else None
    headers = {"Content-Type": "application/json"}
    if args.api_key:
        headers["Authorization"] = f"Bearer {args.api_key}"
    chat_url = endpoint_url(args.endpoint)
    args.trace_dir.mkdir(parents=True, exist_ok=True)
    all_rows: list[dict[str, Any]] = []

    for batch_no, start in enumerate(range(0, len(inputs), args.batch_size), start=1):
        batch = inputs[start : start + args.batch_size]
        expected = {int(x["input_index"]): str(x["attribute"]) for x in batch}
        task = {
            "task": "Map each input attribute to the most useful supported UCP declared-model field, or preserve ambiguity/unresolved when evidence is insufficient.",
            "rules": [
                "Use the read-only tools for evidence. Do not guess target names from the input alone.",
                "Useful strongly-supported/probable inference is allowed when basis is explicit; mathematical proof is not required.",
                "Do not turn related concepts, generic containers or unbound types into confirmed direct fields.",
                "Use short independent lexical/synonym/translation searches and exact object reads as needed.",
                "Return JSON only when finished: {\"results\": [...]} for exactly this batch, using the output fields from OUTPUT_SCHEMA.json.",
            ],
            "items": batch,
        }
        messages: list[dict[str, Any]] = [
            {"role": "system", "content": system_prompt + "\n\n" + consumer_policy},
            {"role": "user", "content": json.dumps(task, ensure_ascii=False)},
        ]
        trace: dict[str, Any] = {"batch_no": batch_no, "input_indexes": sorted(expected), "turns": []}
        batch_rows: list[dict[str, Any]] | None = None

        for turn in range(1, args.max_turns + 1):
            started = time.perf_counter()
            payload = {"model": args.model, "messages": messages, "tools": tools, "tool_choice": "auto"}
            resp = requests.post(chat_url, headers=headers, json=payload, cert=cert, verify=verify, timeout=args.llm_timeout)
            duration = round(time.perf_counter() - started, 3)
            try:
                body = resp.json()
            except Exception as exc:
                raise RuntimeError(f"LLM returned non-JSON HTTP {resp.status_code}: {resp.text[:2000]}") from exc
            trace_turn: dict[str, Any] = {"turn": turn, "llm_duration_sec": duration, "http_status": resp.status_code, "usage": body.get("usage")}
            if not (200 <= resp.status_code < 300):
                trace_turn["error_body"] = body
                trace["turns"].append(trace_turn)
                raise RuntimeError(f"LLM HTTP {resp.status_code}: {body}")
            choice = (body.get("choices") or [{}])[0]
            message = choice.get("message") or {}
            tool_calls = message.get("tool_calls") or []
            assistant_message: dict[str, Any] = {"role": "assistant", "content": message.get("content")}
            if tool_calls:
                assistant_message["tool_calls"] = tool_calls
            messages.append(assistant_message)
            trace_turn["finish_reason"] = choice.get("finish_reason")
            trace_turn["tool_call_count"] = len(tool_calls)

            if tool_calls:
                tool_summaries = []
                for call in tool_calls:
                    fn = call.get("function") or {}
                    name = str(fn.get("name") or "")
                    raw_args = fn.get("arguments") or "{}"
                    try:
                        call_args = json.loads(raw_args) if isinstance(raw_args, str) else dict(raw_args)
                    except Exception:
                        call_args = {}
                    tool_result = executor.call(name, call_args)
                    tool_summaries.append({"name": name, "args": call_args, "ok": tool_result.get("ok"), "status_code": tool_result.get("status_code"), "duration_ms": tool_result.get("duration_ms")})
                    messages.append({
                        "role": "tool",
                        "tool_call_id": call.get("id"),
                        "name": name,
                        "content": json.dumps(tool_result, ensure_ascii=False),
                    })
                trace_turn["tools"] = tool_summaries
                trace["turns"].append(trace_turn)
                print(f"batch={batch_no} turn={turn} llm={duration:.1f}s tools={len(tool_calls)}")
                continue

            trace["turns"].append(trace_turn)
            try:
                final = parse_content_json(message.get("content"))
                batch_rows = validate_batch(final, expected)
            except Exception as exc:
                # One bounded repair request; no Gold or target hints are introduced.
                messages.append({"role": "user", "content": f"Your final response was not valid for the required batch schema: {exc}. Return corrected JSON only for the same input indexes."})
                print(f"batch={batch_no} turn={turn} final_parse_repair={exc}")
                continue
            print(f"batch={batch_no} completed turn={turn} llm={duration:.1f}s results={len(batch_rows)}")
            break

        trace["completed"] = batch_rows is not None
        (args.trace_dir / f"batch-{batch_no:02d}.json").write_text(json.dumps(trace, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        if batch_rows is None:
            raise RuntimeError(f"batch {batch_no} did not finish within {args.max_turns} turns")
        all_rows.extend(batch_rows)

    all_rows.sort(key=lambda x: int(x["input_index"]))
    if [int(x["input_index"]) for x in all_rows] != list(range(1, 92)):
        raise RuntimeError("combined result does not cover input indexes 1..91 exactly once")
    output = {"schema_version": RESULT_SCHEMA, "results": all_rows}
    args.output.write_text(json.dumps(output, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"status": "completed", "output": str(args.output), "result_count": len(all_rows)}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
