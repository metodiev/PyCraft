"""Request dispatch, dependency injection and error mapping.

This module is the seam where the other two meet: ``schema`` decides whether a
payload is acceptable, ``errors`` decides what a failure should look like over
the wire, and this module decides *when* each of them runs.
"""

from __future__ import annotations

import inspect
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import parse_qsl, urlsplit

from errors import ApiError, MethodNotAllowedError, NotFoundError, status_for
from schema import Schema

SINGLETON = "singleton"
REQUEST = "request"


@dataclass
class Request:
    """An inbound request, modelled as a plain object.

    ``query`` maps a parameter name onto the *list* of values it carried, so a
    repeated key is not silently collapsed.
    """

    method: str
    path: str
    body: Any = None
    query: dict[str, list[str]] = field(default_factory=dict)
    headers: dict[str, str] = field(default_factory=dict)

    @classmethod
    def from_target(
        cls,
        method: str,
        target: str,
        *,
        body: Any = None,
        headers: Mapping[str, str] | None = None,
    ) -> Request:
        """Build a request from a raw target such as ``/items?page=2&tag=a``.

        The method is upper-cased; ``path`` is everything before the ``?`` and
        the query string is split on ``&``/``=`` with ``+`` meaning space.
        """
        # TODO: split the target, percent-decode the query pairs and group
        # repeated keys into lists.
        raise NotImplementedError


@dataclass
class Response:
    """An outbound response."""

    status: int
    body: Any = None
    headers: dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class Route:
    """A registered handler plus everything needed to call it."""

    method: str
    pattern: str
    handler: Callable[..., Any]
    schema: Schema | None = None
    dependencies: tuple[str, ...] = ()
    payload_name: str = "payload"


class Scope:
    """Per-request cache of resolved dependencies.

    A request-scoped dependency is built **at most once per scope**; every
    teardown runs exactly once, in reverse construction order, when the scope
    closes — including when the handler raised.
    """

    def __init__(self, container: Container, request: Request | None = None) -> None:
        self.container = container
        self.request = request
        self._instances: dict[str, Any] = {}
        self._closed = False

    def resolve(self, name: str) -> Any:
        """Return the dependency registered under ``name``.

        A ``"singleton"`` dependency comes from the container; a ``"request"``
        one is constructed on first use and cached on this scope only, so two
        requests never share it.
        """
        # TODO: resolve and cache, remembering any teardown for close().
        raise NotImplementedError

    def close(self) -> None:
        """Tear the scope down; safe to call more than once.

        Teardowns run even when the handler raised, and must not be able to
        turn a failure into a different one.
        """
        # TODO: run the registered teardowns once, newest first.
        raise NotImplementedError


@dataclass(frozen=True)
class _Definition:
    name: str
    factory: Callable[..., Any]
    scope: str = REQUEST
    teardown: Callable[[Any], None] | None = None


class Container:
    """Registers factories and hands out instances at the right lifetime."""

    def __init__(self) -> None:
        self._definitions: dict[str, _Definition] = {}
        self._singletons: dict[str, Any] = {}

    def register(
        self,
        name: str,
        factory: Callable[..., Any],
        *,
        scope: str = REQUEST,
        teardown: Callable[[Any], None] | None = None,
    ) -> None:
        """Register ``factory`` under ``name``.

        The factory receives the resolving :class:`Scope` as its single
        argument. ``scope`` is either ``REQUEST`` or ``SINGLETON``; anything
        else is a ``ValueError``, and a singleton may not declare a teardown.
        """
        # TODO: validate the scope and store the definition.
        raise NotImplementedError

    def create_scope(self, request: Request | None = None) -> Scope:
        """Open a scope for one request."""
        return Scope(self, request)

    def resolve(self, name: str, scope: Scope | None = None) -> Any:
        """Resolve ``name`` outside a handler.

        A ``REQUEST``-scoped name without a scope is a ``LookupError``: the
        caller reached for something it cannot legitimately own. An unknown
        name is a ``LookupError`` too.
        """
        # TODO: resolve through the scope, or the container for singletons.
        raise NotImplementedError

    def _definition(self, name: str) -> _Definition:
        try:
            return self._definitions[name]
        except KeyError:
            raise LookupError(f"no dependency registered under {name!r}") from None

    def _resolve_singleton(self, name: str, scope: Scope | None) -> Any:
        if name not in self._singletons:
            self._singletons[name] = self._definitions[name].factory(scope)
        return self._singletons[name]


class Application:
    """Routes requests, injects dependencies and maps failures onto responses."""

    def __init__(self, container: Container | None = None) -> None:
        self.container = container if container is not None else Container()
        self.routes: list[Route] = []

    def add_route(
        self,
        method: str,
        pattern: str,
        handler: Callable[..., Any],
        *,
        schema: Schema | None = None,
        dependencies: Iterable[str] = (),
        payload_name: str = "payload",
    ) -> Callable[..., Any]:
        """Register ``handler``, returning it so this can be used as a decorator."""
        self.routes.append(
            Route(
                method=method.upper(),
                pattern=pattern,
                handler=handler,
                schema=schema,
                dependencies=tuple(dependencies),
                payload_name=payload_name,
            )
        )
        return handler

    def route(
        self,
        method: str,
        pattern: str,
        *,
        schema: Schema | None = None,
        dependencies: Iterable[str] = (),
        payload_name: str = "payload",
    ) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
        """Decorator form of :meth:`add_route`."""

        def decorator(handler: Callable[..., Any]) -> Callable[..., Any]:
            return self.add_route(
                method,
                pattern,
                handler,
                schema=schema,
                dependencies=dependencies,
                payload_name=payload_name,
            )

        return decorator

    def handle(self, request: Request) -> Response:
        """Dispatch ``request`` and always return a :class:`Response`.

        Nothing escapes: the handler is called with its path parameters, its
        validated payload and its dependencies injected by name; results and
        failures alike come back as a :class:`Response`. The request scope is
        closed exactly once on every path.
        """
        # TODO: open a scope, dispatch, translate exceptions into responses,
        # and always close the scope.
        raise NotImplementedError

    # --- internals -------------------------------------------------------
    def _dispatch(self, request: Request, scope: Scope) -> Response:
        """Match, validate, inject and invoke. Raises; :meth:`handle` maps it.

        Signature-based injection is the point: a handler named
        ``def create(payload, request, users)`` is called with a validated
        payload, the ``Request`` itself and the ``users`` dependency, while a
        handler that does not ask for them is not given them.
        """
        # TODO: match the route, validate the body, resolve dependencies and
        # call the handler with only the parameters it declares.
        raise NotImplementedError

    def _error_response(self, error: Exception) -> Response:
        """Turn ``error`` into a response using :func:`errors.status_for`."""
        # TODO: an ApiError contributes its JSON body; anything else must not
        # leak its text to the caller.
        raise NotImplementedError

    def _match(self, method: str, path: str) -> tuple[Route, dict[str, str]] | None:
        """Return ``(route, path_params)`` for a match, else ``None``.

        A trailing slash is ignored, and a literal segment beats ``{name}``
        whatever the registration order.
        """
        # TODO: match segments, preferring the most specific route.
        raise NotImplementedError
