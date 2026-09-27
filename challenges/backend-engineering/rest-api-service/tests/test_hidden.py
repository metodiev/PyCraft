"""Hidden tests — the design details that separate a working router from a good one."""

import pytest

from middleware import MiddlewarePipeline
from router import Router
from service import RequestService


# --- routing specificity -------------------------------------------------
def test_literal_segment_beats_placeholder():
    """The classic routing bug: a placeholder swallowing a fixed path."""
    router = Router()
    router.add_route("GET", "/users/{user_id}", lambda user_id: f"param:{user_id}")
    router.add_route("GET", "/users/me", lambda: "literal")

    match = router.match("GET", "/users/me")
    assert match is not None
    handler, params = match
    assert handler(**params) == "literal"


def test_literal_wins_regardless_of_registration_order():
    router = Router()
    router.add_route("GET", "/users/me", lambda: "literal")
    router.add_route("GET", "/users/{user_id}", lambda user_id: f"param:{user_id}")

    match = router.match("GET", "/users/me")
    assert match is not None
    handler, params = match
    assert handler(**params) == "literal"


def test_more_specific_pattern_wins():
    router = Router()
    router.add_route("GET", "/a/{b}/c/{d}", lambda **kw: "generic")
    router.add_route("GET", "/a/x/c/{d}", lambda **kw: "specific")

    match = router.match("GET", "/a/x/c/y")
    assert match is not None
    handler, _ = match
    assert handler() == "specific"


def test_trailing_slash_is_ignored():
    router = Router()
    router.add_route("GET", "/users", lambda: "list")

    for path in ("/users", "/users/"):
        match = router.match("GET", path)
        assert match is not None, path


def test_trailing_slash_ignored_with_parameters():
    router = Router()
    router.add_route("GET", "/users/{user_id}", lambda user_id: user_id)

    match = router.match("GET", "/users/42/")
    assert match is not None
    _, params = match
    assert params == {"user_id": "42"}


def test_root_path_matches():
    router = Router()
    router.add_route("GET", "/", lambda: "root")

    match = router.match("GET", "/")
    assert match is not None
    handler, _ = match
    assert handler() == "root"


def test_segment_count_must_match():
    router = Router()
    router.add_route("GET", "/a/b", lambda: "two")

    assert router.match("GET", "/a") is None
    assert router.match("GET", "/a/b/c") is None


def test_wrong_method_does_not_match():
    router = Router()
    router.add_route("GET", "/health", lambda: "ok")

    assert router.match("POST", "/health") is None


def test_method_is_case_insensitive():
    router = Router()
    router.add_route("get", "/health", lambda: "ok")

    assert router.match("GET", "/health") is not None


def test_multiple_parameters_are_all_extracted():
    router = Router()
    router.add_route("GET", "/orgs/{org}/repos/{repo}", lambda org, repo: f"{org}/{repo}")

    match = router.match("GET", "/orgs/acme/repos/api")
    assert match is not None
    handler, params = match
    assert params == {"org": "acme", "repo": "api"}
    assert handler(**params) == "acme/api"


# --- middleware onion ----------------------------------------------------
def _tagger(label: str, log: list[str]):
    def middleware(handler):
        def wrapped(*args, **kwargs):
            log.append(f"{label}:in")
            result = handler(*args, **kwargs)
            log.append(f"{label}:out")
            return result

        return wrapped

    return middleware


def test_outermost_middleware_runs_first():
    """Applying in the wrong order silently reverses the onion."""
    log: list[str] = []

    def handler():
        log.append("handler")
        return "ok"

    wrapped = MiddlewarePipeline([_tagger("first", log), _tagger("second", log)]).wrap(handler)
    wrapped()

    assert log == ["first:in", "second:in", "handler", "second:out", "first:out"]


def test_use_is_chainable_and_ordered():
    log: list[str] = []

    def handler():
        log.append("handler")
        return "ok"

    pipeline = MiddlewarePipeline()
    result = pipeline.use(_tagger("a", log)).use(_tagger("b", log))
    assert result is pipeline

    pipeline.wrap(handler)()
    assert log == ["a:in", "b:in", "handler", "b:out", "a:out"]


def test_empty_pipeline_is_a_passthrough():
    wrapped = MiddlewarePipeline().wrap(lambda x: x * 2)
    assert wrapped(21) == 42


def test_middleware_can_short_circuit():
    called: list[str] = []

    def blocking(handler):
        def wrapped(*args, **kwargs):
            called.append("blocked")
            return "short"

        return wrapped

    def handler():
        called.append("handler")
        return "reached"

    wrapped = MiddlewarePipeline([blocking]).wrap(handler)
    assert wrapped() == "short"
    assert called == ["blocked"]


# --- service behaviour ---------------------------------------------------
def test_handler_receives_path_parameters():
    service = RequestService()
    service.route("GET", "/users/{user_id}")(lambda user_id: {"id": user_id})

    response = service.handle("GET", "/users/7")
    assert response.status == 200
    assert response.body == {"id": "7"}


def test_value_error_becomes_400():
    """A handler's ValueError must not escape as a crash."""
    service = RequestService()

    def failing():
        raise ValueError("bad input")

    service.route("GET", "/boom")(failing)

    response = service.handle("GET", "/boom")
    assert response.status == 400


def test_not_found_has_a_body():
    service = RequestService()
    response = service.handle("GET", "/missing")

    assert response.status == 404
    assert response.body is not None


def test_middleware_can_observe_every_request():
    service = RequestService()
    seen: list[str] = []

    @service.use
    def recorder(handler):
        def wrapped(method, path):
            seen.append(f"{method} {path}")
            return handler(method, path)

        return wrapped

    service.route("GET", "/a")(lambda: "a")
    service.route("GET", "/b")(lambda: "b")

    service.handle("GET", "/a")
    service.handle("GET", "/b")

    assert seen == ["GET /a", "GET /b"]


def test_middleware_can_short_circuit_a_request():
    service = RequestService()

    @service.use
    def guard(handler):
        def wrapped(method, path):
            if path == "/secret":
                from service import Response

                return Response(403, {"error": "Forbidden"})
            return handler(method, path)

        return wrapped

    service.route("GET", "/secret")(lambda: "leaked")

    response = service.handle("GET", "/secret")
    assert response.status == 403
    assert response.body != "leaked"


def test_routes_survive_multiple_dispatches():
    """Registration must not be consumed by the first match."""
    service = RequestService()
    service.route("GET", "/count")(lambda: "hit")

    for _ in range(5):
        assert service.handle("GET", "/count").status == 200


def test_service_does_not_expose_the_routers_internals():
    """The modules must stay separable; reaching across the seam is a smell."""
    service = RequestService()
    service.route("GET", "/x")(lambda: "x")

    assert service.handle("GET", "/x").status == 200
    # The pipeline and router are distinct collaborators.
    assert service.router is not service.middlewares
