"""Hidden tests — the design details that separate a working service from a good one.

Every test here targets a mistake that a plausible implementation makes and
that the visible suite does not exercise: validation that stops at the first
error, falsy values mistaken for missing ones, a mutable default shared between
requests, a dependency cached globally instead of per request, skipped teardown
when the handler raises, and error statuses that blame the caller for a server
fault.
"""

import copy
from collections import Counter

import pytest
from errors import (
    ApiError,
    ConflictError,
    FieldError,
    MethodNotAllowedError,
    NotFoundError,
    ValidationError,
    status_for,
)
from schema import BOOL, FLOAT, INT, LIST, OBJECT, STR, Field, Schema
from service import SINGLETON, Application, Container, Request, Response




# --- schema: reporting every problem -------------------------------------
def test_all_problems_are_reported_not_just_the_first():
    """Stopping at the first error is the single most common validation bug."""
    schema = Schema(
        {
            "name": Field(STR, min_length=1),
            "age": Field(INT, ge=0),
            "role": Field(STR, choices=["admin", "member"]),
        }
    )

    with pytest.raises(ValidationError) as caught:
        schema.validate({"name": "", "age": -1, "role": "root"})

    paths = sorted(detail.path for detail in caught.value.details)
    codes = sorted(detail.code for detail in caught.value.details)
    assert paths == ["age", "name", "role"]
    assert codes == ["choice", "too_short", "too_small"]


def test_a_missing_field_does_not_stop_later_fields_being_checked():
    schema = Schema({"name": Field(STR), "age": Field(INT)})

    with pytest.raises(ValidationError) as caught:
        schema.validate({"age": "nope"})

    assert sorted(detail.path for detail in caught.value.details) == ["age", "name"]


def test_details_are_field_errors_with_paths():
    schema = Schema({"owner": Field(OBJECT, fields={"email": Field(STR, min_length=3)})})

    with pytest.raises(ValidationError) as caught:
        schema.validate({"owner": {"email": ""}})

    assert caught.value.details[0].path == "owner.email"
    assert isinstance(caught.value.details[0], FieldError)


def test_list_items_are_reported_with_their_index():
    schema = Schema({"tags": Field(LIST, item=Field(STR, min_length=2))})

    with pytest.raises(ValidationError) as caught:
        schema.validate({"tags": ["ok", "x", "fine", "y"]})

    assert [detail.path for detail in caught.value.details] == ["tags[1]", "tags[3]"]


# --- schema: optional vs falsy -------------------------------------------
def test_zero_is_not_missing():
    """``0`` is a value, not the absence of one."""
    schema = Schema({"limit": Field(INT, required=False, default=20, ge=0)})

    assert schema.validate({"limit": 0}) == {"limit": 0}
    assert schema.validate({"limit": "0"}) == {"limit": 0}


def test_empty_string_is_not_missing():
    schema = Schema({"comment": Field(STR, required=False, default="none")})

    assert schema.validate({"comment": ""}) == {"comment": ""}


def test_false_is_not_missing():
    schema = Schema({"enabled": Field(BOOL, required=False, default=True)})

    assert schema.validate({"enabled": False}) == {"enabled": False}
    assert schema.validate({"enabled": "false"}) == {"enabled": False}


def test_empty_list_is_not_missing():
    schema = Schema({"tags": Field(LIST, item=Field(STR), required=False, default=["all"])})

    assert schema.validate({"tags": []}) == {"tags": []}


def test_absent_optional_field_still_uses_the_default():
    schema = Schema({"comment": Field(STR, required=False, default="none")})

    assert schema.validate({}) == {"comment": "none"}


def test_absent_optional_field_without_a_default_is_omitted():
    schema = Schema({"comment": Field(STR, required=False)})

    assert schema.validate({}) == {}


def test_required_falsy_input_is_accepted():
    schema = Schema({"count": Field(INT, required=True)})

    assert schema.validate({"count": 0}) == {"count": 0}


# --- schema: defaults and immutability -----------------------------------
def test_mutable_default_is_not_shared_between_payloads():
    """A default list must be copied, or two requests share one object."""
    schema = Schema({"tags": Field(LIST, item=Field(STR), required=False, default=["new"])})

    first = schema.validate({})
    second = schema.validate({})
    first["tags"].append("leaked")

    assert second["tags"] == ["new"]


def test_mutable_default_is_not_shared_across_schemas():
    schema = Schema({"tags": Field(LIST, item=Field(STR), required=False, default=[])})

    first = schema.validate({})
    second = schema.validate({})
    assert first["tags"] is not second["tags"]

    first["tags"].append("x")
    assert schema.validate({})["tags"] == []


def test_validate_does_not_mutate_the_caller_payload():
    payload = {"name": "ada", "tags": ["a", "b"], "age": "36"}
    schema = Schema(
        {
            "name": Field(STR),
            "tags": Field(LIST, item=Field(STR)),
            "age": Field(INT),
        }
    )

    result = schema.validate(payload)

    assert payload == {"name": "ada", "tags": ["a", "b"], "age": "36"}
    assert result["age"] == 36
    assert result["tags"] == ["a", "b"]
    assert result["tags"] is not payload["tags"]


def test_nested_validated_objects_are_copies():
    schema = Schema(
        {"owner": Field(OBJECT, fields={"name": Field(STR), "tags": Field(LIST, item=Field(STR))})}
    )
    payload = {"owner": {"name": "ada", "tags": ["x"]}}

    result = schema.validate(payload)
    result["owner"]["tags"].append("y")

    assert payload["owner"]["tags"] == ["x"]


# --- schema: coercion and nullability ------------------------------------
def test_bool_is_not_an_int():
    """``True`` is an ``int`` in Python; the wire contract still says it is not."""
    schema = Schema({"count": Field(INT)})

    with pytest.raises(ValidationError) as caught:
        schema.validate({"count": True})

    assert caught.value.details[0].code == "type"


def test_null_is_rejected_unless_nullable():
    strict = Schema({"note": Field(STR)})
    lenient = Schema({"note": Field(STR, nullable=True)})

    with pytest.raises(ValidationError):
        strict.validate({"note": None})
    assert lenient.validate({"note": None}) == {"note": None}


def test_uncoercible_values_are_reported_as_type_errors():
    schema = Schema({"count": Field(INT), "scale": Field(FLOAT), "live": Field(BOOL)})

    with pytest.raises(ValidationError) as caught:
        schema.validate({"count": "many", "scale": "wide", "live": "perhaps"})

    assert sorted(detail.code for detail in caught.value.details) == ["type", "type", "type"]
    assert sorted(detail.path for detail in caught.value.details) == ["count", "live", "scale"]


def test_nested_object_type_error_uses_the_nested_path():
    schema = Schema({"owner": Field(OBJECT, fields={"name": Field(STR)})})

    with pytest.raises(ValidationError) as caught:
        schema.validate({"owner": "ada"})

    assert caught.value.details[0].path == "owner"
    assert caught.value.details[0].code == "type"


def test_a_valid_payload_is_not_rejected_by_a_sibling_problem():
    schema = Schema({"name": Field(STR), "age": Field(INT)})

    with pytest.raises(ValidationError):
        schema.validate({"name": "ada", "age": "old"})


# --- errors: mapping ------------------------------------------------------
def test_unhandled_exception_maps_to_500():
    assert status_for(RuntimeError("kaboom")) == 500
    assert status_for(KeyError("nope")) == 500


def test_validation_is_422_and_conflict_is_409():
    """422 and 409 are different failures; conflating them lies to the client."""
    assert status_for(ValidationError()) == 422
    assert status_for(ConflictError()) == 409
    assert status_for(ValidationError()) != status_for(ConflictError())


def test_custom_api_error_keeps_its_own_status():
    class TeapotError(ApiError):
        status = 418
        code = "teapot"

    assert status_for(TeapotError()) == 418


def test_message_falls_back_to_the_class_default():
    assert ValidationError().message == ValidationError.default_message
    assert ValidationError("custom").message == "custom"


def test_details_default_to_an_empty_tuple():
    assert ValidationError().details == ()
    assert ValidationError().to_body()["error"]["details"] == []


def test_error_body_carries_every_detail():
    error = ValidationError(
        details=[
            FieldError("a", "missing", "field is required"),
            FieldError("b", "type", "expected an integer"),
        ]
    )

    details = error.to_body()["error"]["details"]
    assert [detail["path"] for detail in details] == ["a", "b"]


def test_method_not_allowed_reports_the_allowed_methods():
    error = MethodNotAllowedError(allowed=["GET", "POST"])

    assert error.status == 405
    assert list(error.allowed) == ["GET", "POST"]
    assert error.to_body()["error"]["allowed"] == ["GET", "POST"]


# --- service: the request scope ------------------------------------------
class Session:
    """A stand-in for a per-request database session."""

    def __init__(self, scope):
        self.scope = scope
        self.open = True
        self.rows: list[str] = []


def _session_container(built: list[Session], closed: list[Session]) -> Container:
    container = Container()

    def factory(scope):
        session = Session(scope)
        built.append(session)
        return session

    container.register("session", factory, teardown=lambda session: closed.append(session))
    return container


def test_dependency_is_constructible_once_per_request():
    """Two handlers asking for the same dependency must share one instance."""
    built: list[Session] = []
    closed: list[Session] = []

    def handler(session):
        return {"opened": session.open}

    def other(session):
        return {"same": True}

    container = _session_container(built, closed)
    app = Application(container)
    app.route("GET", "/a", dependencies=["session"])(handler)
    app.route("GET", "/b", dependencies=["session"])(other)

    assert app.handle(Request("GET", "/a")).status == 200
    assert len(built) == 1
    assert len(closed) == 1


def test_dependency_is_not_shared_between_requests():
    """Caching a request-scoped dependency globally leaks state across requests."""
    built: list[Session] = []
    closed: list[Session] = []

    container = _session_container(built, closed)
    app = Application(container)
    captured: list[Session] = []

    def handler(session):
        captured.append(session)
        session.rows.append("row")
        return {"rows": len(session.rows)}

    app.route("GET", "/a", dependencies=["session"])(handler)

    assert app.handle(Request("GET", "/a")).body == {"rows": 1}
    assert app.handle(Request("GET", "/a")).body == {"rows": 1}
    assert len(built) == 2
    assert captured[0] is not captured[1]
    assert [len(session.rows) for session in captured] == [1, 1]


def test_a_shared_container_does_not_leak_state_between_applications():
    built: list[Session] = []
    closed: list[Session] = []
    container = _session_container(built, closed)

    first = Application(container)
    first.route("GET", "/a", dependencies=["session"])(lambda session: {"n": len(built)})

    second = Application(container)
    second.route("GET", "/a", dependencies=["session"])(lambda session: {"n": len(built)})

    first.handle(Request("GET", "/a"))
    second.handle(Request("GET", "/a"))

    assert len(built) == 2


def test_scope_resolves_the_same_instance_more_than_once():
    built: list[Session] = []
    closed: list[Session] = []
    container = _session_container(built, closed)
    scope = container.create_scope()

    first = scope.resolve("session")
    second = scope.resolve("session")

    assert first is second
    assert len(built) == 1


def test_teardown_cannot_be_run_twice():
    built: list[Session] = []
    closed: list[Session] = []
    container = _session_container(built, closed)
    app = Application(container)
    app.route("GET", "/a", dependencies=["session"])(lambda session: "ok")

    app.handle(Request("GET", "/a"))

    assert len(closed) == 1


def test_a_declared_dependency_the_handler_does_not_use_is_never_built():
    """Resolving every declared name eagerly opens resources nobody asked for."""
    built: list[Session] = []
    closed: list[Session] = []
    container = _session_container(built, closed)
    app = Application(container)
    app.route("GET", "/health", dependencies=["session"])(lambda request: "ok")

    response = app.handle(Request("GET", "/health"))

    assert response.status == 200
    assert built == []
    assert closed == []


def test_a_route_with_no_dependencies_builds_nothing():
    built: list[Session] = []
    closed: list[Session] = []
    container = _session_container(built, closed)
    app = Application(container)
    app.route("GET", "/health")(lambda: "ok")

    app.handle(Request("GET", "/health"))

    assert built == []
    assert closed == []


def test_singleton_is_shared_and_never_torn_down():
    built: list[str] = []
    container = Container()

    def factory(scope):
        built.append("built")
        return object()

    container.register("config", factory, scope=SINGLETON)

    app = Application(container)
    app.route("GET", "/a", dependencies=["config"])(lambda config: "ok")
    app.route("GET", "/b", dependencies=["config"])(lambda config: "ok")

    app.handle(Request("GET", "/a"))
    app.handle(Request("GET", "/b"))

    assert built == ["built"]


def test_teardown_runs_when_the_handler_raises():
    """An unhandled handler exception must not strand an open dependency."""
    built: list[Session] = []
    closed: list[Session] = []
    container = _session_container(built, closed)
    app = Application(container)

    def failing(session):
        raise RuntimeError("handler exploded")

    app.route("GET", "/boom", dependencies=["session"])(failing)

    response = app.handle(Request("GET", "/boom"))

    assert response.status == 500
    assert len(closed) == 1


def test_teardown_runs_when_the_payload_is_invalid():
    built: list[Session] = []
    closed: list[Session] = []
    container = _session_container(built, closed)
    app = Application(container)
    app.route("POST", "/items", schema=Schema({"name": Field(STR)}), dependencies=["session"])(
        lambda payload, session: payload
    )

    response = app.handle(Request("POST", "/items", body={}))

    assert response.status == 422
    # Whatever was opened must have been closed; nothing may be left dangling.
    assert len(closed) == len(built)


def test_teardown_runs_when_the_handler_returns_a_response_early():
    built: list[Session] = []
    closed: list[Session] = []
    container = _session_container(built, closed)
    app = Application(container)
    app.route("GET", "/early", dependencies=["session"])(
        lambda session: Response(201, {"created": True})
    )

    response = app.handle(Request("GET", "/early"))

    assert response.status == 201
    assert len(closed) == 1


def test_teardowns_run_newest_first():
    order: list[str] = []
    container = Container()
    container.register("outer", lambda scope: "o", teardown=lambda value: order.append("outer"))
    container.register(
        "inner", lambda scope: scope.resolve("outer"), teardown=lambda value: order.append("inner")
    )

    app = Application(container)
    app.route("GET", "/a", dependencies=["outer", "inner"])(lambda outer, inner: "ok")
    app.handle(Request("GET", "/a"))

    assert order == ["inner", "outer"]


def test_resolving_a_request_scoped_dependency_without_a_scope_fails():
    container = Container()
    container.register("session", lambda scope: Session(scope))

    with pytest.raises(LookupError):
        container.resolve("session")


def test_unknown_dependency_is_a_lookup_error():
    container = Container()

    with pytest.raises(LookupError):
        container.resolve("nope", container.create_scope())


def test_container_rejects_a_teardown_on_a_singleton():
    container = Container()

    with pytest.raises(ValueError):
        container.register("config", lambda scope: object(), scope=SINGLETON, teardown=lambda _: None)


# --- service: dispatch and error mapping ---------------------------------
def test_validation_error_response_is_422_with_details():
    app = Application()
    app.route("POST", "/items", schema=Schema({"name": Field(STR, min_length=1)}))(
        lambda payload: payload
    )

    response = app.handle(Request("POST", "/items", body={"name": ""}))

    assert response.status == 422
    assert response.body["error"]["code"] == "validation_error"
    assert response.body["error"]["details"][0]["path"] == "name"


def test_conflict_is_409_not_422():
    """A state conflict must not be reported as a payload problem."""
    app = Application()

    def create(payload):
        raise ConflictError("name already exists")

    app.route("POST", "/items", schema=Schema({"name": Field(STR)}))(create)

    response = app.handle(Request("POST", "/items", body={"name": "ada"}))

    assert response.status == 409
    assert response.body["error"]["code"] == "conflict"
    assert "already exists" in response.body["error"]["message"]


def test_not_found_from_a_handler_is_404():
    app = Application()

    def fetch(item_id):
        raise NotFoundError(f"item {item_id} is gone")

    app.route("GET", "/items/{item_id}")(fetch)

    response = app.handle(Request("GET", "/items/9"))

    assert response.status == 404
    assert response.body["error"]["code"] == "not_found"


def test_unknown_exception_is_a_500_without_leaking_details():
    app = Application()

    def crash():
        raise RuntimeError("connection string postgres://secret")

    app.route("GET", "/crash")(crash)

    response = app.handle(Request("GET", "/crash"))

    assert response.status == 500
    assert response.body["error"]["code"] == "internal_error"
    assert "secret" not in str(response.body)


def test_error_body_is_serialisable_by_json():
    import json

    app = Application()
    app.route("POST", "/items", schema=Schema({"name": Field(STR)}))(lambda payload: payload)

    response = app.handle(Request("POST", "/items", body={}))

    json.dumps(response.body)


def test_known_path_with_the_wrong_method_is_405():
    app = Application()
    app.route("GET", "/items")(lambda: [])

    response = app.handle(Request("POST", "/items", body={}))

    assert response.status == 405
    assert set(response.body["error"]["allowed"]) == {"GET"}


def test_no_exception_ever_escapes_handle():
    app = Application()
    app.route("GET", "/x", dependencies=["missing"])(lambda missing: "ok")

    response = app.handle(Request("GET", "/x"))

    assert response.status == 500


def test_handler_can_return_a_response_verbatim():
    app = Application()
    app.route("GET", "/custom")(lambda: Response(202, {"queued": True}, {"retry-after": "1"}))

    response = app.handle(Request("GET", "/custom"))

    assert response.status == 202
    assert response.headers == {"retry-after": "1"}


def test_query_parameters_are_grouped_not_collapsed():
    request = Request.from_target("GET", "/items?tag=a&tag=b&page=2")

    assert request.query["tag"] == ["a", "b"]
    assert request.query["page"] == ["2"]


def test_blank_query_values_are_kept():
    request = Request.from_target("GET", "/items?q=")

    assert request.query == {"q": [""]}


def test_target_is_split_at_the_first_question_mark():
    request = Request.from_target("POST", "/items/1?verbose=true")

    assert request.path == "/items/1"
    assert request.query == {"verbose": ["true"]}


def test_escaped_query_values_are_decoded():
    request = Request.from_target("GET", "/search?q=hello+world&filter=a%2Fb")

    assert request.query["q"] == ["hello world"]
    assert request.query["filter"] == ["a/b"]


def test_handler_supplies_its_own_query_handling():
    app = Application()
    app.route("GET", "/items")(lambda request: {"page": request.query.get("page", ["1"])[0]})

    response = app.handle(Request.from_target("GET", "/items?page=3"))

    assert response.body == {"page": "3"}


def test_path_parameters_are_strings_and_do_not_shadow_dependencies():
    app = Application()
    app.route("GET", "/users/{user_id}")(lambda user_id: {"id": user_id})

    response = app.handle(Request("GET", "/users/42"))

    assert response.body == {"id": "42"}


def test_literal_segment_beats_a_placeholder_regardless_of_order():
    def literal_handler():
        return "literal"

    def parameterised_handler(item_id):
        return f"param:{item_id}"

    for placeholder_first in (True, False):
        app = Application()
        if placeholder_first:
            app.add_route("GET", "/items/{item_id}", parameterised_handler)
            app.add_route("GET", "/items/new", literal_handler)
        else:
            app.add_route("GET", "/items/new", literal_handler)
            app.add_route("GET", "/items/{item_id}", parameterised_handler)

        assert app.handle(Request("GET", "/items/new")).body == "literal"


def test_trailing_slash_is_ignored_when_dispatching():
    app = Application()
    app.route("GET", "/items")(lambda: "list")

    assert app.handle(Request("GET", "/items/")).status == 200
    assert app.handle(Request("GET", "/items")).status == 200


def test_deleting_an_absent_resource_is_a_404_not_a_500():
    app = Application()

    def remove(item_id):
        raise NotFoundError(f"item {item_id} is gone")

    app.route("DELETE", "/items/{item_id}")(remove)

    assert app.handle(Request("DELETE", "/items/1")).status == 404


def test_handler_errors_are_mapped_by_class_not_by_message():
    """A plain ``ValueError`` must not be mistaken for a client error."""
    app = Application()

    def bad():
        raise ValueError("could not parse config file")

    app.route("GET", "/bad")(bad)

    assert app.handle(Request("GET", "/bad")).status == 500


def test_response_body_of_a_validation_error_is_a_dict_with_details():
    app = Application()
    app.route("POST", "/items", schema=Schema({"a": Field(INT), "b": Field(INT)}))(
        lambda payload: payload
    )

    response = app.handle(Request("POST", "/items", body={"a": "x", "b": "y"}))

    assert isinstance(response.body, dict)
    assert len(response.body["error"]["details"]) == 2


def test_details_counts_are_stable_across_requests():
    """A shared error accumulator between requests would grow without bound."""
    app = Application()
    app.route("POST", "/items", schema=Schema({"name": Field(STR, min_length=1)}))(
        lambda payload: payload
    )

    for _ in range(3):
        response = app.handle(Request("POST", "/items", body={"name": ""}))
        assert len(response.body["error"]["details"]) == 1


def test_repeated_requests_do_not_accumulate_routes():
    app = Application()
    app.route("GET", "/items")(lambda: "list")

    for _ in range(3):
        app.handle(Request("GET", "/items"))

    assert len(app.routes) == 1


def test_request_scope_sees_its_own_request():
    captured: list[str] = []
    container = Container()

    def factory(scope):
        captured.append(scope.request.path if scope.request else "none")
        return object()

    container.register("ctx", factory)
    app = Application(container)
    app.route("GET", "/a", dependencies=["ctx"])(lambda ctx: "ok")
    app.route("GET", "/b", dependencies=["ctx"])(lambda ctx: "ok")

    app.handle(Request("GET", "/a"))
    app.handle(Request("GET", "/b"))

    assert captured == ["/a", "/b"]


def test_payload_param_can_be_renamed():
    app = Application()
    app.route(
        "POST",
        "/items",
        schema=Schema({"name": Field(STR)}),
        payload_name="data",
    )(lambda data: data)

    assert app.handle(Request("POST", "/items", body={"name": "ada"})).body == {"name": "ada"}


def test_deep_nested_structure_validates_and_coerces():
    schema = Schema(
        {
            "order": Field(
                OBJECT,
                fields={
                    "id": Field(INT, ge=1),
                    "lines": Field(
                        LIST,
                        item=Field(OBJECT, fields={"sku": Field(STR, min_length=1)}),
                        min_length=1,
                    ),
                },
            )
        }
    )

    result = schema.validate({"order": {"id": "7", "lines": [{"sku": "abc"}]}})

    assert result == {"order": {"id": 7, "lines": [{"sku": "abc"}]}}


def test_many_errors_in_a_deep_payload_are_all_reported():
    schema = Schema(
        {
            "order": Field(
                OBJECT,
                fields={
                    "id": Field(INT),
                    "lines": Field(LIST, item=Field(OBJECT, fields={"sku": Field(STR)})),
                },
            )
        }
    )

    with pytest.raises(ValidationError) as caught:
        schema.validate({"order": {"id": "x", "lines": [{"sku": 1}, {"sku": 2}]}})

    assert Counter(detail.path for detail in caught.value.details) == Counter(
        {"order.id": 1, "order.lines[0].sku": 1, "order.lines[1].sku": 1}
    )


def test_nested_mutable_defaults_are_not_shared():
    """A default that is only shallow-copied leaks its nested state."""
    schema = Schema(
        {
            "meta": Field(
                OBJECT,
                required=False,
                default={"tags": []},
                fields={"tags": Field(LIST, item=Field(STR), required=False, default=[])},
            )
        }
    )

    first = schema.validate({})
    first["meta"]["tags"].append("leaked")

    assert schema.validate({})["meta"]["tags"] == []


def test_validate_returns_plain_dicts():
    schema = Schema({"owner": Field(OBJECT, fields={"name": Field(STR)})})

    result = schema.validate({"owner": {"name": "ada"}})

    assert type(result) is dict
    assert type(result["owner"]) is dict
    assert copy.deepcopy(result) == result
