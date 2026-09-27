"""Assembles the router and middleware into a callable service."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from middleware import MiddlewarePipeline
from router import Router


@dataclass
class Response:
    """A minimal response object."""

    status: int
    body: Any = None
    headers: dict[str, str] = field(default_factory=dict)


class RequestService:
    """Dispatches requests through the router and middleware chain."""

    def __init__(self) -> None:
        self.router = Router()
        self.middlewares = MiddlewarePipeline()

    def route(self, method: str, pattern: str):  # noqa: ANN201 - decorator
        """Register a handler via decorator syntax."""

        def decorator(handler):  # noqa: ANN001, ANN202
            self.router.add_route(method, pattern, handler)
            return handler

        return decorator

    def use(self, middleware):  # noqa: ANN001, ANN201
        """Register a middleware."""
        self.middlewares.use(middleware)
        return middleware

    def handle(self, method: str, path: str) -> Response:
        """Dispatch a request.

        Returns 200 on a match, 404 when nothing matches, and 400 when a handler
        raises ``ValueError`` — that exception must not escape.
        """
        # TODO: dispatch through the middleware chain and map the outcomes.
        raise NotImplementedError
