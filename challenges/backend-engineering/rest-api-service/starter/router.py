"""Path routing.

Supports ``{name}`` placeholders and prefers the most specific match.
Tests import ``Router`` from here.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any


class Router:
    """Maps (method, path) onto handlers."""

    def __init__(self) -> None:
        self._routes: list[tuple[str, str, Callable[..., Any]]] = []

    def add_route(self, method: str, pattern: str, handler: Callable[..., Any]) -> None:
        """Register ``handler`` for ``method`` and ``pattern``."""
        # TODO: store the route. Methods should match case-insensitively.
        raise NotImplementedError

    def match(self, method: str, path: str) -> tuple[Callable[..., Any], dict[str, str]] | None:
        """Return ``(handler, params)`` for a match, else ``None``.

        A literal segment must win over a placeholder, and a trailing slash
        must not affect matching.
        """
        # TODO: implement matching.
        raise NotImplementedError
