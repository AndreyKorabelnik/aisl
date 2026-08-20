from __future__ import annotations

import argparse
import os
import ssl

from aisl_sdk import AislClient

from .providers import OpenAICompatibleProvider, fixture_provider
from .runtime import AgentRuntime
from .service import AgentHttpService


def _provider_from_env():
    kind = os.getenv("AISL_AGENT_PROVIDER", "openai-compatible").strip().lower()
    if kind == "fixture":
        return fixture_provider(object_id=os.getenv("AISL_AGENT_FIXTURE_OBJECT_ID", "t-ind"))
    if kind != "openai-compatible":
        raise SystemExit(f"unsupported AISL_AGENT_PROVIDER: {kind}")
    base_url = os.getenv("LLM_BASE_URL")
    model = os.getenv("LLM_MODEL")
    if not base_url or not model:
        raise SystemExit("LLM_BASE_URL and LLM_MODEL are required for openai-compatible provider")
    cert_file = os.getenv("LLM_CERT_FILE")
    key_file = os.getenv("LLM_KEY_FILE")
    if bool(cert_file) ^ bool(key_file):
        raise SystemExit("both LLM_CERT_FILE and LLM_KEY_FILE are required for mTLS")
    cert = (cert_file, key_file) if cert_file and key_file else None
    ca_file = os.getenv("LLM_CA_FILE")
    verify: bool | str | ssl.SSLContext = ca_file if ca_file else True
    return OpenAICompatibleProvider(
        base_url=base_url,
        model=model,
        api_key=os.getenv("LLM_API_KEY"),
        timeout_sec=float(os.getenv("LLM_TIMEOUT_SEC", "300")),
        cert=cert,
        verify=verify,
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="External AISL agent runtime")
    parser.add_argument("serve", nargs="?")
    parser.add_argument("--api-url", default=os.getenv("AISL_API_URL", "http://127.0.0.1:8080"))
    parser.add_argument("--host", default=os.getenv("HOST", "127.0.0.1"))
    parser.add_argument("--port", type=int, default=int(os.getenv("PORT", "18220")))
    parser.add_argument("--max-tool-rounds", type=int, default=int(os.getenv("AISL_AGENT_MAX_TOOL_ROUNDS", "16")))
    args = parser.parse_args(argv)
    client = AislClient(args.api_url, timeout_sec=float(os.getenv("AISL_API_TIMEOUT_SEC", "60")))
    provider = _provider_from_env()
    runtime = AgentRuntime(client=client, provider=provider, max_tool_rounds=args.max_tool_rounds)
    AgentHttpService(runtime=runtime, host=args.host, port=args.port).serve_forever()
    return 0
