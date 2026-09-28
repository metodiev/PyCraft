# Functions, Arguments and Scope

A function is the smallest unit of reusable code, and most of the bugs that
survive code review live in its boundary: what it accepts, what a default really
evaluates to, and which variable a name refers to when the same word appears in
three places.

This tutorial covers the mechanics you will use in every challenge that follows.
It assumes you can already write a function; it is about the parts that are easy
to get subtly wrong.

## Arguments: three ways to pass a value

Python resolves arguments in a fixed order, and knowing that order removes most
of the guesswork.

```python
def render(name, greeting="Hello", *, punctuation="!", width=0):
    text = f"{greeting}, {name}{punctuation}"
    return text.ljust(width)
```

| Call | Result | Why |
| ----- | ------ | --- |
| `render("Ada")` | `"Hello, Ada!"` | Defaults fill in |
| `render("Ada", "Hi")` | `"Hi, Ada!"` | Positional overrides the default |
| `render("Ada", punctuation="?")` | `"Hello, Ada?"` | Keyword skips `greeting` |
| `render("Ada", width=10)` | `"Hello, Ada! "` | Padded to ten characters |

Three things are worth naming explicitly.

**Positional parameters come first.** `name` and `greeting` can be passed by
position or by keyword. Once a caller passes one by keyword, everything after it
must also be by keyword — `render(greeting="Hi", "Ada")` is a `SyntaxError`.

**A bare `*` makes parameters keyword-only.** Everything after it in the
signature must be named at the call site. This is how a library keeps
`punctuation` and `width` readable at a glance, and how it stays free to reorder
them later without breaking callers.

**`*args` and `**kwargs` collect the rest.** A parameter named `*args` gathers
extra positional arguments into a tuple, and `**kwargs` gathers extra keyword
arguments into a dict:

```python
def log(message, *args, **kwargs):
    print(message.format(*args, **kwargs))

log("{0} scored {points}", "Ada", points=42)
```

## The mutable default trap

This is the single most common Python bug, and it is worth being able to
recognise on sight:

```python
def add_item(item, items=[]):        # wrong
    items.append(item)
    return items

add_item("a")   # ['a']
add_item("b")   # ['a', 'b']  — not what the caller expects
```

Default values are evaluated **once**, when the `def` statement runs, and the
resulting object is stored on the function. Every call that omits the argument
receives that same list. Appending to it mutates a shared object, so state leaks
between calls.

The fix is a sentinel:

```python
def add_item(item, items=None):
    if items is None:
        items = []
    items.append(item)
    return items
```

Use `None` as the sentinel, and test with `is None` rather than `== None` (or a
falsy check, which would wrongly reject a deliberately empty list). The same
rule applies to dicts, sets and any other mutable default.

## Scope: where a name is looked up

Python resolves a name by searching four scopes, in order, and stopping at the
first match. The rule is known as **LEGB**: Local, Enclosing, Global, Built-in.

```python
total = 0                        # global

def outer():
    count = 0                    # enclosing (for inner)

    def inner():
        count_local = count      # enclosing: finds `count`
        return count_local + total   # global: finds `total`
    return inner()
```

Assigning to a name inside a function makes it local **for the whole function**,
not just after the assignment. That is why this raises:

```python
counter = 0

def bump():
    counter += 1     # UnboundLocalError
```

`counter += 1` is an assignment, so Python treats `counter` as local and reads it
before it has a value. Declaring `global counter` (or `nonlocal` for an enclosing
function) opts back out, but needing to is usually a sign that the function
should return a value instead of mutating shared state.

Each function call gets a **fresh** local namespace. Locals do not persist
between calls, which is exactly what makes the mutable-default trap surprising
when you first meet it: the function's own locals are fresh, but its *default
arguments* are not.

## `return` and falling off the end

A function with no `return`, or a `return` with no value, evaluates to `None`.

```python
def show(label):
    print(label)          # returns None

result = show("hi")       # prints "hi"
print(result is None)     # True
```

This matters more often than it sounds. A function that prints its result and
one that returns it look identical at a glance, and a test that checks a return
value will fail with a confusing `None` if you used `print`. When a challenge
says *return* the value, it means the caller must be able to use it:

```python
def greet(name):
    return f"Hello, {name}!"

message = greet("World")   # usable: "Hello, World!"
```

## Putting it together

A well-behaved function has a narrow contract: it accepts what it needs,
documents the defaults, returns rather than prints, and does not mutate anything
it was handed by default. The habits are small, and they are what separate code
that passes the visible tests from code that survives the hidden ones.

## Practice

Apply this material in the [Hello, World challenge](../challenges/python-fundamentals-hello-world):
build a function with a defaulted, keyword-safe signature and confirm the tests
see your **return value**, not your output.
