# Strings, Bytes and Text Formatting

Text handling looks trivial until a file arrives with a byte-order mark, a `\r\n`
line ending, or a quoted comma sitting inside a field. Most of those bugs come from
one confusion — where the boundary between bytes and text actually is — and from two
methods that quietly do more than their names suggest.

## str is text, bytes is a transport format

A `str` is a sequence of Unicode code points; a `bytes` is a sequence of integers
0–255. The only bridge between them is an encoding, applied explicitly:

```python
raw = "café".encode("utf-8")      # b'caf\xc3\xa9'
text = raw.decode("utf-8")        # 'café'
len("café"), len(raw)             # (4, 5)
```

Text files opened with `open(path)` or `open(path, encoding="utf-8")` decode on read
and encode on write; files opened with `"rb"` never touch the boundary. Network
protocols, compression and hashing all operate on bytes, so the encode/decode step
belongs at the edge of your program, not sprinkled through the middle.

Two traps follow. Indexing differs by type: `b"abc"[0]` is the integer `97`, while
`"abc"[0]` is the one-character string `"a"`. And decoding with the wrong codec raises
`UnicodeDecodeError`; when data is genuinely untrusted or mixed, `errors="replace"`
keeps the pipeline alive at the cost of losing bytes, while `errors="surrogateescape"`
round-trips arbitrary bytes losslessly.

## F-strings and format specs

An f-string evaluates expressions at runtime, and everything after `:` is a format
spec with its own small grammar: fill, alignment, sign, width, precision and type.

```python
name, score, ratio = "Ada", 1234567, 0.8734
f"{name:<10}|"        # 'Ada       |'   left-align in 10
f"{score:,}"          # '1,234,567'
f"{ratio:.1%}"        # '87.3%'
f"{ratio:>8.2f}"      # '    0.87'
f"{42:#06x}"          # '0x002a'
f"{name!r}"           # "'Ada'"  — repr, before the format spec
```

Use `!r` when the value might be a string containing whitespace or newlines; plain
interpolation makes `"a b"` and `"a  b"` indistinguishable in logs. Pre-3.12 you cannot
reuse the same quote character inside an f-string, and backslashes are not allowed in
the expression part even now, so extract complicated expressions into a variable first.

## Immutability and the cost of repeated +=

Strings cannot be modified in place. `s += "x"` therefore reads as "create a new string
and rebind the name", and doing it in a loop makes the total work quadratic — each
iteration copies everything accumulated so far.

```python
def slow(parts):
    out = ""
    for part in parts:
        out += part          # O(n²) overall: copies 1 + 2 + 3 + ... characters
    return out

def fast(parts):
    return "".join(parts)    # one allocation, O(n)
```

CPython has an optimisation that resizes the buffer in place when the string has exactly
one reference, which hides the problem in toy benchmarks and makes the code look fine
until the loop is wrapped in a function that keeps a second reference, or runs on another
interpreter. Do not rely on it: if you are accumulating, collect into a list and join, or
into `io.StringIO` when the pieces arrive from many places.

## split, join, strip and partition

```python
"a,b,,c".split(",")       # ['a', 'b', '', 'c']  — empty fields survive
"a  b \t c".split()       # ['a', 'b', 'c']      — runs of whitespace, no empties
"a=1=2".split("=", 1)     # ['a', '1=2']         — maxsplit bounds the work
"-".join(["a", "b"])      # 'a-b'                — separator belongs to join
"key: value".partition(":")   # ('key', ':', ' value')
```

`partition` always returns a three-tuple and never raises, which is why it beats
`split(":", 1)` for parsing a single delimiter — you get a guaranteed structure plus a
truthy separator to test. `split()` with no argument is the opposite contract: it
collapses whitespace runs and drops leading and trailing empties.

`strip` is where surprises live. It removes any of the characters in its argument set
from both ends, not a prefix or suffix string:

```python
"  padded \n".strip()        # 'padded'
"prefix-x".strip("prefix-")  # ''      — all these characters are stripped
"http://example.com".strip("http://")  # 'example.com' by luck, not by design
```

That third line appears correct until the host is `http://http.example` or the path ends
in a letter that belongs to the set. For a known prefix or suffix use
`removeprefix`/`removesuffix` (3.9+), which match literally.

The subtle one is `strip()` versus `rstrip("\n")`. `strip()` removes spaces, tabs and
carriage returns as well as newlines, so a line whose trailing whitespace is meaningful
(a fixed-width field, a value containing a trailing space) is silently changed.
`rstrip("\n")` removes only newlines, but leaves the `\r` of a CRLF file attached to the
data. When the requirement is "drop the line terminator", say exactly that:

```python
line.rstrip("\r\n")     # only line terminators
line.strip()            # terminators plus any surrounding whitespace
line.removesuffix("\n") # exactly one newline, if present
```

## Parsing a line with quoted commas

Splitting on every comma breaks the moment a field contains a comma inside quotes. The
correct model is a small state machine that walks characters and keeps one boolean:

```python
def parse_line(line):
    fields, buf, in_quotes, i = [], [], False, 0
    while i < len(line):
        ch = line[i]
        if in_quotes:
            if ch == '"' and i + 1 < len(line) and line[i + 1] == '"':
                buf.append('"'); i += 2          # "" -> one literal quote
                continue
            if ch == '"':
                in_quotes = False                # closing quote
            else:
                buf.append(ch)
        elif ch == ',':
            fields.append("".join(buf)); buf = []
        elif ch == '"' and not buf:
            in_quotes = True                     # opens only at field start
        else:
            buf.append(ch)
        i += 1
    if in_quotes:
        raise ValueError("unterminated quoted field")
    fields.append("".join(buf))
    return fields
```

A quote opens a field only when the buffer is empty, so an embedded `"` mid-field stays
literal instead of starting a quoted section. A `in_quotes` flag still set at the end
means the line was malformed and the call is rejected. Note that this snippet, like
`csv.reader`, tolerates stray characters after a closing quote; a strict RFC 4180 parser
rejects them, which is one of the checks the challenge's tests will make. Reach for
`csv` in production; understand this loop when you must validate or pre-screen input that
`csv` accepts too leniently.

## Practice

Work through [CSV Line Parser](../challenges/python-fundamentals-csv-line-parser), which
parses a single RFC 4180 style line and rejects malformed quoting.

<details><summary>Hint: parsing with a state flag</summary>

Track one flag for "currently inside quotes", and let a doubled quote consume itself
rather than closing the field. Parse characters, not comma-separated strings, and decide
what to do with an unterminated field before you return.

</details>
