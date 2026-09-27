# Project: Validated Microservice

**This is a project, not a drill.** Three modules make up the core of a
web-style service, and you must wire them together so the behaviour emerges
from the parts.

The interesting part is not "route a path to a function". It is that **a
service is defined by how it fails**: whether a bad payload reports one problem
or all of them, whether a state conflict is confused with a syntax error, and
whether a database session opened for one request is still open — or still
shared — for the next.

No web framework is involved. Requests and responses are plain objects and the
tests drive the dispatcher directly, so what is being assessed is the *design*,
not the plumbing.

| File | Responsibility |
| ---- | -------------- |
| `schema.py` | A declarative field/validation layer: types, coercion, constraints |
| `errors.py` | A typed error hierarchy, its HTTP status mapping and error bodies |
| `service.py` | Request/response objects, the DI container and the dispatcher |

`errors.py` is a leaf — it imports nothing local. `schema.py` imports only
`errors`. `service.py` ties them together.

## Your task

### `schema.py`

A `Schema` maps field names onto `Field` definitions.

| Name | Contract |
| ---- | -------- |
| `STR`, `INT`, `FLOAT`, `BOOL`, `LIST`, `OBJECT` | Type tags: `"str"`, `"int"`, `"float"`, `"bool"`, `"list"`, `"object"` |
| `MISSING` | Sentinel: "no default was declared" |
| `Field` | Dataclass: `type`, `required=True`, `default=MISSING`, `nullable=False`, `min_length`, `max_length`, `ge`, `le`, `choices`, `item`, `fields` |
| `Schema(fields)` | Build a schema from `{name: Field}` |
| `Schema.validate(data)` | Return a plain `dict` of coerced values |

`validate` semantics:

- **Report every problem.** Collect all failures and raise a single
  `ValidationError` whose `details` hold one `FieldError` per problem — never
  raise on the first one.
- **Paths identify the offender.** A top-level field is `name`; a list element
  is `tags[1]`; a nested object field is `owner.email`.
- **`required` means the key is absent.** A *present* falsy value (`0`, `""`,
  `False`, `[]`) is a real value and must be validated and kept, not replaced by
  the default.
- **`default` applies only when the key is absent**, may be mutable, and must
  not be shared between results (two calls and a later `append` must not see
  each other's data).
- **Optional with no default** simply omits the key from the result.
- **Undeclared keys are dropped**, and the caller's mapping is never mutated.
- **Coercion from the wire:** `"42"` → `42`, `"1.5"` → `1.5`, `"true"`/`"false"`
  (also `"yes"`/`"no"`, `"on"`/`"off"`, `"1"`/`"0"`) → `bool`. A `bool` is *not*
  a valid `INT` on the wire. A value that cannot be coerced is a `"type"` error.
- **`None`** is rejected unless `nullable=True`.
- **Constraints** on `str`/`list`: `min_length`/`max_length`. On `int`/`float`:
  `ge`/`le`. `choices` applies to any type. Codes: `missing`, `null`, `type`,
  `too_short`, `too_long`, `too_small`, `too_large`, `choice`.
- **Nesting:** `LIST` validates each element with `item`; `OBJECT` validates its
  mapping with `fields`.

### `errors.py`

| Name | Contract |
| ---- | -------- |
| `FieldError(path, code, message)` | Frozen dataclass; `to_dict()` → `{"path", "code", "message"}` |
| `ApiError(message=None, *, details=())` | Base error; `message` falls back to the class's `default_message`; `details` is a tuple |
| `ValidationError` | 422, `"validation_error"` |
| `NotFoundError` | 404, `"not_found"` |
| `MethodNotAllowedError(..., allowed=())` | 405, `"method_not_allowed"`; `allowed` is a tuple |
| `ConflictError` | 409, `"conflict"` |
| `ApiError.to_body()` | `{"error": {"code", "message", "details": [...]}}` |
| `status_for(error)` | The status for any exception: an `ApiError` reports its own, **anything else is 500** |

`MethodNotAllowedError.to_body()` adds `body["error"]["allowed"]` as a list.
The bodies must be JSON-serialisable: `details` is a list, not a tuple.
A subclass that sets its own `status`/`code` must keep them (`status_for` reads
the instance, not a hard-coded table).

### `service.py`

| Name | Contract |
| ---- | -------- |
| `Request(method, path, body=None, query={}, headers={})` | `query` maps a key onto the **list** of values it carried |
| `Request.from_target(method, target)` | Parse `"/items?tag=a&tag=b"`; upper-case the method; `+` means space; blank values (`?q=`) are kept |
| `Response(status, body=None, headers={})` | Plain result object |
| `Container()` | `register(name, factory, *, scope=REQUEST, teardown=None)`, `create_scope(request=None)`, `resolve(name, scope=None)` |
| `Scope` | `resolve(name)`, `close()`, and `scope.request` |
| `Application(container=None)` | `add_route`/`route`/`handle`; `app.routes` |
| `Application.handle(request)` | Return a `Response`; nothing may escape |

`Application` semantics:

- A handler only receives the parameters it declares, injected by name:
  a path parameter, the registered `payload_name` (default `payload`) holding the
  validated body, the `request`, and any dependency from `dependencies=`.
- A schema failure → 422; an unknown path → 404; a known path with the wrong
  method → **405** (with `allowed`); an `ApiError` raised by a handler → its own
  status; anything else → 500 with a generic body that leaks no internals.
- A literal segment beats `{placeholder}` whatever the registration order, and a
  trailing slash is ignored.
- Returning a `Response` passes it through; `None` becomes 204; anything else
  becomes a 200 with that body.
- **Lifetimes:** a `REQUEST`-scoped dependency is constructed **at most once per
  request**, is never shared with another request, is constructed only if the
  handler actually names it, and its `teardown` runs exactly once — *including
  when the handler raises*. Teardowns run newest-first. A `SINGLETON` is built
  once per container and never torn down. `Container.register` rejects an unknown
  scope and a teardown on a singleton with `ValueError`; an unknown name, or a
  request-scoped name resolved with no scope, is a `LookupError`.

## Examples

```pycon
>>> schema = Schema({"name": Field(STR, min_length=1), "age": Field(INT, ge=18)})
>>> schema.validate({"name": "ada", "age": "36"})
{'name': 'ada', 'age': 36}
>>> schema.validate({"name": "", "age": 17})
ValidationError: payload failed validation: 2 error(s)
>>> [d.path for d in _.details]
['name', 'age']

>>> status_for(ConflictError("taken")), status_for(RuntimeError("boom"))
(409, 500)

>>> app = Application()
>>> app.route("POST", "/items", schema=Schema({"name": Field(STR)}))(lambda payload: payload)
>>> app.handle(Request("POST", "/items", body={"name": "ada"})).status
200
>>> app.handle(Request("POST", "/items", body={})).status
422
```

## Constraints

- **Standard library only** — no `fastapi`, `flask`, `requests`, `pydantic`.
  The sandbox has CPython 3.12 and pytest, nothing more.
- Tests import the modules by plain name (`from schema import Schema`), so keep
  the module names as they are and use absolute local imports.
- `errors.py` must not import `schema` or `service`; `schema.py` must not import
  `service`.
- Coerced results are plain `dict`/`list`/scalars, never the caller's objects.

## Hints

<details>
<summary>Hint 1 — Collecting every error</summary>

Pass a single `problems` list down through the recursive walk instead of letting
each level raise. Every check *appends* a `FieldError` and carries on; only the
top-level `validate` raises, once, with `details=tuple(problems)`.

</details>

<details>
<summary>Hint 2 — Absent vs falsy</summary>

`data.get(name)` cannot tell `{"limit": 0}` from `{}` — both are falsy. Test
membership instead (`if name not in data:`), and give the "no default" case its
own sentinel object so `None` stays a legitimate value.

</details>

<details>
<summary>Hint 3 — Defaults that do not leak</summary>

`default` may be a list or dict. `copy.deepcopy` it into each result, or two
payloads will share one object and a later `append` will appear in both.

</details>

<details>
<summary>Hint 4 — Lifetimes and teardown</summary>

Give every scope its own `_instances` dict — the container's cache is for
singletons only. In `handle`, wrap the dispatch in `try/except/finally` and call
`scope.close()` in the `finally`: that is the only placement that runs on the
success path, on a returned `Response`, *and* when the handler raised.
`close()` should take the teardown list into a local variable so a second call
is a no-op.

</details>
