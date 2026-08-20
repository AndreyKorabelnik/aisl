from __future__ import annotations

import os
import re
from collections.abc import Iterable

_SENSITIVE_NAME = re.compile(r"(?:TOKEN|PASSWORD|SECRET|API_KEY|ACCESS_KEY|PRIVATE_KEY)", re.IGNORECASE)
_URL_CREDENTIALS = re.compile(r"(?P<scheme>https?://)(?P<credentials>[^/@\s]+)@")
_NAMED_SECRET = re.compile(
    r"(?P<name>(?:access[_-]?token|token|password|secret|api[_-]?key))(?P<sep>\s*[:=]\s*)(?P<value>[^\s,;]+)",
    re.IGNORECASE,
)


def environment_secret_values(extra_environment: dict[str, str] | None = None) -> tuple[str, ...]:
    combined = dict(os.environ)
    combined.update(extra_environment or {})
    values = {
        value
        for name, value in combined.items()
        if value and len(value) >= 4 and _SENSITIVE_NAME.search(name)
    }
    return tuple(sorted(values, key=len, reverse=True))


def redact_text(text: str, *, secrets: Iterable[str] = ()) -> str:
    redacted = text
    for secret in secrets:
        if secret:
            redacted = redacted.replace(secret, "****")
    redacted = _URL_CREDENTIALS.sub(lambda match: f"{match.group('scheme')}****@", redacted)
    redacted = _NAMED_SECRET.sub(
        lambda match: f"{match.group('name')}{match.group('sep')}****",
        redacted,
    )
    return redacted
