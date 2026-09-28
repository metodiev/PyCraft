# URLs, Query Strings and Percent-Encoding

A URL looks like a string, and that is the trap. It is a structured identifier
whose components have different escaping rules, so code that builds one by
concatenation works for every value until the first value contains `&`, `=`, a
space, or a non-ASCII character. By then the bug is in production, invisible in
logs, and reported as "search sometimes returns everything".

## The grammar

`scheme://authority/path?query#fragment`

The scheme names the protocol. The authority holds an optional `user:password@`
prefix, a host, and an optional `:port`. The path identifies a resource within
that host. The query is a sequence of `key=value` pairs separated by `&`. The
fragment is resolved by the client only — it is never sent to the server.

Percent-encoding converts a byte into `%` followed by two uppercase hex digits.
Which bytes *need* encoding differs by component, and this is where bugs live.

| Component | Delimiters | Notes |
| ----- | ----- | ----- |
| Path segment | `/` | A literal `/` inside a segment must be escaped as `%2F` |
| Query key or value | `&`, `=`, `#` | Plus the characters above |
| Fragment | Same as query | Not transmitted |

The set of characters that may appear literally is `A-Z a-z 0-9 - . _ ~` plus
component-specific reserved characters. Everything else must be escaped. Encoding
is applied to *bytes*, so a non-ASCII character is first encoded as UTF-8 and then
percent-escaped: `café` becomes `caf%C3%A9`, and `€` becomes `%E2%82%AC`. This is
why "escape the Unicode code point" is wrong — a code point is not a byte.

## Plus is space, but only in the query

In `application/x-www-form-urlencoded` — the encoding used by HTML forms and by
most query strings — `+` represents a space. So `?q=hello+world` means
`q = "hello world"`. To put a literal plus in a query value, send `%2B`.

In the path, `+` is just a plus. `%2B` in a query value and `%2B` in a path both
decode to `+`, but a bare `+` decodes to a space in a query and to `+` in a path.
The practical consequence: never pass the same string through one encoder for
both positions, and when you write a decoder for the query, handle `+` before you
handle `%` escapes.

## Path segments and whole queries encode differently

Encoding a single path segment means escaping its delimiters so it stays one
segment. Encoding a whole query string means assembling already-encoded pieces
with `&` and `=`, which must *not* be escaped. Getting this backwards produces
either a mangled URL or a query with useless escape sequences.

Python's standard library makes the distinction explicit:

```python
from urllib.parse import quote, urlencode

segment = quote("café/au lait", safe="")
query = urlencode({"q": "a=b & c", "page": 2})
# segment -> 'caf%C3%A9%2Fau%20lait'
# query   -> 'q=a%3Db+%26+c&page=2'
```

`urlencode` defaults to `quote_plus`, which is correct for a query but wrong for
a path. For path segments use `quote` with `safe=""` so it does not leave `/`
unescaped, and when a slash is genuinely allowed as a separator, encode each
segment separately and join with `/`.

## Repeated parameters and ordering

Query strings can repeat a key — `?tag=a&tag=b` — and many clients expect that to
mean a set of values. In Python, `parse_qs` collects repeats into a list, while
`parse_qs(..., keep_blank_values=True)` is needed to keep `?q=` as `""` instead of
dropping it.

Key *order* is not semantically significant, but it is observable: caches and
signature validation often key on the raw string, so two logically equal queries
with different orders may not match. That looks harmless until a signed URL is
rejected because a proxy reordered the parameters, so treat the raw query as
opaque when signing, or normalise it explicitly.

## Why concatenation breaks

Consider a search box whose value is `café & cream = 5`.

```python
# Wrong: raw interpolation
url = f"https://api.example.com/search?q={value}&lang=en"
# https://api.example.com/search?q=café & cream = 5&lang=en
```

The server sees four parameters: `q=café `, ` cream `, ` 5`, `lang=en`. The space
terminates the request line and produces a malformed request. The ampersand starts
a new parameter. The non-ASCII bytes are outside the allowed URI set, so libraries
may refuse the request or encode them differently, and the two encodings will not
be equivalent to a signature check.

The correct construction encodes each value independently and lets a library join
the parts:

```python
from urllib.parse import urlencode

url = "https://api.example.com/search?" + urlencode(
    {"q": value, "lang": "en"}
)
```

When a full URL is already available, `urlsplit` and `urlunsplit` let you replace
exactly one component without touching the others — the safest way to add a
parameter to a URL you did not build. Round-trip every value through the encoder
and decoder in tests, including `&`, `=`, `+`, `%`, a space and a non-ASCII
character; a codec that handles those correctly handles the rest.

## Practice

Implement the codec in [Query String Codec](../challenges/web-development-query-string-codec),
and re-read [Validating Requests at the Boundary](../tutorials/web-development-request-validation) to see
where decoded values enter your typed parser. Other tracks are listed in the
[tutorials](../tutorials) index.

<details><summary>Hint: checking a round trip</summary>

`urlencode(parse_qs(query, keep_blank_values=True), doseq=True)` does not always
return the original string — order and plus-versus-percent choices differ. Round
trips should be tested on decoded values, not on the encoded text.

</details>
