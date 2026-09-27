"""Typed API errors, their HTTP status mapping and a JSON-ready error body.

This module is the leaf of the three: it must not import ``schema`` or
``service``, so both of those can depend on it without a cycle.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class FieldError:
    """One field-level problem discovered while validating a payload."""

    path: str
    code: str
    message: str

    def to_dict(self) -> dict[str, str]:
        """Return ``{"path": ..., "code": ..., "message": ...}``."""
        return {"path": self.path, "code": self.code, "message": self.message}


class ApiError(Exception):
    """Base class for every error that maps onto an HTTP status.

    Subclasses declare ``status``, ``code`` and ``default_message``; the status
    of an instance is therefore a property of *its class*, not of the call site
    that raised it.
    """

    status = 500
    code = "internal_error"
    default_message = "Internal server error"

    def __init__(self, message: str | None = None, *, details: Sequence[FieldError] = ()) -> None:
        """Store ``message`` (falling back to ``default_message``) and ``details``.

        ``self.message`` and ``self.details`` (a tuple) are part of the
        contract; so is calling ``Exception.__init__`` with the message.
        """
        # TODO: keep the message on the exception and the details alongside it.
        raise NotImplementedError

    def to_body(self) -> dict[str, Any]:
        """Return the JSON-serialisable error body:

        ``{"error": {"code": ..., "message": ..., "details": [<FieldError.to_dict()>, ...]}}``
        """
        # TODO: build the nested error body described above.
        raise NotImplementedError


class ValidationError(ApiError):
    """The payload did not satisfy its schema."""

    status = 422
    code = "validation_error"
    default_message = "Request payload is invalid"


class NotFoundError(ApiError):
    """Nothing matched the request."""

    status = 404
    code = "not_found"
    default_message = "Resource not found"


class MethodNotAllowedError(ApiError):
    """The path exists, but not for this method."""

    status = 405
    code = "method_not_allowed"
    default_message = "Method not allowed"

    def __init__(
        self,
        message: str | None = None,
        *,
        details: Sequence[FieldError] = (),
        allowed: Iterable[str] = (),
    ) -> None:
        """Like ``ApiError``, plus ``allowed``: the methods this path does accept.

        ``self.allowed`` is a tuple, and ``to_body`` adds
        ``body["error"]["allowed"]`` as a list on top of the base body.
        """
        # TODO: forward to the base class and remember the allowed methods.
        raise NotImplementedError

    def to_body(self) -> dict[str, Any]:
        """Return the base error body with ``allowed`` added to the error object."""
        # TODO: extend ApiError.to_body() with the allowed methods.
        raise NotImplementedError


class ConflictError(ApiError):
    """The request conflicts with the current state of the resource."""

    status = 409
    code = "conflict"
    default_message = "Request conflicts with the current state"


def status_for(error: Exception) -> int:
    """Return the HTTP status for ``error``.

    An ``ApiError`` reports its own ``status``; anything else is an internal
    failure and must map to 500 — never to a status that blames the caller.
    """
    # TODO: map the error onto a status code.
    raise NotImplementedError
