"""Reconcile desired infrastructure against observed state.

The tests import ``dependency_graph``, ``diff_resources``, ``plan`` and
``resource_type`` from here.
"""

from __future__ import annotations


def resource_type(address: str) -> str:
    """Return the type half of a ``type.name`` resource address.

    >>> resource_type("aws_vpc.main")
    'aws_vpc'
    """
    # TODO: split on the first dot and reject malformed addresses.
    raise NotImplementedError("Complete the resource_type function")


def dependency_graph(resources):
    """Map every resource address to the sorted addresses it references.

    A reference is ``${<address>}`` or ``${<address>.<attribute>}`` inside any
    attribute value, however deeply nested.

    >>> dependency_graph({"aws_subnet.public": {"vpc_id": "${aws_vpc.main.id}"}})
    {'aws_subnet.public': ['aws_vpc.main']}
    """
    # TODO: resolve interpolations against the known addresses.
    raise NotImplementedError("Complete the dependency_graph function")


def diff_resources(desired, actual, immutable=None):
    """Classify every resource as create, update, replace, delete or no-op.

    Returns one dict per address in ``sorted(desired | actual)`` order.
    """
    # TODO: compare the attributes the configuration declares and let the
    # per-type ``immutable`` sets decide between update and replace.
    raise NotImplementedError("Complete the diff_resources function")


def plan(desired, actual, immutable=None):
    """Return ``{"changes": [...], "summary": {...}}`` for the whole plan."""
    # TODO: diff, then order applies by dependency and destroys in reverse.
    raise NotImplementedError("Complete the plan function")
