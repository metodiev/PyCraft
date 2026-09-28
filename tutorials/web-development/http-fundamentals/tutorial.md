# HTTP Fundamentals for API Developers

Frameworks hide HTTP well enough that you can ship an endpoint without ever
thinking about the protocol. That works until a client caches a response it
should not have, a proxy retries a non-idempotent call, or a client sends
`text/plain` and gets a 500 instead of a 415. The protocol decisions below are
small, visible at the boundary, and expensive to change later.

## The shape of a message

A request is a method, a target, headers, and an optional body.

```bash
curl -i -X POST https://api.example.com/v1/orders \
  -H 'Content-Type: application/json' \
  -H 'Authorization: Bearer <token>' \
  -d '{"sku": "A-1", "quantity": 2}'
```

The response echoes a status line, headers, and a body. `GET` and `HEAD` carry no
semantics for a request body; `POST`, `PUT` and `PATCH` do. Query strings select
or filter a representation of a resource; the path identifies it. Sending an
identifier in a query string rather than the path is legal but loses the
hierarchy that caching and logs depend on.

## Status codes: pick the one that is true

The first digit is the family: 2xx success, 3xx redirection, 4xx client error,
5xx server error. The specific code is what a client's retry and error handling
branch on.

| Code | Use it when |
| ----- | ----- |
| 400 | The request is malformed — bad JSON syntax, unparseable field |
| 401 | No credentials, or invalid/expired ones. Sends `WWW-Authenticate` |
| 403 | Credentials are fine but this identity may not do this |
| 404 | The resource does not exist, or you are hiding its existence from an unauthorised caller |
| 409 | The request conflicts with current state — duplicate key, version mismatch |
| 422 | Well-formed syntax, but the values fail semantic validation |
| 500 | Your code failed. Never for bad input |

The 401/403 pair is the most commonly confused. `401` means "authenticate";
`403` means "authenticated, not allowed". Returning `403` to an anonymous caller
tells them the resource exists; if that matters, return `404` instead. Between
409 and 422 the rule of thumb is whether the failure depends on stored state
(taken username, stale `If-Match` version) or only on the submitted values
(negative quantity, invalid date range). Both are client errors; neither is a
`500`.

Use `201` with a `Location` header when a `POST` creates a resource, `204` for a
success with no body, and `202` when work is queued. A `200` with an `"error"`
field is a trap: clients that branch on status will treat it as success.

## Idempotency decides retries

An operation is idempotent when repeating it leaves the same state. `GET`, `PUT`,
`DELETE`, `HEAD` and `OPTIONS` are defined as idempotent; `POST` is not.

The consequence is practical. A client or intermediate proxy that times out on a
`PUT` can safely resend it — the second call overwrites the same value. A
timed-out `POST /orders` cannot be blindly retried, because the first attempt may
have committed. If you need safe retries on a non-idempotent operation, accept a
client-generated idempotency key and store it with the result, returning the
original response for a repeat of that key. Note that `DELETE` is idempotent but
not necessarily successful twice: the second call may return `404` or `204`
according to your contract, but the state is the same either way.

## Headers, content negotiation and tokens

Header names are case-insensitive — `Content-Type`, `content-type` and
`CONTENT-TYPE` are the same field — because the original specification treats
them that way and existing implementations rely on it. Header *values* are not
case-insensitive except where a specific field says so, and the values of
repeated headers must be combined in order.

`Content-Type` describes the body you sent; `Accept` describes what you will
accept back. A server that cannot serve any acceptable type should return `406`,
and one that receives a body it cannot parse should return `415`. Always declare
the charset for textual formats, and remember that `application/json` is UTF-8 by
definition — adding `; charset=utf-8` is harmless, and omitting it is not an
error. On the response side, `Vary: Accept` matters: without it a cache can hand
an XML representation to a client that asked for JSON.

HTTP is stateless: each request must carry everything needed to understand it.
A bearer token in the `Authorization` header is the usual choice for APIs —
clients send it explicitly, it works across services, and it is not attached
automatically by a browser. Cookies are sent automatically by the browser to a
matching origin, which is why they are the vector for cross-site request forgery
and require `SameSite` and CSRF protection. Do not put a token in a URL: query
strings appear in logs, browser history and `Referer` headers.

## Practice

Apply this material in [Validated Microservice](../challenges/web-development-validated-microservice),
then read [Validating Requests at the Boundary](../tutorials/web-development-request-validation). The
[challenges](../challenges) catalogue lists the wider track.

<details><summary>Hint: checking the real exchange</summary>

`curl -i` prints the response headers alongside the body; frameworks in
development mode mask the exact codes, so verify against the wire format.

</details>
