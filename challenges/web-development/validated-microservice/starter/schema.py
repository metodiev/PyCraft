"""Declarative field-level validation for request bodies.

A :class:`Schema` maps field names onto :class:`Field` definitions. Validation
coerces values from their wire representation, applies constraints, and reports
**every** problem it finds rather than stopping at the first one.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from errors import FieldError, ValidationError

STR = "str"
INT = "int"
FLOAT = "float"
BOOL = "bool"
LIST = "list"
OBJECT = "object"

# Wire strings that count as booleans.
TRUE_STRINGS = frozenset({"true", "1", "yes", "on"})
FALSE_STRINGS = frozenset({"false", "0", "no", "off"})


class _Missing:
    """Sentinel meaning "no default was declared"."""

    __slots__ = ()

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return "MISSING"


MISSING = _Missing()


class _Invalid:
    """Sentinel meaning "this value could not be coerced"."""

    __slots__ = ()

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return "INVALID"


INVALID = _Invalid()


@dataclass
class Field:
    """One declared field of a :class:`Schema`.

    ``default`` is only consulted when the key is *absent* from the payload — a
    present falsy value (``0``, ``""``, ``False``, ``[]``) is a real value and
    must survive validation. A default may be mutable, so it must be copied
    into each result rather than shared between payloads.
    """

    type: str = STR
    required: bool = True
    default: Any = MISSING
    nullable: bool = False
    min_length: int | None = None
    max_length: int | None = None
    ge: float | None = None
    le: float | None = None
    choices: Sequence[Any] | None = None
    item: Field | None = None
    fields: Mapping[str, Field] | None = None


class Schema:
    """A mapping of field names onto :class:`Field` definitions."""

    def __init__(self, fields: Mapping[str, Field]) -> None:
        self.fields: dict[str, Field] = dict(fields)

    def validate(self, data: Any) -> dict[str, Any]:
        """Coerce and check ``data``, returning a new mapping.

        Only declared fields appear in the result. Every problem found is
        collected and raised as a single :class:`~errors.ValidationError` whose
        ``details`` hold one :class:`~errors.FieldError` per problem, each with
        the dotted path to the offending value (``tags[1]``, ``owner.email``).
        The caller's mapping must not be mutated.
        """
        # TODO: walk the declared fields, coerce each value, collect every
        # FieldError, and raise ValidationError once if any were found.
        raise NotImplementedError
