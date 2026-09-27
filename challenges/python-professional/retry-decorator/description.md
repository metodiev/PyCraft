# Retry Decorator

Flaky APIs, transient network errors, eventually-consistent services — mature
code assumes the first attempt may fail and retries the ones that are safe to
retry. Build the decorator that makes that a one-liner.

## Your task

Complete `retry` so that it can be used both plainly and with arguments:

```python
@retry()                    # defaults: times=3, exceptions=(Exception,)
def fetch(): ...

@retry(times=5, exceptions=(TimeoutError, ConnectionError))
def call_api(): ...
```

### Exact signature (required)

```python
def retry(times: int = 3, exceptions: tuple = (Exception,)):
    ...
```

`retry` is a **decorator factory**: calling it returns a decorator, and that
decorator returns a wrapper function.

### Behaviour

| Requirement | Detail |
| ----------- | ------ |
| Attempts | The wrapped function is called at most `times` times, **not** `times + 1`. `times` counts total calls, so `times=1` means a single attempt. |
| Retried errors | Only exceptions that are **instances of the types in `exceptions`** trigger another attempt. |
| Other errors | Any exception *not* covered by `exceptions` propagates immediately, without further attempts. |
| Final failure | When every attempt raises a matching exception, the **last** one is re-raised (the caller sees the original exception object). |
| Success | As soon as one attempt returns a value, that value is returned and no further attempts are made. |
| Metadata | `functools.wraps` must be used: the wrapper keeps the wrapped function's `__name__`, `__doc__`, and `__wrapped__`. |
| Arguments | Positional and keyword arguments are forwarded unchanged on every attempt. |

No delays or backoff are needed — the tests care only about call counts, error
propagation, and metadata.

## Examples

```python
attempts = 0

@retry(times=3)
def flaky():
    global attempts
    attempts += 1
    if attempts < 2:
        raise ValueError("not yet")
    return "ok"

flaky()        # -> "ok", attempts == 2

@retry(times=1)
def doomed():
    raise ValueError("boom")

doomed()       # -> ValueError("boom"), exactly 1 call

@retry(times=3, exceptions=(TypeError,))
def wrong_type():
    raise ValueError("unrelated")

wrong_type()   # -> ValueError propagates at once, exactly 1 call
```

## Constraints

* Standard library only; `functools` is allowed and expected.
* Do not catch exceptions that are not listed — swallowing unrelated errors is
  the classic bug this exercise is guarding against.

## Hints

<details>
<summary>Hint 1 — Three nested functions</summary>

A decorator factory needs three layers: `retry` → `decorator` → `wrapper`.
Only `retry` takes the configuration; `wrapper` is the function that loops.

```python
def retry(times=3, exceptions=(Exception,)):
    def decorator(func):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            ...
        return wrapper
    return decorator
```
</details>

<details>
<summary>Hint 2 — Catching and re-raising the right exception</summary>

Catch with the user-supplied tuple so unrelated exception types naturally
escape:

```python
for attempt in range(times):
    try:
        return func(*args, **kwargs)
    except exceptions:
        if attempt == times - 1:
            raise        # bare raise re-raises the active exception
```
</details>
