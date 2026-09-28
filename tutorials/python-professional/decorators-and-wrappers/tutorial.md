# Decorators, Wrappers and functools

A decorator is a function that takes a function and returns something callable. That is
the whole idea, and the difficulty is never the idea — it is the closure that carries the
extra state, the metadata that gets silently destroyed, and the extra layer of nesting
that appears when the decorator needs arguments.

## Functions are objects

A `def` binds a name to a function object like any other value. It can be passed,
returned, stored and replaced:

```python
def shout(text):
    return text.upper()

call = shout                 # another name for the same object
call("hi")                   # 'HI'
shout = lambda text: text    # rebinding the name; functions are mutable state
```

A closure is a nested function that reads a variable from the enclosing scope. The
enclosed variable is looked up when the inner function is **called**, not when it is
defined, which is why late binding surprises people:

```python
funcs = [lambda: i for i in range(3)]
[f() for f in funcs]        # [2, 2, 2] — every closure sees the final i
funcs = [lambda i=i: i for i in range(3)]
[f() for f in funcs]        # [0, 1, 2] — default binds the value now
```

## The decorator protocol

`@decorator` above a `def` is shorthand for `func = decorator(func)`. The returned value
replaces the original name, so it must be callable and it must accept the same arguments:

```python
def logged(func):
    def wrapper(*args, **kwargs):
        print(f"call {func.__name__}")
        return func(*args, **kwargs)
    return wrapper

@logged
def add(a, b):
    return a + b
```

`*args, **kwargs` is what keeps the wrapper signature-agnostic; anything narrower makes
the decorator unusable on half your functions. Ordering matters when you stack them:
the one closest to the `def` is applied first, so `@a` over `@b` means `a(b(func))`, and
the outermost decorator's wrapper runs first at call time.

## functools.wraps is not optional

The wrapper above has thrown away the metadata. `add.__name__` is now `"wrapper"`, the
docstring is gone, and signature-based tooling — `inspect.signature`, FastAPI and Flask
routing, test runners that read parameters, `pickle` — sees the wrong function:

```python
import functools

def logged(func):
    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        print(f"call {func.__name__}")
        return func(*args, **kwargs)
    return wrapper
```

`functools.wraps` copies `__module__`, `__name__`, `__qualname__`, `__doc__`,
`__dict__` and `__wrapped__`, and sets the wrapper's signature to the wrapped function's.
Two practical consequences: debuggers and `help()` show the real function, and
`inspect.signature(add)` returns the real parameters. Also use
`functools.wraps` on the outer function when the decorator takes arguments — it is easy
to remember on the inner wrapper and forget a level up.

There is a cost worth naming: `inspect.signature` on a wrapped function has to follow
`__wrapped__` and is slower than on a plain one, and some framework code caches it. Not a
reason to skip `wraps` — a reason not to call `signature` in a hot loop.

## Decorators that take arguments

`@retry(attempts=3)` cannot pass the function to `retry` directly, because
`retry(attempts=3)` is a call, not a decorator. So a decorator factory returns a
decorator, which returns a wrapper — three levels:

```python
import functools, time

def retry(attempts=3, delay=0.1, exceptions=(Exception,)):
    def decorator(func):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            for attempt in range(1, attempts + 1):
                try:
                    return func(*args, **kwargs)
                except exceptions:
                    if attempt == attempts:
                        raise          # final attempt: propagate the real error
                    time.sleep(delay)
            raise ValueError("attempts must be at least 1")
        return wrapper
    return decorator

@retry(attempts=5, exceptions=(TimeoutError,))
def fetch(url):
    ...
```

Points that matter in production: re-raise the **final** exception rather than swallowing
it, and use a bare `raise` inside the handler so the original traceback survives; make the
retryable exception tuple a parameter, because retrying a `ValueError` never helps;
use exponential backoff and jitter instead of a fixed delay, or a failing dependency gets
hammered by every client at the same interval; and be aware that the wrapper hides the
fact that one logical call may issue five. A retry around a non-idempotent write — one
that charges a card — needs an idempotency key, not just a loop; otherwise a timeout that
succeeded server-side turns into a second charge when the retry fires.

Applying the decorator at import time is also a design decision: it wraps every call of
that function, including the ones in tests where you wanted the failure to be visible
immediately.

## functools.lru_cache and the hashability requirement

`lru_cache` memoises on the arguments tuple, so every argument must be hashable — which
is the same requirement `dict` keys have, and it fails the same way, with `TypeError:
unhashable type: 'list'` at call time:

```python
import functools

@functools.lru_cache(maxsize=128)          # maxsize=None means unbounded
def fib(n: int) -> int:
    return n if n < 2 else fib(n - 1) + fib(n - 2)

fib.cache_info()      # CacheInfo(hits=..., misses=..., maxsize=128, currsize=...)
fib.cache_clear()
```

Cache keys use equality, not identity, because a call is keyed by the argument values:
with the default `typed=False`, `f(1)`, `f(1.0)` and `f(True)` all share one entry. Pass
`typed=True` when `1` and `True` must not collapse together — with it, those three calls
produce three entries and only an exact repeat is a hit. Note also that the key includes
the keyword names, so `f(a=1, b=2)` and `f(b=2, a=1)` are two separate entries for the
same logical call.

Two further traps. An unbounded cache keyed by a growing set of distinct arguments is a
memory leak, which is why `maxsize` defaults to 128. And a cached function that is not
pure — it reads a file, a clock, or a database — will return stale results, so
`cache_clear` belongs in whatever invalidates that state.

For instance methods, `@lru_cache` on the method keeps `self` in the key, pinning every
instance alive for as long as the cache entry survives; modern alternatives are
`functools.cached_property`, or a cache keyed by an immutable id. When you only need to
cache a function that takes one hashable argument, `functools.cache` is `lru_cache(maxsize=None)`
with a shorter name.

## Practice

Build a decorator factory in
[Retry Decorator](../challenges/python-professional-retry-decorator): it retries a failing
call and re-raises the final error, preserving the wrapped function's metadata.

<details><summary>Hint: three levels and a final raise</summary>

Return a decorator from the factory, wrap the function with `functools.wraps`, count
attempts in the closure, and re-raise on the last one so the caller sees the real
exception rather than a `RuntimeError` from the loop.

</details>
