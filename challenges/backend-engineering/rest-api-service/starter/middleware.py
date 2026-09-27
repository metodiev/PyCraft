"""Middleware composition.

Middlewares wrap a handler. The first middleware in the list is the outermost,
so it sees the request first and the response last.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

Handler = Callable[..., Any]


class MiddlewarePipeline:
    """Wraps a handler in a chain of middlewares."""

    def __init__(self, middlewares: list[Callable[[Handler], Handler]] | None = None) -> None:
        self.middlewares = list(middlewares or [])

    def use(self, middleware: Callable[[Handler], Handler]) -> MiddlewarePipeline:
        """Append a middleware. Returns self so calls can be chained."""
        # TODO: append and return self.
        raise NotImplementedError

    def wrap(self, handler: Handler) -> Handler:
        """Return ``handler`` wrapped by every middleware.

        Applying them in the wrong order silently reverses the onion, which the
        tests check for explicitly.
        """
        # TODO: wrap the handler.
        raise NotImplementedError
