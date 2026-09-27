"""Visible tests — the basic contract of each module.

These are the tests the learner can run while working. They cover the happy
paths and the shape of each interface; the deeper design requirements are
graded separately.
"""

import pytest

from errors import ConflictError, FieldError, NotFoundError, ValidationError, status_for
from schema import BOOL, FLOAT, INT, MISSING, STR, Field, Schema
from service import Application, Container, Request, Response


# --- schema.py -----------------------------------------------------------
def test_schema_accepts_a_valid_payload():
    schema = Schema({"name": Field(STR, min_length=1, max_length=10)})

    assert schema.validate({"name": "ada"}) == {"name": "ada"}


def test_schema_coerces_wire_values():
    schema = Schema({"count": Field(INT), "scale": Field(FLOAT), "live": Field(BOOL)})

    assert schema.validate({"count": "42", "scale": "1.5", "live": "true"}) == {
        "count": 42,
        "scale": 1.5,
        "live": True,
    }


def test_missing_required_field_is_reported():
    schema = Schema({"name": Field(STR)})

    with pytest.raises(ValidationError) as caught:
        schema.validate({})

    assert [detail.path for detail in caught.value.details] == ["name"]
    assert caught.value.details[0].code == "missing"


def test_constraint_violation_is_reported():
    schema = Schema({"age": Field(INT, ge=18, le=120)})

    with pytest.raises(ValidationError) as caught:
        schema.validate({"age": 17})

    assert [detail.path for detail in caught.value.details] == ["age"]
    assert caught.value.details[0].code == "too_small"


def test_choices_are_enforced():
    schema = Schema({"role": Field(STR, choices=["admin", "member"])})

    with pytest.raises(ValidationError):
        schema.validate({"role": "root"})

    assert schema.validate({"role": "member"}) == {"role": "member"}


def test_optional_field_falls_back_to_its_default():
    schema = Schema({"limit": Field(INT, required=False, default=20)})

    assert schema.validate({}) == {"limit": 20}
    assert schema.validate({"limit": "5"}) == {"limit": 5}


def test_undeclared_keys_are_dropped():
    schema = Schema({"name": Field(STR)})

    assert schema.validate({"name": "ada", "admin": True}) == {"name": "ada"}


# --- errors.py -----------------------------------------------------------
def test_error_status_mapping():
    assert status_for(ValidationError()) == 422
    assert status_for(NotFoundError()) == 404
    assert status_for(ConflictError()) == 409


def test_error_body_is_json_ready():
    error = ValidationError(
        "payload is invalid",
        details=[FieldError("name", "missing", "field is required")],
    )

    assert error.to_body() == {
        "error": {
            "code": "validation_error",
            "message": "payload is invalid",
            "details": [{"path": "name", "code": "missing", "message": "field is required"}],
        }
    }


def test_api_errors_subclass_exception():
    with pytest.raises(NotFoundError):
        raise NotFoundError("gone")


# --- service.py ----------------------------------------------------------
def test_request_parses_a_query_string():
    request = Request.from_target("get", "/items?page=2")

    assert request.method == "GET"
    assert request.path == "/items"
    assert request.query == {"page": ["2"]}


def test_application_dispatches_a_request():
    app = Application()
    app.route("GET", "/ping")(lambda: {"pong": True})

    response = app.handle(Request("GET", "/ping"))

    assert isinstance(response, Response)
    assert response.status == 200
    assert response.body == {"pong": True}


def test_unknown_route_is_a_404():
    app = Application()

    response = app.handle(Request("GET", "/missing"))

    assert response.status == 404
    assert response.body["error"]["code"] == "not_found"


def test_invalid_payload_is_a_422():
    app = Application()
    app.route("POST", "/items", schema=Schema({"name": Field(STR)}))(
        lambda payload: payload
    )

    response = app.handle(Request("POST", "/items", body={}))

    assert response.status == 422
    assert response.body["error"]["code"] == "validation_error"


def test_validated_payload_reaches_the_handler():
    app = Application()
    app.route("POST", "/items", schema=Schema({"count": Field(INT, ge=0)}))(
        lambda payload: payload
    )

    response = app.handle(Request("POST", "/items", body={"count": "3"}))

    assert response.status == 200
    assert response.body == {"count": 3}


def test_container_builds_a_dependency_per_request():
    container = Container()
    calls: list[str] = []

    def factory(scope):
        calls.append("built")
        return {"seen": scope.request}

    container.register("db", factory)

    app = Application(container)
    app.route("GET", "/x", dependencies=["db"])(lambda db: {"ok": True})

    assert app.handle(Request("GET", "/x")).status == 200
    assert calls == ["built"]


def test_scope_teardown_runs_after_a_successful_request():
    container = Container()
    closed: list[str] = []

    class Session:
        pass

    container.register(
        "session",
        lambda scope: Session(),
        teardown=lambda session: closed.append("closed"),
    )

    app = Application(container)
    app.route("GET", "/x", dependencies=["session"])(lambda session: "ok")

    assert app.handle(Request("GET", "/x")).status == 200
    assert closed == ["closed"]


def test_container_rejects_an_unknown_scope():
    container = Container()

    with pytest.raises(ValueError):
        container.register("db", lambda scope: object(), scope="galaxy")


def test_handler_returning_none_is_204():
    app = Application()
    app.route("DELETE", "/items/{item_id}")(lambda item_id: None)

    assert app.handle(Request("DELETE", "/items/7")).status == 204


def test_path_parameters_are_injected_by_name():
    app = Application()
    app.route("GET", "/users/{user_id}/posts/{post_id}")(
        lambda user_id, post_id: {"user": user_id, "post": post_id}
    )

    response = app.handle(Request("GET", "/users/7/posts/9"))

    assert response.status == 200
    assert response.body == {"user": "7", "post": "9"}


def test_missing_default_sentinel_is_exported():
    """``MISSING`` marks "no default"; it must not be a plain ``None``."""
    assert MISSING is not None
    assert Field(STR).default is MISSING
