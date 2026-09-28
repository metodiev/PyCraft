# Validating Requests at the Boundary

Validation is not a step that happens at the start of a request; it is the
translation between two worlds. Outside the boundary, everything is a string
that may be absent, malformed, or hostile. Inside, you want typed objects whose
existence already proves the fields are present and well-shaped. Get that
translation right and the rest of the codebase never has to ask whether a value
is `None`.

## Parse, don't validate

The difference is what you have afterwards. A validation function returns a
boolean and leaves the raw value in place; a parser returns a *new object* of a
constrained type, and the caller has nothing else to use.

```python
from dataclasses import dataclass

@dataclass(frozen=True)
class CreateUser:
    email: str
    age: int
    display_name: str

def parse_create_user(payload: dict) -> CreateUser:
    return CreateUser(
        email=parse_email(payload.get("email")),
        age=parse_age(payload.get("age")),
        display_name=parse_name(payload.get("display_name")),
    )
```

Each helper raises a typed error when it cannot produce a value. The handler
converts the request body into `CreateUser` once, and the service layer accepts
`CreateUser` — not a dict. Because the type says what is guaranteed, a second
`if not user.get("email")` further down is not caution, it is a sign the parse
did not do its job. That redundancy is where inconsistencies creep in: someone
tightens the schema, the duplicate check is not updated, and two code paths now
disagree about what is valid.

## Syntax failures versus semantic failures

Separate the two, because clients handle them differently.

A **syntax** failure means the payload could not be understood: invalid JSON,
a required field missing, `"age": "banana"` where an integer is required, an
unknown enum member. These are `400` for a malformed body in general (and `415`
when the `Content-Type` itself is unsupported). Languages and frameworks differ
on whether "well-formed JSON, wrong types" is `400` or `422`; the important thing
is that you pick one convention and document it, and that a malformed request
never reaches business logic.

A **semantic** failure means the payload parsed but the request cannot be
satisfied: the email is already registered, the coupon has expired, the seat is
already taken. These are `409` when the conflict is with stored state and `422`
when the rule is intrinsic to the input — an end date before the start date can
be rejected without touching the database.

Two anti-patterns follow from blurring this line. Letting a `ValueError` from
deep inside a domain object escape as a `500` hides a client error as a server
fault. And catching every exception into a generic `400` discards the
information a client needs to fix the call. Have the parse layer raise a
dedicated error type carrying the offending field, and let the handler map it.

## Report all field errors at once

A client that sends ten fields with three mistakes should learn about three. If
you raise on the first failure, the caller needs three round trips, and each
round trip teaches them something that the previous one could have.

Collect errors into a mapping keyed by field path and return them together,
inside a single body:

```python
errors = [
    {"field": "email", "code": "invalid_format"},
    {"field": "age", "code": "out_of_range", "message": "must be >= 18"},
]
```

This requires the parse to attempt every field rather than short-circuit, which
is a design constraint on the helpers: each returns a value or an error, and the
caller decides whether to proceed. For nested payloads, use dotted or bracketed
paths (`items[2].quantity`) so the client can locate the problem. Do not leak
exception text or stack traces in the response; log them with a correlation id
and return the id.

## Never trust client-supplied identity

Fields the client sends are claims, not facts. A body containing `"user_id"`,
`"role"`, `"is_admin"`, `"tenant_id"` or `"price"` is an invitation to forge
them. Take identity from the authenticated principal — the parsed and verified
token, or the server-side session — and never from the payload.

```python
order = Order(
    user_id=principal.user_id,
    tenant=principal.tenant,
    sku=payload["sku"],
    quantity=payload["quantity"],
)
```

Ownership checks are a second, separate step: fetching `/orders/42` requires
confirming that order 42 belongs to `principal.user_id`. Both the missing check
and the trusting-the-payload shortcut produce the same class of bug, and neither
shows up in a happy-path test. Enforce it structurally where you can — query
scoped by the principal, rather than fetch-then-compare — because a scoped query
cannot be forgotten later.

## Keep validation out of the service layer

If the search endpoint and the create endpoint both call `search_users`, and
`search_users` re-validates the query string, you now have validation in two
places and a service function that cannot be used by trusted internal callers.
The service layer should accept typed input and enforce *business rules*;
format, presence, and range checks belong to the parse step at the edge.

A useful test: change the maximum page size from 100 to 50. If you must edit the
service, the boundary check was wrong. If the service raises `ValueError` for a
user id that does not exist, that is a domain outcome — return it as a typed
result or a domain exception, and translate it to `404` in the handler. The
handler is the only place that knows about HTTP.

## Practice

Build it end to end in [Validated Microservice](../challenges/web-development-validated-microservice),
then read [URLs, Query Strings and Percent-Encoding](../tutorials/web-development-url-and-query-encoding)
for the encoding rules your boundary parser has to respect. See the
[tutorials](../tutorials) index for other tracks.

<details><summary>Hint: testing the parser directly</summary>

Test `parse_create_user` as a plain function with a dict — no HTTP client, no
server. Boundary parsers are pure, so their tests are fast and exhaustive.

</details>
