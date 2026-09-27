# Project: In-Process REST API Service

**This is a project, not a drill.** Several files make up the service, and you
must wire them together so behaviour emerges from the parts.

## Your task

Implement a small, framework-free HTTP-style request router with a middleware
chain. The tests drive it directly, so no socket or web framework is involved —
what is being assessed is the *design*, not the plumbing.

Two files must cooperate:

| File | Responsibility |
| ---- | -------------- |
| `router.py` | Path matching, parameter extraction, dispatch |
| `middleware.py` | Cross-cutting concerns wrapped around handlers |
| `service.py` | Assembles the two into something callable |

### `router.py` — `Router`

- `add_route(method, pattern, handler)` registers a handler.
- Patterns use `{name}` for a path segment, e.g. `/users/{user_id}`.
- `match(method, path)` returns `(handler, params)` or `None`.
- A literal segment must beat a parameterised one: with both `/users/me` and
  `/users/{user_id}` registered, `GET /users/me` must reach the literal route.
- Matching must ignore a trailing slash: `/users` and `/users/` are the same.
- Unknown method on a known path is *not* a match (return `None`); the caller
  decides how to report it.

### `middleware.py` — `MiddlewarePipeline`

- Middlewares wrap a handler: `middleware(handler) -> wrapped_handler`.
- They run **outermost first** on the way in, and unwind in reverse on the way
  out (the classic onion model).
- A middleware may short-circuit by returning without calling the next handler.

### `service.py` — `RequestService`

- `handle(method, path, **params)` dispatches through the middleware chain.
- Returns a `Response` with `status`, `body`, and `headers`.
- A matched route → `200`.
- No match → `404`.
- A handler raising `ValueError` → `400` (do not let it escape).

## Examples

| Call | Result |
| ---- | ------ |
| `service.handle("GET", "/users/42")` | `Response(200, {"id": "42"})` |
| `service.handle("GET", "/nope")` | `Response(404, {"error": "Not found"})` |
| handler raises `ValueError` | `Response(400, {"error": "..."})` |

## Constraints

- **Standard library only.** No `requests`, no web framework, no networking.
- Do not open sockets or files.
- Define `Response` in `service.py` (tests import it from there).

## Hints

<details>
<summary>Hint 1 — Ordering literal before parameterised</summary>

Iterate the registered routes in a way that prefers exact segment matches. One
approach is to compare how many segments are literal and pick the most specific
match rather than the first registered one.
</details>

<details>
<summary>Hint 2 — The onion model</summary>

Wrapping in a loop means the *last* middleware you apply ends up innermost. To
have the first middleware in your list run first, apply them in reverse order —
or fold with `functools.reduce` in the direction that puts item zero outermost.
</details>

<details>
<summary>Hint 3 — Splitting the path</summary>

`path.strip("/").split("/")` turns `/users/42/` into `["users", "42"]`. Watch out
for the root path, where the stripped result is empty.
</details>
