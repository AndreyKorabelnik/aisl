from __future__ import annotations

from typing import Any


class RuntimeApiError(RuntimeError):
    def __init__(
        self,
        status_code: int,
        code: str,
        message: str,
        *,
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.code = code
        self.message = message
        self.details = details or {}


class ResourceNotFound(RuntimeApiError):
    def __init__(self, resource: str, identifier: str) -> None:
        super().__init__(404, "resource_not_found", f"{resource} not found: {identifier}")


class RevisionConflict(RuntimeApiError):
    def __init__(self, resource: str, expected: int, actual: int) -> None:
        super().__init__(
            409,
            "revision_conflict",
            f"{resource} revision conflict: expected {expected}, actual {actual}",
            details={"expected_revision": expected, "actual_revision": actual},
        )


class InvalidState(RuntimeApiError):
    def __init__(self, message: str, *, details: dict[str, Any] | None = None) -> None:
        super().__init__(409, "invalid_resource_state", message, details=details)


class UnsafePath(RuntimeApiError):
    def __init__(self, path: str, reason: str) -> None:
        super().__init__(
            400,
            "unsafe_output_path",
            f"unsafe output path: {path}: {reason}",
            details={"path": path, "reason": reason},
        )


class CapabilityUnavailable(RuntimeApiError):
    def __init__(self, capability: str, reason: str) -> None:
        super().__init__(
            409,
            "capability_unavailable",
            f"capability is unavailable: {capability}: {reason}",
            details={"capability": capability, "reason": reason},
        )
