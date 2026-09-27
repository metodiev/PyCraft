# Query String Codec

`?page=2&tag=python&tag=web` — the query string is the part of HTTP everybody
hand-writes and everybody gets subtly wrong: a literal `+` becomes a space, a
`%2B` stays a plus, an empty value is not the same as a missing key, and
repeated keys need a list.

## Your task

Implement `encode_query(pairs)` and `decode_query(query)`.

### `encode_query(pairs)`

Take an iterable of `(key, value)` string pairs and return the query string
**without** a leading `?`.

* Keys and values are percent-encoded with the "unreserved" set only —
  `A–Z a–z 0–9 - . _ ~` stay literal; **everything else** becomes `%XX` with
  **uppercase** hex digits. In particular a space becomes `%20`, not `+`.
* Pairs are emitted in the order given, joined by `&`, in `key=value` form.
* An empty pair list gives `""`.
* A non-`str` key or value raises `TypeError`.

### `decode_query(query)`

Return a `list` of `(key, value)` string pairs, in order, **preserving
duplicates** — never a dict.

* `+` decodes to a space; `%XX` decodes to the byte with that hex value.
* Decoded bytes are UTF-8: `%C3%A9` is `"é"` (the query string may also contain
  literal non-ASCII characters).
* A parameter with no `=` yields `""` as its value (`"flag"` → `("flag", "")`).
* A leading `?` on the input is ignored (`"?a=1"` → `[("a", "1")]`).
* An empty query, or one that is only `?` or `&`, yields `[]`.
* Malformed input raises `ValueError`: a `%` not followed by two hex digits, or
  a percent-escape sequence that is not valid UTF-8.

## Examples

| Call | Expected result |
| ---- | --------------- |
| `encode_query([("a", "1")])` | `"a=1"` |
| `encode_query([("a b", "c d")])` | `"a%20b=c%20d"` |
| `encode_query([("q", "a+b")])` | `"q=a%2Bb"` |
| `encode_query([("x", "é")])` | `"x=%C3%A9"` |
| `encode_query([])` | `""` |
| `decode_query("a=1&b=2")` | `[("a", "1"), ("b", "2")]` |
| `decode_query("a=1&a=2")` | `[("a", "1"), ("a", "2")]` |
| `decode_query("q=a+b")` | `[("q", "a b")]` |
| `decode_query("q=a%2Bb")` | `[("q", "a+b")]` |
| `decode_query("?flag")` | `[("flag", "")]` |
| `decode_query("a=1&")` | `[("a", "1")]` |
| `decode_query("x=%zz")` | raises `ValueError` |

## Constraints

* Standard library only. `urllib.parse` exists but decoding `+` and validating
  malformed escapes the way the table above describes is easier to get right by
  hand — and the tests can tell the difference (e.g. `quote_plus` emits `+` for
  spaces, which this task forbids).
* `encode_query(decode_query(q))` must reproduce `q` exactly for every
  canonical query string.
* Never print; return values only.

## Hints

<details>
<summary>Hint 1 — Percent-encoding by hand</summary>

Encode the UTF-8 bytes and keep only the unreserved characters literal:

```python
UNRESERVED = set("ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-._~")

def _escape(text):
    return "".join(
        chr(byte) if chr(byte) in UNRESERVED else f"%{byte:02X}"
        for byte in text.encode("utf-8")
    )
```

Iterating the UTF-8 bytes (not the characters) is what makes multi-byte
characters come out as several `%XX` groups.

</details>

<details>
<summary>Hint 2 — Splitting safely, then decoding</summary>

Split once per pair so a `=` inside a value survives:

```python
for part in query.lstrip("?").split("&"):
    if not part:
        continue
    key, separator, value = part.partition("=")
    pairs.append((_unescape(key), _unescape(value)))
```

For `_unescape`, replace `+` with a space, collect the raw bytes into a
`bytearray`, and decode once at the end with `.decode("utf-8")` — a sequence
that decodes to invalid UTF-8 raises `UnicodeDecodeError`, which is a subclass of
`ValueError`, so a bare `except` clause is not needed for that case (but the
`%zz` case is yours to detect).
</details>
