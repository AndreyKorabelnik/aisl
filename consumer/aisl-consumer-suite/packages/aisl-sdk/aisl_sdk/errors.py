from __future__ import annotations

from typing import Any


class AislClientError(RuntimeError):
    """Base class for public AISL client failures."""


class AislTransportError(AislClientError):
    """The Knowledge API could not be reached or the HTTP exchange failed."""


class AislContractError(AislClientError):
    """The server response could not be consumed as the advertised JSON contract."""


class AislApiError(AislClientError):
    """Knowledge API returned a non-success HTTP response."""

    def __init__(
        self,
        *,
        status_code: int,
        method: str,
        path: str,
        detail: Any,
    ) -> None:
        self.status_code = int(status_code)
        self.method = str(method).upper()
        self.path = str(path)
        self.detail = detail
        super().__init__(
            f"Knowledge API returned HTTP {self.status_code} for "
            f"{self.method} {self.path}: {self.detail}"
        )
