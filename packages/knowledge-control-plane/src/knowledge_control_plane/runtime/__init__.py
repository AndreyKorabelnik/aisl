"""Durable unified runtime backend for knowledge-control-plane."""

from .settings import RuntimeSettings


def create_runtime_app(settings: RuntimeSettings | None = None):
    """Import the FastAPI assembly lazily to keep domain services acyclic."""

    from .app import create_runtime_app as factory

    return factory(settings)


__all__ = ["RuntimeSettings", "create_runtime_app"]
