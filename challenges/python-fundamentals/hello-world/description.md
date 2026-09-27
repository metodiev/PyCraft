# Hello, World

Welcome to **PyCraft**. Every engineering career starts the same way — putting
text on a screen.

## Your task

Complete the function `greet` so it returns a friendly greeting.

The function receives a `name` and must return the string:

```
Hello, <name>!
```

Include the comma, the space, and the trailing exclamation mark. **Return** the
string — do not print it.

## Examples

| Input | Expected result |
| ----- | --------------- |
| `"World"` | `"Hello, World!"` |
| `"Ada"` | `"Hello, Ada!"` |

## Hints

<details>
<summary>Hint 1 — Building strings</summary>

Use an f-string to interpolate a value:

```python
name = "World"
f"Hello, {name}!"
```
</details>

<details>
<summary>Hint 2 — Returning, not printing</summary>

`print()` displays text but the call evaluates to `None`. The tests check the
**return value**, so use `return`.
</details>
