"""Visible tests — the basic contract for each module."""

from middleware import MiddlewarePipeline
from router import Router
from service import RequestService, Response


def test_router_matches_a_literal_path():
    router = Router()
    router.add_route("GET", "/health", lambda: "ok")

    match = router.match("GET", "/health")
    assert match is not None
    handler, params = match
    assert handler() == "ok"
    assert params == {}


def test_router_extracts_parameters():
    router = Router()
    router.add_route("GET", "/users/{user_id}", lambda user_id: user_id)

    match = router.match("GET", "/users/42")
    assert match is not None
    handler, params = match
    assert params == {"user_id": "42"}
    assert handler(**params) == "42"


def test_router_returns_none_for_unknown_path():
    router = Router()
    router.add_route("GET", "/health", lambda: "ok")
    assert router.match("GET", "/nope") is None


def test_service_dispatches_a_request():
    service = RequestService()
    service.route("GET", "/ping")(lambda: "pong")

    response = service.handle("GET", "/ping")
    assert isinstance(response, Response)
    assert response.status == 200
    assert response.body == "pong"


def test_service_returns_404():
    service = RequestService()
    response = service.handle("GET", "/missing")

    assert response.status == 404


def test_middleware_runs_around_the_handler():
    order: list[str] = []

    def middleware(handler):
        def wrapped(*args, **kwargs):
            order.append("before")
            result = handler(*args, **kwargs)
            order.append("after")
            return result

        return wrapped

    def handler():
        order.append("handler")
        return "done"

    wrapped = MiddlewarePipeline([middleware]).wrap(handler)
    assert wrapped() == "done"
    assert order == ["before", "handler", "after"]
